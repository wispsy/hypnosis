"""Immutable checkpoint history and a typed Backpack collection index."""
from dataclasses import asdict,dataclass
from pathlib import Path,PurePosixPath

from .records import _identifier,_sha

MAX_HISTORY=128
MAX_HISTORY_BYTES=512*1024*1024


@dataclass(frozen=True)
class CheckpointReceipt:
    run_id: str
    model_id: str
    artifact_path: str
    checkpoint_sha256: str
    config_sha256: str
    corpus_sha256: str
    recipe_sha256: str
    tokenizer_sha256: str
    profile: str
    parent_sha256: str | None
    continued_from_sha256: str | None
    steps: int
    tokens: int

    def __post_init__(self):
        _identifier(self.run_id);_identifier(self.model_id)
        for key in ('checkpoint_sha256','config_sha256','corpus_sha256','recipe_sha256','tokenizer_sha256'): _sha(getattr(self,key))
        _identifier(self.profile)
        for key in ('parent_sha256','continued_from_sha256'):
            if getattr(self,key) is not None: _sha(getattr(self,key))
        path=PurePosixPath(self.artifact_path)
        if not self.artifact_path or len(self.artifact_path)>1024 or path.is_absolute() or '..' in path.parts or '\\' in self.artifact_path:
            raise ValueError('Checkpoint index uses a bounded root-relative artifact path')
        if type(self.steps) is not int or not 0<=self.steps<=1000000 or type(self.tokens) is not int or not 0<=self.tokens<=256000000:
            raise ValueError('Checkpoint counters exceed the native bounds')


class CheckpointCollection:
    """One explicitly opened local Backpack index; checkpoint bytes stay in files."""
    def __init__(self,database,root):
        from backpack_store import Backpack,DataclassCodec
        self.root=Path(root).resolve();self.store=Backpack.open(database)
        try: self.store.register(DataclassCodec(CheckpointReceipt,type_key='hypnosis.checkpoint',schema_version=1))
        except BaseException: self.store.close();raise

    def __enter__(self): return self
    def __exit__(self,*_args): self.store.close()

    def add(self,artifact,job):
        from thoughtform.artifacts import load_artifact
        from .training import _identity
        artifact=Path(artifact);relative=artifact.resolve().relative_to(self.root).as_posix()
        loaded=load_artifact(artifact);receipt=loaded.receipt
        identity=job['identity']
        if (receipt['corpus_sha256']!=identity['corpus_sha256'] or receipt['recipe_sha256']!=identity['recipe_sha256']):
            raise ValueError('Checkpoint identity differs from the selected job')
        value=CheckpointReceipt(run_id=job['config']['run_id'],model_id=receipt['model_id'],artifact_path=relative,
            checkpoint_sha256=receipt['checkpoint']['sha256'],config_sha256=identity['config_sha256'],
            corpus_sha256=receipt['corpus_sha256'],recipe_sha256=receipt['recipe_sha256'],
            tokenizer_sha256=receipt['tokenizer_sha256'],profile=job['config'].get('profile','pilot-v1'),
            parent_sha256=receipt['parent_sha256'],continued_from_sha256=job.get('continuation_sha256'),
            steps=loaded.state.step,tokens=loaded.state.tokens)
        tags=['run:'+value.run_id,'model:'+value.model_id,'profile:'+value.profile,'artifact:'+_identity(relative)]
        prior=self.store.find(CheckpointReceipt,tags=tags,limit=2).records
        if prior:
            if len(prior)!=1 or prior[0].value!=value: raise ValueError('Indexed checkpoint changed')
            return False
        self.store.put(value,tags=tags);return True

    def page(self,*,model_id=None,profile=None,limit=50,cursor=None):
        tags=[]
        if model_id is not None: _identifier(model_id);tags=['model:'+model_id]
        if profile is not None: _identifier(profile);tags.append('profile:'+profile)
        page=self.store.find(CheckpointReceipt,tags=tags,limit=limit,cursor=cursor)
        return {'checkpoints':[asdict(record.value) for record in page.records],'next_cursor':page.next_cursor}


def index_run(directory,database,root):
    """Rebuild/reconcile typed receipts from complete immutable artifact sidecars."""
    from .training import _read
    directory=Path(directory);job=_read(directory/'job.json')
    artifacts=sorted((directory/'checkpoints').glob('step-*/artifact.json'))
    if len(artifacts)>MAX_HISTORY: raise ValueError('Retained checkpoint count exceeds its bound')
    if (directory/'artifact.json').exists(): artifacts.append(directory/'artifact.json')
    added=0
    with CheckpointCollection(database,root) as collection:
        for artifact in artifacts: added+=collection.add(artifact,job)
    return {'status':'completed','artifacts':len(artifacts),'added':added}


def retain_checkpoint(job,model,tokenizer,numerical,state,metadata,selection):
    """Publish an immutable native snapshot; latest recovery state is separate."""
    from thoughtformula import save_training_checkpoint,load_training_checkpoint
    from thoughtform.artifacts import load_artifact,publish_artifact
    from .training import _read,_write
    history=job.directory/'checkpoints';history.mkdir(exist_ok=True)
    destination=history/f'step-{state.step:09d}'
    if not destination.exists():
        entries=list(history.glob('step-*'))
        size=sum(path.stat().st_size for path in history.glob('step-*/*.tft'))
        if len(entries)>=MAX_HISTORY or size+(job.directory/'latest.tft').stat().st_size+65536>MAX_HISTORY_BYTES:
            return False
        destination.mkdir()
    checkpoint=destination/'model.tft';artifact=destination/'artifact.json'
    if checkpoint.exists():
        _model,loaded_tokenizer,loaded_config,loaded_state,loaded_metadata=load_training_checkpoint(checkpoint)
        if loaded_state.step!=state.step or loaded_config!=numerical or loaded_metadata!=metadata or loaded_tokenizer.to_dict()!=tokenizer.to_dict():
            raise ValueError('Existing retained checkpoint has a different identity')
    else: save_training_checkpoint(checkpoint,model,tokenizer,numerical,state,metadata=metadata)
    if artifact.exists(): load_artifact(artifact)
    else: publish_artifact(artifact,checkpoint,job.recipe,corpus_sha256=job.corpus['sha256'],parent_sha256=job.parent_sha256)
    context=job.checkpoint_context(selection)
    path=destination/'context.json'
    if path.exists() and _read(path)!=context: raise ValueError('Retained checkpoint context changed')
    if not path.exists(): _write(path,context)
    with CheckpointCollection(job.directory/'history.sqlite',job.directory) as collection:
        collection.add(artifact,job.binding)
    return True
