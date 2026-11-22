"""Finite verification/repair policy; success belongs to a selected verifier."""
from dataclasses import dataclass
import json
import math
import time
from .execution import bounded_call,call_owned
from .runtime import RunControl
from .tools import digest


@dataclass(frozen=True)
class RepairLimits:
    max_attempts: int = 3
    max_seconds: float = 30
    max_output_bytes: int = 65536

    def __post_init__(self):
        if type(self.max_attempts) is not int or not 1<=self.max_attempts<=32:raise ValueError('Invalid attempt limit')
        if type(self.max_output_bytes) is not int or not 0<=self.max_output_bytes<=16*1024*1024:raise ValueError('Invalid output budget')
        if type(self.max_seconds) not in (int,float) or not math.isfinite(self.max_seconds) or not 0<self.max_seconds<=3600:raise ValueError('Invalid verification time budget')


@dataclass(frozen=True)
class Candidate:
    value: object
    diff: str = ''
    uncertain_effects: bool = False
    tool_receipts: tuple = ()

    @property
    def has_uncertain_effects(self):
        return self.uncertain_effects or any(type(r) is dict and r.get("effect")=="uncertain" for r in self.tool_receipts)

    def __post_init__(self):
        if type(self.diff) is not str or type(self.uncertain_effects) is not bool or type(self.tool_receipts) is not tuple:raise TypeError('Invalid candidate fields')
        digest(self.value);digest(self.tool_receipts)


@dataclass(frozen=True)
class Verification:
    passed: bool
    code: str = ''
    evidence_sha256: str | None = None

    def __post_init__(self):
        from .records import _identifier,_sha
        if type(self.passed) is not bool:raise TypeError('Verifier pass must be an actual boolean')
        if self.code:_identifier(self.code)
        if self.evidence_sha256 is not None:_sha(self.evidence_sha256)


@dataclass(frozen=True)
class RepairReport:
    status: str
    code: str
    attempts: tuple
    candidate: Candidate | None
    output_bytes: int
    elapsed_seconds: float

    @property
    def passed(self):return self.status=='completed' and bool(self.attempts) and self.attempts[-1]['passed'] is True

    def receipt(self):
        return {'status':self.status,'code':self.code,'passed':self.passed,'attempts':[dict(a) for a in self.attempts],
                'output_bytes':self.output_bytes,'elapsed_seconds':self.elapsed_seconds}


def _candidate_receipt(candidate,number):
    return {'attempt':number,'candidate_sha256':digest(candidate.value),'diff_sha256':digest(candidate.diff),
            'diff_bytes':len(candidate.diff.encode()),'uncertain_effects':candidate.has_uncertain_effects,
            'tools_sha256':digest(candidate.tool_receipts),'tool_calls':len(candidate.tool_receipts),'passed':None}


async def verify_and_repair(produce,verify,*,repair=None,limits=None,control=None,observer=None):
    """Run trusted callbacks; never interpret model narration as verification.

    produce() and repair(candidate,verification,attempt) return Candidate. The
    selected verifier returns Verification after inspecting the real artifact.
    Diffs remain private/reviewable; receipts retain only hashes and counts.
    """
    limits=limits if limits is not None else RepairLimits();control=control if control is not None else RunControl()
    if type(limits) is not RepairLimits or type(control) is not RunControl:raise TypeError('Use typed verification limits/control')
    if any(not callable(f) for f in (produce,verify)) or (repair is not None and not callable(repair)):raise TypeError('Select trusted callbacks')
    started=time.monotonic();deadline=started+limits.max_seconds;attempts=[];candidate=None;output=0
    def finish(status,code=''):
        return RepairReport(status,code,tuple(attempts),candidate,output,time.monotonic()-started)
    async def invoke(function,*args):
        return await bounded_call(lambda:call_owned(function,*args),control=control,seconds=deadline-time.monotonic())
    verification=None
    for number in range(1,limits.max_attempts+1):
        status,value,error=await invoke(produce) if number==1 else await invoke(repair,candidate,verification,number)
        if status!='completed':return finish(status,'candidate_error' if error is not None else 'time_budget' if status=='limited' else '')
        if type(value) is not Candidate:return finish('failed','candidate_type')
        candidate=value
        encoded=json.dumps({'value':candidate.value,'diff':candidate.diff},ensure_ascii=True,allow_nan=False).encode()
        output+=len(encoded)
        if output>limits.max_output_bytes:return finish('limited','output_budget')
        entry=_candidate_receipt(candidate,number);attempts.append(entry)
        if observer is not None:observer({'kind':'candidate',**entry})
        if candidate.has_uncertain_effects:return finish('failed','uncertain_effects')
        status,value,error=await invoke(verify,candidate)
        if status!='completed':return finish(status,'verifier_error' if error is not None else 'time_budget' if status=='limited' else '')
        if type(value) is not Verification:return finish('failed','verifier_type')
        verification=value;entry.update(passed=verification.passed,verification_code=verification.code,
                                        evidence_sha256=verification.evidence_sha256)
        if observer is not None:observer({'kind':'verified',**entry})
        if verification.passed:return finish('completed')
        if repair is None:return finish('failed','verification_failed')
    return finish('limited','attempt_budget')
