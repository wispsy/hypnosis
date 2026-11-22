"""Explicit resource admission over func_seq's durable stage lifecycle."""
import asyncio
from dataclasses import asdict, dataclass
import json
import math
import time

from .execution import bounded_call, call_owned
from .records import _identifier, _sha
from .runtime import RunControl
from .tools import digest


@dataclass(frozen=True)
class RoleJob:
    id: str
    role: str
    source_sha256: str
    function: object
    dependencies: tuple[str, ...] = ()
    resource: str = 'shared-model'
    units: int = 1

    def __post_init__(self):
        for value in (self.id, self.role, self.resource):
            _identifier(value)
        _sha(self.source_sha256)
        if not callable(self.function) or type(self.dependencies) is not tuple or len(set(self.dependencies)) != len(self.dependencies):
            raise ValueError('Select a trusted function and distinct dependencies')
        for value in self.dependencies:
            _identifier(value)
        if type(self.units) is not int or not 1 <= self.units <= 1000000:
            raise ValueError('Job units must be a positive bounded reservation')

    def identity(self):
        return {key: getattr(self, key) for key in ('id', 'role', 'source_sha256', 'dependencies', 'resource', 'units')}


@dataclass(frozen=True)
class JobLimits:
    max_concurrency: int = 1
    max_units: int = 32
    max_seconds: float = 30
    max_output_bytes: int = 65536

    def __post_init__(self):
        for name, maximum in (('max_concurrency', 16), ('max_units', 1000000), ('max_output_bytes', 16*1024*1024)):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError('Invalid shared job budget')
        if type(self.max_seconds) not in (int, float) or not math.isfinite(self.max_seconds) or not 0 < self.max_seconds <= 3600:
            raise ValueError('Invalid job deadline')


@dataclass(frozen=True)
class JobReport:
    identity_sha256: str
    outcomes: tuple
    values: dict
    reserved_units: int
    output_bytes: int

    @property
    def status(self):
        states = {entry['status'] for entry in self.outcomes}
        return next((state for state in ('canceled', 'failed', 'limited', 'blocked') if state in states), 'completed')

    def receipt(self):
        return {'identity_sha256': self.identity_sha256, 'status': self.status,
                'outcomes': [dict(entry) for entry in self.outcomes],
                'reserved_units': self.reserved_units, 'output_bytes': self.output_bytes}


def _waves(jobs, concurrency):
    pending = list(jobs)
    known = {job.id for job in jobs}
    if len(known) != len(jobs) or any(set(job.dependencies)-known for job in jobs):
        raise ValueError('Jobs need distinct IDs and known dependencies')
    done, result = set(), []
    while pending:
        wave, resources = [], set()
        for job in pending:
            if set(job.dependencies) <= done and job.resource not in resources and len(wave) < concurrency:
                wave.append(job)
                resources.add(job.resource)
        if not wave:
            raise ValueError('Job dependencies contain a cycle')
        result.append(tuple(wave))
        done.update(job.id for job in wave)
        pending = [job for job in pending if job not in wave]
    return tuple(result)


async def coordinate(jobs, *, run_id, config_sha256, limits=None, control=None,
                     checkpoint=None, retry=False, observer=None):
    """Execute selected callbacks with finite admission, no dynamic role loading.

    Jobs receive the same RunControl. Different resource IDs permit parallelism
    only when explicitly selected; the default model cache key serializes work.
    Checkpoints may hold private values. Retry after uncertain work is explicit.
    """
    from func_seq import Script
    _identifier(run_id)
    _sha(config_sha256)
    limits = limits if limits is not None else JobLimits()
    control = control if control is not None else RunControl()
    if type(limits) is not JobLimits or type(control) is not RunControl:
        raise TypeError('Use typed job budgets and control')
    jobs = tuple(jobs)
    if not 1 <= len(jobs) <= 128 or any(type(job) is not RoleJob for job in jobs):
        raise ValueError('Select between one and 128 typed jobs')
    waves = _waves(jobs, limits.max_concurrency)
    identity = digest({'jobs': [job.identity() for job in jobs], 'config': config_sha256, 'limits': asdict(limits)})
    script = Script(run_id, version=identity)
    deadline = time.monotonic()+limits.max_seconds

    def stage_for(wave):
        async def stage(previous):
            state = json.loads(json.dumps(previous))
            known = {entry['id']: entry['status'] for entry in state['outcomes']}
            admitted = []

            def record(job, status, code='', value=None, size=0):
                entry = {'id': job.id, 'role': job.role, 'status': status, 'code': code,
                         'source_sha256': job.source_sha256, 'output_sha256': digest(value) if status == 'completed' else None}
                state['outcomes'].append(entry)
                if status == 'completed':
                    state['values'][job.id] = value
                    state['output_bytes'] += size
                if observer is not None:
                    observer({'kind': 'job', **entry})

            for job in wave:
                if any(known.get(id) != 'completed' for id in job.dependencies):
                    record(job, 'blocked', 'dependency')
                elif control.canceled:
                    record(job, 'canceled')
                elif time.monotonic() >= deadline:
                    record(job, 'limited', 'time_budget')
                elif state['reserved_units']+job.units > limits.max_units:
                    record(job, 'limited', 'unit_budget')
                else:
                    state['reserved_units'] += job.units
                    admitted.append(job)

            async def execute(job):
                return await bounded_call(lambda: call_owned(job.function, control), control=control, seconds=deadline-time.monotonic())

            tasks = [asyncio.create_task(execute(job)) for job in admitted]
            try:
                results = await asyncio.gather(*tasks)
            except BaseException:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                raise
            # Admission-order accounting is deterministic even when jobs finish out of order.
            for job, (status, value, error) in zip(admitted, results):
                if status != 'completed':
                    record(job, status, 'job_error' if error else 'time_budget' if status == 'limited' else '')
                    continue
                try:
                    raw = json.dumps(value, allow_nan=False, ensure_ascii=True, sort_keys=True).encode()
                    digest(value)
                except (TypeError, ValueError, OverflowError):
                    record(job, 'failed', 'result_type')
                    continue
                if state['output_bytes']+len(raw) > limits.max_output_bytes:
                    record(job, 'limited', 'output_budget')
                else:
                    record(job, 'completed', value=value, size=len(raw))
            return state
        return stage

    prior = {'outcomes': [], 'values': {}, 'reserved_units': 0, 'output_bytes': 0}
    for index, wave in enumerate(waves):
        prior = script.add_function(stage_for(wave), prior, step_id=f'wave-{index+1}')
    completed = await script.arun(checkpoint=checkpoint, retry=retry)
    state = completed.results[script.step_ids[-1]]
    by_id = {entry['id']: entry for entry in state['outcomes']}
    return JobReport(identity, tuple(by_id[job.id] for job in jobs), state['values'], state['reserved_units'], state['output_bytes'])
