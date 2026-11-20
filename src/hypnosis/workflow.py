"""Trusted training stages composed through func_seq's existing lifecycle."""
from dataclasses import asdict, dataclass
import hashlib
import json

from .records import _identifier, _sha


@dataclass(frozen=True)
class WorkflowIdentity:
    corpus_sha256: str
    recipe_sha256: str
    config_sha256: str
    sources_sha256: str
    profile: str = 'homegrown-v1'

    def __post_init__(self):
        for name in ('corpus_sha256','recipe_sha256','config_sha256','sources_sha256'):
            _sha(getattr(self,name))
        _identifier(self.profile)

    @property
    def version(self):
        return hashlib.sha256(json.dumps(asdict(self),sort_keys=True,separators=(',',':')).encode()).hexdigest()


def training_workflow(run_id, identity, *, prepare, train, evaluate, register):
    """Accept trusted callables, never callable names from serialized input.

    Call `.run(checkpoint=explicit_path, retry=True)` only after reviewing an
    uncertain failed/interrupted stage. func_seq persists completed results and
    refuses changed definitions. Numerical state is a separate native checkpoint.
    """
    from func_seq import Script
    _identifier(run_id)
    if type(identity) is not WorkflowIdentity: raise TypeError('Use WorkflowIdentity')
    script=Script(run_id,version=identity.version)
    prepared=script.add_function(prepare,step_id='prepare')
    trained=script.add_function(train,prepared,step_id='train')
    evaluated=script.add_function(evaluate,trained,step_id='evaluate')
    script.add_function(register,evaluated,step_id='register')
    return script
