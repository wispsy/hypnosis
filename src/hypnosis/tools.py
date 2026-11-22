"""Selected capability authority and owned, bounded tool-call outcomes."""
import asyncio
from contextlib import aclosing
from dataclasses import dataclass
import hashlib
import inspect
import json
import math
import time
from .execution import from_sync
from .records import _identifier
from .runtime import RunControl


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True,init=False)
class ToolRequest:
    id: str
    name: str
    arguments_json: str

    def __init__(self,id,name,arguments):
        from hidden_moves.core.schema import json_value
        _identifier(id)
        if type(name) is not str or not name or len(name)>256:raise ValueError('Use a bounded capability name')
        if type(arguments) is not dict:raise TypeError('Tool arguments require an object')
        value=json_value(arguments)
        raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)
        if len(raw.encode())>65536:raise ValueError('Tool arguments exceed the absolute input limit')
        object.__setattr__(self,'id',id);object.__setattr__(self,'name',name);object.__setattr__(self,'arguments_json',raw)

    @property
    def arguments(self):return json.loads(self.arguments_json)


@dataclass(frozen=True)
class ToolPolicy:
    allowed: tuple[str,...]
    max_calls: int = 32
    max_input_bytes: int = 16384
    max_output_bytes: int = 65536
    max_seconds: float = 30

    def __post_init__(self):
        if type(self.allowed) is not tuple or len(set(self.allowed))!=len(self.allowed) or len(self.allowed)>128 or any(type(n) is not str or not n or len(n)>256 for n in self.allowed):raise ValueError('Select explicit bounded distinct capability names')
        for value,maximum in ((self.max_calls,1000),(self.max_input_bytes,65536),(self.max_output_bytes,1024*1024)):
            if type(value) is not int or not 0<=value<=maximum:raise ValueError('Invalid tool budget')
        if type(self.max_seconds) not in (int,float) or not math.isfinite(self.max_seconds) or not 0<self.max_seconds<=3600:raise ValueError('Invalid time budget')


@dataclass(frozen=True)
class ToolOutcome:
    request_id: str
    name: str
    status: str
    code: str
    effect: str
    input_sha256: str
    output_sha256: str | None = None
    output_bytes: int = 0
    elapsed_seconds: float = 0
    value: object = None

    def receipt(self):
        return {key:getattr(self,key) for key in ('request_id','name','status','code','effect','input_sha256',
                'output_sha256','output_bytes','elapsed_seconds')}


class ToolExecutor:
    """One run's explicit authority. Catalog owns schemas, binding and dispatch.

    Async tools cooperate with cancellation. Synchronous tools run on an owned
    worker which is joined before returning, including after a deadline. A Python
    call cannot be forcibly killed; late/uncertain effects never authorize replay.
    """
    def __init__(self,catalog,policy):
        if type(policy) is not ToolPolicy:raise TypeError('Use ToolPolicy')
        selected={d.name for d in catalog.definitions()}
        if not set(policy.allowed)<=selected:raise ValueError('Authority exceeds the selected catalog')
        self.catalog,self.policy=catalog,policy;self.calls=0;self._started=None;self.last_receipt=None

    async def invoke(self,request,*,control=None):
        from hidden_moves.adapters.errors import CapabilityArgumentError,CapabilityResultError
        if type(request) is not ToolRequest:raise TypeError('Use ToolRequest')
        control=control if control is not None else RunControl()
        if type(control) is not RunControl:raise TypeError('Use RunControl')
        started=time.monotonic();input_sha=hashlib.sha256(request.arguments_json.encode()).hexdigest()
        def outcome(status,code='',effect='not_started',**values):
            value=ToolOutcome(request.id,request.name,status,code,effect,input_sha,
                              elapsed_seconds=time.monotonic()-started,**values)
            self.last_receipt=value.receipt();return value
        if request.name not in self.policy.allowed:return outcome('denied','unselected')
        if control.canceled:return outcome('canceled')
        if len(request.arguments_json.encode())>self.policy.max_input_bytes:return outcome('limited','input_budget')
        if self.calls>=self.policy.max_calls:return outcome('limited','call_budget')
        if self._started is None:self._started=started
        remaining=self.policy.max_seconds-(started-self._started)
        if remaining<=0:return outcome('limited','time_budget')
        definition=self.catalog.describe(request.name);self.calls+=1
        async def call():
            if definition.is_async:value=self.catalog.invoke(request.name,request.arguments)
            else:
                async with aclosing(from_sync(lambda:iter((self.catalog.invoke(request.name,request.arguments),)))) as source:
                    value=await anext(source)
            if inspect.isawaitable(value):value=await value
            return self.catalog.serialize_result(request.name,value)
        operation=asyncio.create_task(call());canceled=asyncio.create_task(control.wait())
        try:
            ready,_=await asyncio.wait((operation,canceled),timeout=remaining,return_when=asyncio.FIRST_COMPLETED)
            if canceled in ready or operation not in ready:
                operation.cancel();await asyncio.gather(operation,return_exceptions=True)
                return outcome('canceled' if canceled in ready else 'limited','' if canceled in ready else 'time_budget','uncertain')
            try:value=operation.result()
            except CapabilityArgumentError:return outcome('denied','arguments')
            except CapabilityResultError:return outcome('failed','result','uncertain')
            except Exception:return outcome('failed','call_error','uncertain')
            try:raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
            except (ValueError,TypeError,UnicodeError):return outcome('failed','result','uncertain')
            if len(raw)>self.policy.max_output_bytes:return outcome('limited','output_budget','completed',output_bytes=len(raw))
            return outcome('completed',effect='completed',output_sha256=hashlib.sha256(raw).hexdigest(),output_bytes=len(raw),value=value)
        except asyncio.CancelledError:
            operation.cancel();await asyncio.gather(operation,return_exceptions=True)
            outcome('canceled','task_cancellation','uncertain');raise
        finally:
            canceled.cancel();await asyncio.gather(canceled,return_exceptions=True)
