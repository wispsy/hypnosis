"""Typed structural receipts over Backpack's existing local record store."""
from dataclasses import dataclass
import json
import re


def _identifier(value):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', value):
        raise ValueError('Use a bounded stable receipt identifier')


def _sha(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('Use a SHA-256 receipt reference')


@dataclass(frozen=True)
class TrainingReceipt:
    run_id: str
    model_id: str
    config_sha256: str
    corpus_sha256: str
    checkpoint_sha256: str
    parent_sha256: str | None
    status: str
    steps: int
    tokens: int

    def __post_init__(self):
        _identifier(self.run_id);_identifier(self.model_id)
        for name in ('config_sha256','corpus_sha256','checkpoint_sha256'):
            _sha(getattr(self,name))
        if self.parent_sha256 is not None: _sha(self.parent_sha256)
        if self.status not in ('completed','limited','paused','failed'):
            raise ValueError('Invalid training receipt status')
        if type(self.steps) is not int or not 0<=self.steps<=1000000 or type(self.tokens) is not int or not 0<=self.tokens<=256000000:
            raise ValueError('Invalid training receipt counters')


@dataclass(frozen=True)
class EvaluationReceipt:
    run_id: str
    checkpoint_sha256: str
    corpus_sha256: str
    metrics_json: str

    def __post_init__(self):
        _identifier(self.run_id);_sha(self.checkpoint_sha256);_sha(self.corpus_sha256)
        if type(self.metrics_json) is not str or len(self.metrics_json.encode())>32768:
            raise ValueError('Evaluation receipt exceeds its byte limit')
        value=json.loads(self.metrics_json, parse_constant=lambda _v: (_ for _ in ()).throw(ValueError('Nonfinite metric')))
        if type(value) is not dict: raise ValueError('Evaluation metrics require an object')


@dataclass(frozen=True)
class ArtifactReceipt:
    run_id: str
    model_id: str
    checkpoint_sha256: str
    tokenizer_sha256: str
    recipe_sha256: str

    def __post_init__(self):
        _identifier(self.run_id);_identifier(self.model_id)
        for name in ('checkpoint_sha256','tokenizer_sha256','recipe_sha256'): _sha(getattr(self,name))


class RunLedger:
    """One owned job writer; reopening explicitly registers only known codecs.

    Receipts contain references and measurements, never source text/transcripts.
    Matching repeated writes are idempotent for explicit workflow recovery;
    conflicting content under the same run/type is refused. A workflow lock
    serializes job writers; this class does not add a second storage engine.
    """
    def __init__(self, path):
        from backpack_store import Backpack, DataclassCodec
        self.store=Backpack.open(path)
        try:
            for model,key in ((TrainingReceipt,'hypnosis.training'),
                              (EvaluationReceipt,'hypnosis.evaluation'),
                              (ArtifactReceipt,'hypnosis.artifact')):
                self.store.register(DataclassCodec(model,type_key=key,schema_version=1))
        except BaseException:
            self.store.close();raise

    def __enter__(self): return self
    def __exit__(self,*_args): self.store.close()

    def record(self,value):
        if type(value) not in (TrainingReceipt,EvaluationReceipt,ArtifactReceipt):
            raise TypeError('Use a registered typed receipt')
        tag='run:'+value.run_id
        existing=self.store.find(type(value),tags=[tag],limit=2).records
        if existing:
            if len(existing)!=1 or existing[0].value!=value:
                raise ValueError('Run already has a different receipt of this type')
            return existing[0].id
        return self.store.put(value,tags=[tag]).id

    def recall(self,model,run_id):
        _identifier(run_id)
        return self.store.find(model,tags=['run:'+run_id],limit=2).records
