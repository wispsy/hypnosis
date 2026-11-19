"""Finite run lifecycles; durable workflows remain in the workflow libraries."""
import asyncio
from dataclasses import asdict, dataclass
import math
import re
import time

TERMINAL_KINDS = frozenset({'completed', 'canceled', 'failed', 'limited'})


@dataclass(frozen=True)
class RunLimits:
    max_events: int = 4096
    max_output_bytes: int = 65536
    max_seconds: float = 30

    def __post_init__(self):
        if type(self.max_events) is not int or not 2 <= self.max_events <= 100000:
            raise ValueError('Event budget must be an integer from 2 to 100000')
        if type(self.max_output_bytes) is not int or not 0 <= self.max_output_bytes <= 16 * 1024 * 1024:
            raise ValueError('Output budget is outside the finite byte range')
        if type(self.max_seconds) not in (int, float) or not math.isfinite(self.max_seconds) or not 0 < self.max_seconds <= 3600:
            raise ValueError('Time budget must be finite and between 0 and 3600 seconds')


@dataclass(frozen=True)
class RunEvent:
    run_id: str
    sequence: int
    kind: str
    text: str = ''
    code: str = ''

    def as_dict(self):
        return asdict(self)


class RunControl:
    """Event-loop-owned cooperative cancellation, distinct from task cancellation."""
    def __init__(self):
        self._cancel = asyncio.Event()

    def cancel(self):
        self._cancel.set()

    @property
    def canceled(self):
        return self._cancel.is_set()

    async def wait(self):
        await self._cancel.wait()


class Harness:
    def __init__(self, limits=None):
        self.limits = limits if limits is not None else RunLimits()
        if type(self.limits) is not RunLimits:
            raise TypeError('limits requires RunLimits')

    async def stream(self, factory, *, run_id, control=None):
        """Yield bounded text events and one outcome on normal consumption.

        The factory returns an async iterable of text. Sources must cooperate
        with cancellation; a blocking provider needs a managed execution adapter.
        Closing/canceling this consumer propagates without a fake final outcome.
        """
        if type(run_id) is not str or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}', run_id):
            raise ValueError('run_id requires a stable bounded identifier')
        if not callable(factory):
            raise TypeError('Source factory must be callable')
        control = control if control is not None else RunControl()
        if type(control) is not RunControl:
            raise TypeError('control requires RunControl')
        sequence, output_bytes = 0, 0
        deadline = time.monotonic() + self.limits.max_seconds
        iterator, pending, canceled = None, None, None
        outcome, code = 'completed', ''
        yield RunEvent(run_id, sequence, 'started')
        sequence += 1
        try:
            if control.canceled:
                outcome = 'canceled'
            else:
                iterator = aiter(factory())
                canceled = asyncio.create_task(control.wait())
                while True:
                    if control.canceled:
                        outcome = 'canceled'
                        break
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        outcome, code = 'limited', 'time_budget'
                        break
                    pending = asyncio.ensure_future(anext(iterator))
                    ready, _waiting = await asyncio.wait((pending, canceled), timeout=remaining,
                                                       return_when=asyncio.FIRST_COMPLETED)
                    if canceled in ready:
                        outcome = 'canceled'
                        break
                    if pending not in ready:
                        outcome, code = 'limited', 'time_budget'
                        break
                    try:
                        value = pending.result()
                    except StopAsyncIteration:
                        break
                    pending = None
                    if type(value) is not str:
                        raise TypeError('Sources must produce text values')
                    if sequence >= self.limits.max_events - 1:
                        outcome, code = 'limited', 'event_budget'
                        break
                    encoded_size = len(value.encode('utf-8'))
                    if output_bytes + encoded_size > self.limits.max_output_bytes:
                        outcome, code = 'limited', 'output_budget'
                        break
                    output_bytes += encoded_size
                    yield RunEvent(run_id, sequence, 'delta', value)
                    sequence += 1
        except Exception:
            outcome, code = 'failed', 'source_error'
        finally:
            tasks = [task for task in (pending, canceled) if task is not None]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            close = getattr(iterator, 'aclose', None)
            if close is not None:
                try:
                    await close()
                except Exception:
                    outcome, code = 'failed', 'source_close_error'
        yield RunEvent(run_id, sequence, outcome, code=code)


async def demo_source(text='Hello from Hypnosis.'):
    """Deterministic offline producer; no provider or model is activated."""
    for character in text:
        yield character
        await asyncio.sleep(0)


async def run_demo(text='Hello from Hypnosis.'):
    events = [event async for event in Harness().stream(lambda: demo_source(text), run_id='demo')]
    return {'schema': 1, 'run_id': 'demo', 'status': events[-1].kind,
            'text': ''.join(event.text for event in events), 'events': len(events)}
