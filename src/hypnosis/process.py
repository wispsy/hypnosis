"""Owned subprocess proof of the selected wispsy.run-event/1 wire contract."""
import asyncio
from contextlib import aclosing
from dataclasses import dataclass
import hashlib
import json
import math
import re

from .runtime import Harness, RunControl, TERMINAL_KINDS

SCHEMA = 'wispsy.run-event/1'
EXIT_CODES = {'completed': 0, 'canceled': 130, 'failed': 1, 'limited': 3}
FIELDS = {'schema', 'run_id', 'sequence', 'kind', 'text', 'code'}
CODES = {'failed': {'source_error', 'source_close_error', 'command_error'},
         'limited': {'time_budget', 'event_budget', 'output_budget'}}


class ProtocolError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ProcessLimits:
    max_record_bytes: int = 65536
    max_stream_bytes: int = 16777216
    max_records: int = 100000
    max_seconds: float = 30
    grace_seconds: float = .2
    stderr_bytes: int = 65536

    def __post_init__(self):
        for name, maximum in (('max_record_bytes', 65536), ('max_stream_bytes', 16777216), ('max_records', 100000), ('stderr_bytes', 65536)):
            if type(getattr(self, name)) is not int or not 1 <= getattr(self, name) <= maximum:
                raise ValueError('Invalid process stream budget')
        for name, maximum in (('max_seconds', 3600), ('grace_seconds', 5)):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= maximum:
                raise ValueError('Invalid process deadline')


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolError('invalid_record')
        result[key] = value
    return result


class RunEventDecoder:
    def __init__(self, limits=None):
        self.limits = limits if limits is not None else ProcessLimits()
        self.buffer = bytearray()
        self.total_bytes = self.records = 0
        self.run_id = self.terminal = None

    def feed(self, data):
        if type(data) is not bytes or len(data) > 4096:
            raise ValueError('Feed bounded byte chunks of at most 4096 bytes')
        self.total_bytes += len(data)
        if self.total_bytes > self.limits.max_stream_bytes:
            raise ProtocolError('stream_limit')
        self.buffer.extend(data)
        result = []
        while b'\n' in self.buffer:
            end = self.buffer.index(10)+1
            if end > self.limits.max_record_bytes:
                raise ProtocolError('record_limit')
            raw = bytes(self.buffer[:end])
            del self.buffer[:end]
            self.records += 1
            if self.records > self.limits.max_records:
                raise ProtocolError('stream_limit')
            try:
                value = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                                   parse_constant=lambda v: (_ for _ in ()).throw(ProtocolError('invalid_record')))
            except (ValueError, UnicodeError, RecursionError):
                raise ProtocolError('invalid_record') from None
            if type(value) is not dict or set(value) != FIELDS or value['schema'] != SCHEMA:
                raise ProtocolError('invalid_record')
            if any(type(value[key]) is not str for key in ('run_id', 'kind', 'text', 'code')) or type(value['sequence']) is not int:
                raise ProtocolError('invalid_record')
            if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}', value['run_id']):
                raise ProtocolError('invalid_record')
            if value['sequence'] != self.records-1 or (self.run_id is not None and value['run_id'] != self.run_id):
                raise ProtocolError('sequence_error')
            kind = value['kind']
            if self.terminal is not None or (self.records == 1 and kind != 'started') or (self.records > 1 and kind not in {'delta', *TERMINAL_KINDS}):
                raise ProtocolError('sequence_error')
            if (kind != 'delta' and value['text']) or (kind not in CODES and value['code']) or (kind in CODES and value['code'] not in CODES[kind]):
                raise ProtocolError('invalid_record')
            self.run_id = value['run_id']
            if kind in TERMINAL_KINDS:
                self.terminal = value
            result.append(value)
        if len(self.buffer) >= self.limits.max_record_bytes:
            raise ProtocolError('record_limit')
        return result

    def finish(self):
        if self.buffer:
            raise ProtocolError('invalid_record')
        if self.terminal is None:
            raise ProtocolError('missing_terminal')


@dataclass(frozen=True)
class ProcessOutcome:
    status: str
    code: str
    transport_ok: bool
    returncode: int | None
    partial_effects: bool
    records: int
    stream_bytes: int
    stderr_bytes: int
    stderr_sha256: str
    stderr_truncated: bool

    def receipt(self):
        from dataclasses import asdict
        return asdict(self)


class ProcessRun:
    """One explicit argv, one owned child. Close the stream when leaving early."""
    def __init__(self, argv, *, limits=None, control=None):
        self.argv = tuple(argv)
        if not 1 <= len(self.argv) <= 128 or any(type(s) is not str or not s or len(s) > 65536 or '\0' in s for s in self.argv):
            raise ValueError('Select an explicit bounded argument vector')
        self.limits = limits if limits is not None else ProcessLimits()
        self.control = control if control is not None else RunControl()
        if type(self.limits) is not ProcessLimits or type(self.control) is not RunControl:
            raise TypeError('Use typed process limits/control')
        self.outcome = None
        self.stderr_tail = b''
        self.pid = None
        self._used = False

    async def stream(self):
        if self._used:
            raise RuntimeError('A process run is single-use')
        self._used = True
        decoder = RunEventDecoder(self.limits)
        process = reader = watcher = stderr = None
        stderr_count, stderr_hash = 0, hashlib.sha256()
        status, code, valid = 'failed', 'downstream_closed', False
        stop_reason = None

        async def drain_stderr():
            nonlocal stderr_count
            while chunk := await process.stderr.read(4096):
                stderr_count += len(chunk)
                stderr_hash.update(chunk)
                self.stderr_tail = (self.stderr_tail+chunk)[-self.limits.stderr_bytes:]

        async def watch():
            nonlocal stop_reason
            try:
                await asyncio.wait_for(self.control.wait(), self.limits.max_seconds)
                stop_reason = 'cancellation'
            except asyncio.TimeoutError:
                stop_reason = 'time_budget'
            if process.returncode is None:
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass
                await asyncio.sleep(self.limits.grace_seconds)
                if process.returncode is None:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass

        try:
            if self.control.canceled:
                status, code = 'canceled', 'cancellation'
                return
            process = await asyncio.create_subprocess_exec(*self.argv, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, limit=8192)
            self.pid = process.pid
            stderr = asyncio.create_task(drain_stderr())
            watcher = asyncio.create_task(watch())
            while True:
                reader = asyncio.create_task(process.stdout.read(4096))
                ready, _ = await asyncio.wait((reader, watcher), return_when=asyncio.FIRST_COMPLETED)
                if watcher in ready or stop_reason is not None:
                    status, code = ('canceled', 'cancellation') if stop_reason == 'cancellation' else ('limited', 'time_budget')
                    break
                chunk = reader.result()
                reader = None
                if not chunk:
                    decoder.finish()
                    exited = asyncio.create_task(process.wait())
                    try:
                        ready, _ = await asyncio.wait((exited, watcher), return_when=asyncio.FIRST_COMPLETED)
                        if watcher in ready:
                            status, code = ('canceled', 'cancellation') if stop_reason == 'cancellation' else ('limited', 'time_budget')
                            break
                        returncode = exited.result()
                    finally:
                        if not exited.done():
                            exited.cancel()
                            await asyncio.gather(exited, return_exceptions=True)
                    terminal = decoder.terminal
                    if returncode != EXIT_CODES[terminal['kind']]:
                        code = 'signal' if returncode < 0 else 'process_exit'
                    else:
                        status, code, valid = terminal['kind'], terminal['code'], True
                    break
                for record in decoder.feed(chunk):
                    yield record
        except ProtocolError as error:
            code = error.code
        except OSError:
            code = 'process_error'
        except asyncio.CancelledError:
            status, code = 'canceled', 'cancellation'
            raise
        finally:
            for task in (reader, watcher):
                if task is not None:
                    task.cancel()
            await asyncio.gather(*(task for task in (reader, watcher) if task is not None), return_exceptions=True)
            if process is not None:
                # Drain stdout during teardown so pipe pressure cannot block reaping.
                async def discard():
                    while await process.stdout.read(4096):
                        pass
                drain = asyncio.create_task(discard())
                try:
                    if process.returncode is None:
                        try:
                            process.terminate()
                        except ProcessLookupError:
                            pass
                        try:
                            await asyncio.wait_for(process.wait(), self.limits.grace_seconds)
                        except asyncio.TimeoutError:
                            process.kill()
                    await process.wait()
                    await drain
                    await stderr
                finally:
                    for task in (drain, stderr):
                        if task is not None and not task.done():
                            task.cancel()
                    await asyncio.gather(drain, stderr, return_exceptions=True)
            self.outcome = ProcessOutcome(status, code, valid, process.returncode if process else None,
                decoder.records > 0 and not (valid and status == 'completed'), decoder.records,
                decoder.total_bytes, stderr_count, stderr_hash.hexdigest(), stderr_count > self.limits.stderr_bytes)


async def write_run_stream(factory, output, *, run_id='stream', harness=None):
    """Write flushed records with OS pipe backpressure; no single-JSON wrapper."""
    decoder = RunEventDecoder()
    harness = harness if harness is not None else Harness()
    terminal = None
    async with aclosing(harness.stream(factory, run_id=run_id)) as events:
        async for event in events:
            value = {'schema': SCHEMA, **event.as_dict()}
            raw = (json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(',', ':'))+'\n').encode()
            for offset in range(0, len(raw), 4096):
                decoder.feed(raw[offset:offset+4096])
            output.write(raw.decode('ascii'))
            output.flush()
            terminal = event.kind
    decoder.finish()
    return EXIT_CODES[terminal]


@dataclass(frozen=True)
class StreamResult:
    exit_code: int
