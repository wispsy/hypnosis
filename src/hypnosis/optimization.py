"""Finite harness configuration trials, held-out gates and explicit promotion."""
from dataclasses import asdict, dataclass
import math
import time

from .execution import bounded_call, call_owned
from .records import _identifier, _sha
from .runtime import RunControl
from .tools import digest
from .verification import RepairReport


@dataclass(frozen=True)
class HarnessConfig:
    id: str
    context_bytes: int = 8192
    tools: tuple[str, ...] = ()
    repair_attempts: int = 1
    workflow_units: int = 8

    def __post_init__(self):
        _identifier(self.id)
        if type(self.tools) is not tuple or len(self.tools) > 128 or len(set(self.tools)) != len(self.tools):
            raise ValueError('Select distinct explicit tools')
        for tool in self.tools:
            if type(tool) is not str or not tool or len(tool) > 256:
                raise ValueError('Invalid capability name')
        for value, low, high in ((self.context_bytes, 64, 1048576), (self.repair_attempts, 1, 32), (self.workflow_units, 1, 1000000)):
            if type(value) is not int or not low <= value <= high:
                raise ValueError('Invalid harness configuration')

    @property
    def sha256(self):
        return digest(asdict(self))


@dataclass(frozen=True)
class TrialCase:
    id: str
    split: str
    source_sha256: str
    expected_sha256: str

    def __post_init__(self):
        _identifier(self.id)
        _sha(self.source_sha256)
        _sha(self.expected_sha256)
        if self.split not in ('validation', 'heldout'):
            raise ValueError('Explicit validation/heldout cases required')


@dataclass(frozen=True)
class TrialLimits:
    max_trials: int = 8
    max_evaluations: int = 128
    max_seconds: float = 30
    max_output_bytes: int = 1048576

    def __post_init__(self):
        for name, maximum in (('max_trials', 32), ('max_evaluations', 4096), ('max_output_bytes', 16777216)):
            if type(getattr(self, name)) is not int or not 1 <= getattr(self, name) <= maximum:
                raise ValueError('Invalid finite trial budget')
        if type(self.max_seconds) not in (int, float) or not math.isfinite(self.max_seconds) or not 0 < self.max_seconds <= 3600:
            raise ValueError('Invalid trial deadline')


@dataclass(frozen=True)
class Promotion:
    identity_sha256: str
    report_sha256: str
    config_id: str
    config_sha256: str

    def receipt(self):
        return asdict(self)


@dataclass(frozen=True)
class TrialReport:
    identity_sha256: str
    status: str
    baseline: str
    trials: tuple
    recommendation: str | None
    evaluations: int
    output_bytes: int

    def receipt(self):
        return {'identity_sha256': self.identity_sha256, 'status': self.status, 'baseline': self.baseline,
                'trials': [{**trial, 'cases': [dict(case) for case in trial['cases']]} for trial in self.trials],
                'recommendation': self.recommendation, 'evaluations': self.evaluations, 'output_bytes': self.output_bytes}

    def promote(self, config_id, *, expected_report_sha256):
        """Return a reviewable decision only; never mutate a live harness or model."""
        if expected_report_sha256 != digest(self.receipt()):
            raise ValueError('Trial report changed since review')
        selected = next((trial for trial in self.trials if trial['config_id'] == config_id), None)
        if self.status != 'completed' or selected is None or not selected['eligible']:
            raise ValueError('Only a completed regression-qualified configuration may be promoted')
        return Promotion(self.identity_sha256, expected_report_sha256, config_id, selected['config_sha256'])


async def search_configurations(configurations, cases, evaluate, *, provider_id, provider_sha256,
                                task_sha256, limits=None, control=None, observer=None):
    """Measure trusted evaluators; no weight-training API is called here.

    The first configuration is baseline. Every evaluation must return the real
    verifier-driven RepairReport; narrated scores and dictionaries are refused.
    Evaluators must enforce each configuration's selected authority and limits.
    """
    _identifier(provider_id)
    _sha(provider_sha256)
    _sha(task_sha256)
    limits = limits if limits is not None else TrialLimits()
    control = control if control is not None else RunControl()
    if type(limits) is not TrialLimits or type(control) is not RunControl or not callable(evaluate):
        raise TypeError('Use typed trial limits/control and a trusted evaluator')
    configurations, cases = tuple(configurations), tuple(cases)
    if not 1 <= len(configurations) <= limits.max_trials or any(type(c) is not HarnessConfig for c in configurations) or len({c.id for c in configurations}) != len(configurations):
        raise ValueError('Select a bounded distinct configuration list, baseline first')
    if not 2 <= len(cases) <= 128 or any(type(c) is not TrialCase for c in cases) or len({c.id for c in cases}) != len(cases) or {c.split for c in cases} != {'validation', 'heldout'}:
        raise ValueError('Select distinct cases with both validation and heldout splits')
    # Identical immutable materials must not leak between the two splits.
    if {c.source_sha256 for c in cases if c.split == 'validation'} & {c.source_sha256 for c in cases if c.split == 'heldout'}:
        raise ValueError('Validation and heldout sources overlap')
    identity = digest({'configs': [asdict(c) for c in configurations], 'cases': [asdict(c) for c in cases],
                       'provider_id': provider_id, 'provider_sha256': provider_sha256,
                       'task_sha256': task_sha256, 'limits': asdict(limits)})
    trials, evaluations, output = [], 0, 0
    deadline = time.monotonic()+limits.max_seconds
    status = 'completed'
    for config in configurations:
        measured = []
        for case in cases:
            if evaluations >= limits.max_evaluations:
                status = 'limited'
                break
            state, result, error = await bounded_call(lambda: call_owned(evaluate, config, case, control),
                                                     control=control, seconds=deadline-time.monotonic())
            if state != 'completed':
                status = state
                break
            evaluations += 1
            if type(result) is not RepairReport:
                status = 'failed'
                break
            if output+result.output_bytes > limits.max_output_bytes:
                status = 'limited'
                break
            output += result.output_bytes
            measured.append({'case_id': case.id, 'split': case.split, 'passed': result.passed,
                             'status': result.status, 'code': result.code,
                             'source_sha256': case.source_sha256, 'expected_sha256': case.expected_sha256,
                             'evidence_sha256': digest(result.receipt())})
            if observer is not None:
                observer({'kind': 'evaluation', 'config_id': config.id, **measured[-1]})
        complete = len(measured) == len(cases)
        baseline = {c['case_id']: c['passed'] for c in trials[0]['cases']} if trials else {}
        regression = complete and any(baseline.get(c['case_id']) and not c['passed'] for c in measured if c['split'] == 'heldout')
        trials.append({'config_id': config.id, 'config_sha256': config.sha256, 'complete': complete,
                       'eligible': complete and not regression,
                       'validation_passed': sum(c['passed'] for c in measured if c['split'] == 'validation'),
                       'heldout_passed': sum(c['passed'] for c in measured if c['split'] == 'heldout'),
                       'cases': measured})
        if not complete:
            break
    eligible = [trial for trial in trials if trial['eligible']]
    selected = max(eligible, key=lambda t: (t['validation_passed'], t['heldout_passed'])) if eligible and status == 'completed' else None
    return TrialReport(identity, status, configurations[0].id, tuple(trials),
                       selected['config_id'] if selected else None, evaluations, output)
