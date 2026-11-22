"""Bounded homegrown jobs: library computation, application policy and receipts."""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import string
from tempfile import NamedTemporaryFile
import time

from .data import load_corpus
from .evaluation import thoughtformula_metrics, syntax_probe
from .records import ArtifactReceipt, EvaluationReceipt, RunLedger, TrainingReceipt, _identifier
from .workflow import WorkflowIdentity, training_workflow


def _identity(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def _read(path, limit=1024*1024):
    with Path(path).open('rb') as stream: raw=stream.read(limit+1)
    if len(raw)>limit: raise ValueError('Job receipt exceeds its byte budget')
    def pairs(items):
        result={}
        for key,value in items:
            if key in result: raise ValueError('Duplicate job field')
            result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=pairs,
        parse_constant=lambda _v: (_ for _ in ()).throw(ValueError('Nonfinite job value')))


def _write(path,value):
    """Atomic replacement only within the explicitly owned job directory."""
    path=Path(path);temporary=None
    raw=json.dumps(value,sort_keys=True,indent=2,allow_nan=False).encode()+b'\n'
    if len(raw)>1024*1024: raise ValueError('Job receipt exceeds its byte budget')
    try:
        with NamedTemporaryFile(dir=path.parent,prefix='.receipt-',delete=False) as stream:
            temporary=Path(stream.name);stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if temporary is not None and temporary.exists(): temporary.unlink()


@dataclass(frozen=True)
class JobConfig:
    run_id: str
    model_id: str = 'hero'
    max_steps: int = 100
    max_seconds: float = 120
    block_size: int = 32
    learning_rate: float = 0.003
    seed: int = 7
    shuffle: bool = False
    max_sequences: int = 2048
    evaluation_sequences: int = 16
    checkpoint_interval: int = 100
    profile: str = 'pilot-v1'

    def __post_init__(self):
        _identifier(self.run_id)
        if self.profile not in ('pilot-v1','balanced-v2'): raise ValueError('Unknown training profile')
        if self.model_id not in ('hero','hero-coding'): raise ValueError('Select Hero or Hero Coding')
        for name,minimum,maximum in (('max_steps',0,10000 if self.profile=='pilot-v1' else 100000),('block_size',1,128),
            ('seed',0,2**32-1),('max_sequences',1,8192),('evaluation_sequences',1,64),
            ('checkpoint_interval',1,1000)):
            value=getattr(self,name)
            if type(value) is not int or not minimum<=value<=maximum: raise ValueError('Invalid finite job setting: '+name)
        for name,maximum in (('max_seconds',900 if self.profile=='pilot-v1' else 3600),('learning_rate',0.1)):
            value=getattr(self,name)
            if type(value) not in (int,float) or not math.isfinite(value) or not 0<value<=maximum:
                raise ValueError('Invalid finite job setting: '+name)
        if type(self.shuffle) is not bool: raise TypeError('Shuffle must be Boolean')


def job_settings(config):
    """Keep the existing pilot's passive config/identity byte-for-byte compatible."""
    value=asdict(config)
    if config.profile=='pilot-v1': value.pop('profile')
    return value


def load_job(path):
    """Read closed passive job settings, without reconstructing callables."""
    value=_read(path,65536)
    if type(value) is not dict: raise ValueError('Job settings require an object')
    return JobConfig(**value)


class TrainingPaused(RuntimeError):
    """A committed native checkpoint is available for explicitly retried recovery."""


class _Job:
    def __init__(self,corpus,directory,config,recipe,parent_artifact,observer,stop,continue_artifact=None):
        from thoughtform.artifacts import load_artifact
        self.corpus,self.documents=load_corpus(corpus)
        self.directory=Path(directory);self.config=config;self.recipe=recipe
        self.parent_artifact=parent_artifact;self.observer=observer;self.stop=stop
        self.continue_artifact=continue_artifact;self.continuation=None;self.continuation_sha256=None
        self.started=time.monotonic();self.parent_sha256=None;self.history_limited=False
        if continue_artifact is not None:
            if config.profile!='balanced-v2' or parent_artifact is not None:
                raise ValueError('Continuation requires balanced-v2 and a distinct explicit continuation artifact')
            self.continuation=load_artifact(continue_artifact)
            if self.continuation.recipe.sha256!=recipe.sha256 or self.continuation.receipt['corpus_sha256']!=self.corpus['sha256']:
                raise ValueError('Continuation must preserve selected corpus and model recipe')
            self.continuation_sha256=self.continuation.receipt['checkpoint']['sha256']
            self.parent_sha256=self.continuation.receipt['parent_sha256']
            self.continuation_context=_read(Path(continue_artifact).parent/'context.json')
        elif (config.model_id=='hero-coding')!=(parent_artifact is not None):
            raise ValueError('Hero Coding requires an explicitly selected Hero parent artifact')
        if parent_artifact is not None:
            parent=load_artifact(parent_artifact)
            if parent.recipe.model_id!=recipe.parent_model_id: raise ValueError('Parent identity differs from the recipe')
            self.parent_sha256=parent.receipt['checkpoint']['sha256']
        binding_identity={'job':job_settings(config),'recipe':recipe.sha256,
            'parent':self.parent_sha256,'corpus':self.corpus['sha256']}
        if self.continuation_sha256 is not None: binding_identity['continuation']=self.continuation_sha256
        self.config_sha256=_identity(binding_identity)
        self.identity=WorkflowIdentity(self.corpus['sha256'],recipe.sha256,self.config_sha256,
                                      _identity(self.corpus['sources']),
                                      profile='homegrown-v1' if config.profile=='pilot-v1' else 'homegrown-v2')
        self.binding={'schema':'hypnosis-job/1','identity':asdict(self.identity),'config':job_settings(config),
                      'recipe':asdict(recipe),'parent_sha256':self.parent_sha256}
        if self.continuation_sha256 is not None: self.binding['continuation_sha256']=self.continuation_sha256
        if self.directory.exists():
            if _read(self.directory/'job.json')!=self.binding: raise ValueError('Destination belongs to a different job')
        else:
            self.directory.mkdir(parents=False,exist_ok=False)
            _write(self.directory/'job.json',self.binding)

    def emit(self,kind,**values):
        if self.observer is not None: self.observer({'kind':kind,'run_id':self.config.run_id,**values})

    def training_documents(self):
        values=[value for value in self.documents if value['split']=='train']
        if self.config.model_id=='hero-coding':
            if self.config.profile=='balanced-v2':
                from .selection import is_coding
                values=[value for value in values if is_coding(value)]
            else:
                values=[value for value in values if value['source_id']=='internal-v1' and
                        value['provenance'].get('family','').startswith('python-')]
        # Fixed curriculum order. The shuffle baseline uses these exact pairs.
        difficulty={'tinystories-train':4,'ud-train':5,'wiktionary':6,'simplewiki':7,'enwiki':7}
        values.sort(key=lambda value:(value['provenance'].get('difficulty',difficulty.get(value['source_id'],8)),
                                      value['source_id'],value['id']))
        maximum=1024 if self.config.profile=='pilot-v1' else 16384
        if not values or len(values)>maximum: raise ValueError('Selected training document budget exceeded')
        return values

    def setup(self):
        from thoughtformula import BPETokenizer,TrainingConfig,token_sequences
        from thoughtform.artifacts import load_artifact
        if self.config.profile=='balanced-v2':
            if hasattr(self,'_prepared_selection'): return self._prepared_selection
            from .selection import prepare_selection
            parent_tokenizer=None
            if self.continuation is not None: parent_tokenizer=self.continuation.tokenizer
            elif self.parent_artifact is not None:
                parent=load_artifact(self.parent_artifact)
                if parent.receipt['checkpoint']['sha256']!=self.parent_sha256: raise ValueError('Selected parent changed')
                parent_tokenizer=parent.tokenizer
            tokenizer,pairs,selection,self.window_sources=prepare_selection(self.training_documents(),self.config,tokenizer=parent_tokenizer)
            initial=self.continuation.state if self.continuation is not None else None
            numerical=TrainingConfig(max_steps=self.config.max_steps+(initial.step if initial else 0),block_size=self.config.block_size,
                learning_rate=self.config.learning_rate,max_seconds=self.config.max_seconds+(initial.elapsed_seconds if initial else 0),
                seed=self.config.seed,shuffle=self.config.shuffle)
            if self.continuation is not None:
                expected=self.checkpoint_context(selection)
                for key in ('schema','profile','corpus_sha256','recipe_sha256','pairs_sha256','tokenizer_sha256','order'):
                    if self.continuation_context.get(key)!=expected[key]: raise ValueError('Continuation data/order identity changed: '+key)
                old=self.continuation.training_config
                if any(getattr(old,key)!=getattr(numerical,key) for key in ('block_size','learning_rate','seed','shuffle','lora_only')):
                    raise ValueError('Continuation must preserve its numerical optimizer policy')
            self._prepared_selection=(tokenizer,pairs,numerical,selection)
            return self._prepared_selection
        selected=self.training_documents();self.unknown_training=[]
        if self.parent_artifact is None:
            tokenizer=BPETokenizer()
            tokenizer.BASE_ALPHABET+=string.printable
            chunks=[];characters=0
            for value in selected:
                if characters+len(value['text'])>128*1024: break
                chunks.append(value['text']);characters+=len(value['text'])
            if not chunks: raise ValueError('No training text fits the tokenizer budget')
            tokenizer.train(tokenizer.EOS_TOKEN.join(chunks),max_merges=32)
        else:
            parent=load_artifact(self.parent_artifact)
            if parent.receipt['checkpoint']['sha256']!=self.parent_sha256:
                raise ValueError('Selected parent changed during job setup')
            tokenizer=parent.tokenizer
        pairs=[];included=[]
        for value in selected:
            try:
                encoded=token_sequences(tokenizer,[value['text']],block_size=self.config.block_size,
                    max_sequences=min(8192,self.config.max_sequences))
            except ValueError:
                self.unknown_training.append(value['id']);continue
            if len(pairs)<self.config.max_sequences:
                included.append(value['id']);pairs.extend(encoded[:self.config.max_sequences-len(pairs)])
        if not pairs: raise ValueError('No representable training windows')
        numerical=TrainingConfig(max_steps=self.config.max_steps,block_size=self.config.block_size,
            learning_rate=self.config.learning_rate,max_seconds=self.config.max_seconds,
            seed=self.config.seed,shuffle=self.config.shuffle)
        return tokenizer,tuple(pairs),numerical,{'selected_ids':included,
            'documents_available':len(selected),'documents_unknown':len(self.unknown_training),
            'unknown_ids':self.unknown_training[:64],'pairs_sha256':_identity(pairs),
            'sequences':len(pairs),'tokenizer_sha256':_identity(tokenizer.to_dict())}

    def checkpoint_context(self,selection):
        return {'schema':'hypnosis-checkpoint-context/1','profile':self.config.profile,
            'corpus_sha256':self.corpus['sha256'],'recipe_sha256':self.recipe.sha256,
            'pairs_sha256':selection['pairs_sha256'],'tokenizer_sha256':selection['tokenizer_sha256'],
            'order':{key:getattr(self.config,key) for key in ('block_size','learning_rate','seed','shuffle','max_sequences')},
            'run_id':self.config.run_id,'config_sha256':self.config_sha256,
            'continued_from_sha256':self.continuation_sha256}

    def prepare(self):
        _tokenizer,_pairs,_numerical,selection=self.setup()
        prepared={'config_sha256':self.config_sha256,**selection}
        path=self.directory/'prepared.json'
        if path.exists() and _read(path)!=prepared: raise ValueError('Prepared data identity changed')
        _write(path,prepared);self.emit('prepared',sequences=selection['sequences'])
        return {'config_sha256':self.config_sha256,'pairs_sha256':selection['pairs_sha256']}

    def metrics(self,model,tokenizer):
        measured=thoughtformula_metrics(model,tokenizer,self.documents,block_size=self.config.block_size,
                                       max_sequences=self.config.evaluation_sequences)
        if self.config.profile=='balanced-v2':
            from .selection import is_coding
            for name,selected in (('coding_heldout',[d for d in self.documents if is_coding(d)]),
                                  ('general_heldout',[d for d in self.documents if not is_coding(d)])):
                measured[name]=thoughtformula_metrics(model,tokenizer,selected,block_size=self.config.block_size,
                                                      max_sequences=self.config.evaluation_sequences)
        return measured

    def train(self,prepared):
        from thoughtformula import (TrainingState,fit,load_training_checkpoint,
            save_training_checkpoint,parameter_count,PurePythonBM25RAG)
        from thoughtform.artifacts import (artifact_metadata,checkpoint_identity,
            load_artifact,publish_artifact,specialize)
        from thoughtform.recipes import initialize
        tokenizer,pairs,numerical,selection=self.setup()
        if prepared!={'config_sha256':self.config_sha256,'pairs_sha256':selection['pairs_sha256']}:
            raise ValueError('Workflow data identity differs')
        metadata=artifact_metadata(self.recipe,self.corpus['sha256'],self.parent_sha256)
        latest=self.directory/'latest.tft';final=self.directory/'model.tft'
        existing=final if final.exists() else latest
        if existing.exists():
            model,loaded_tokenizer,loaded_config,state,loaded_metadata=load_training_checkpoint(existing)
            if loaded_config!=numerical or loaded_metadata!=metadata or loaded_tokenizer.to_dict()!=tokenizer.to_dict():
                raise ValueError('Native resume identity differs from the selected job')
        else:
            if self.continuation is not None:
                model=self.continuation.model;state=self.continuation.state
            elif self.parent_artifact is not None:
                model,tokenizer,parent_sha=specialize(self.parent_artifact,self.recipe)
                if parent_sha!=self.parent_sha256: raise ValueError('Parent artifact changed')
                state=TrainingState()
            else:
                model=initialize(self.recipe,tokenizer,seed=self.config.seed);state=TrainingState()
        before_path=self.directory/'before.json'
        if not before_path.exists():
            before=self.metrics(model,tokenizer)
            _write(before_path,before)
        def checkpoint(progress):
            if progress.step%self.config.checkpoint_interval==0:
                save_training_checkpoint(latest,model,tokenizer,numerical,progress,metadata=metadata,overwrite=True)
                if self.config.profile=='balanced-v2':
                    from .checkpoints import retain_checkpoint
                    self.history_limited=not retain_checkpoint(self,model,tokenizer,numerical,progress,metadata,selection)
        def observe(metric):
            if metric.step%25==0 or metric.step==numerical.max_steps:
                self.emit('step',**asdict(metric))
        expired=lambda:time.monotonic()-self.started>=self.config.max_seconds
        if not final.exists():
            result=fit(model,pairs,numerical,state=state,checkpoint=checkpoint,observer=observe,
                       stop=lambda:(self.stop is not None and self.stop()) or expired() or self.history_limited)
            state=result.state
            save_training_checkpoint(latest,model,tokenizer,numerical,state,metadata=metadata,overwrite=True)
            if result.status=='paused' and not expired() and not self.history_limited:
                if self.config.profile=='balanced-v2':
                    from .checkpoints import retain_checkpoint
                    retain_checkpoint(self,model,tokenizer,numerical,state,metadata,selection)
                self.emit('paused',step=state.step)
                raise TrainingPaused('Native state saved; retry this workflow explicitly to resume')
            save_training_checkpoint(final,model,tokenizer,numerical,state,metadata=metadata)
        status='completed' if state.step>=numerical.max_steps else 'limited'
        artifact_path=self.directory/'artifact.json'
        if artifact_path.exists(): artifact=load_artifact(artifact_path).receipt
        else:
            artifact=publish_artifact(artifact_path,final,self.recipe,corpus_sha256=self.corpus['sha256'],
                                      parent_sha256=self.parent_sha256)
        if artifact['checkpoint']['sha256']!=checkpoint_identity(final)[0]:
            raise ValueError('Published artifact differs from the completed native checkpoint')
        inference=self.directory/'model.mgpt'
        if not inference.exists(): model.save_checkpoint(str(inference),tokenizer,PurePythonBM25RAG(),[])
        summary={'status':status,'step':state.step,'tokens':state.tokens,'elapsed_seconds':state.elapsed_seconds,
                 'parameters':parameter_count(model),'selection':selection,
                 'checkpoint_sha256':artifact['checkpoint']['sha256'],
                 'inference_sha256':checkpoint_identity(inference)[0]}
        if self.config.profile=='balanced-v2':
            from .checkpoints import retain_checkpoint
            if latest.exists(): retain_checkpoint(self,model,tokenizer,numerical,state,metadata,selection)
            context=self.checkpoint_context(selection)
            context_path=self.directory/'context.json'
            if context_path.exists() and _read(context_path)!=context: raise ValueError('Final checkpoint context changed')
            if not context_path.exists(): _write(context_path,context)
            from .selection import consumed_windows
            consumed=consumed_windows(pairs,self.window_sources,state.step,shuffle=self.config.shuffle,seed=self.config.seed)
            if sum(consumed['tokens'].values())!=state.tokens: raise ValueError('Consumed-source token audit differs from native progress')
            summary['consumed_sources']=consumed
            initial=self.continuation.state if self.continuation is not None else TrainingState()
            summary.update(steps_this_job=state.step-initial.step,tokens_this_job=state.tokens-initial.tokens,
                training_seconds_this_job=state.elapsed_seconds-initial.elapsed_seconds,
                continued_from_sha256=self.continuation_sha256,history_limited=self.history_limited)
        _write(self.directory/'training.json',summary);self.emit('trained',step=state.step,status=status)
        return summary

    def evaluate(self,trained):
        from thoughtform.artifacts import load_artifact
        from thoughtform.contracts import GenerationConfig
        loaded=load_artifact(self.directory/'artifact.json')
        if loaded.receipt['checkpoint']['sha256']!=trained['checkpoint_sha256']:
            raise ValueError('Evaluation selects a different checkpoint')
        path=self.directory/'evaluation.json'
        if path.exists(): measured=_read(path)
        else:
            domains=self.metrics(loaded.model,loaded.tokenizer)
            measured={'heldout':{k:domains[k] for k in ('validation','test')},
                'syntax':syntax_probe(loaded.adapter(generation=GenerationConfig(max_new_tokens=32,temperature=0))),
                'claim':'small experimental next-token/syntax measurements only'}
            if self.config.profile=='balanced-v2':
                measured.update({key:domains[key] for key in ('coding_heldout','general_heldout')})
            _write(path,measured)
        return {'training':trained,'evaluation':measured}

    def register(self,evaluated):
        from thoughtform.artifacts import load_artifact
        artifact=load_artifact(self.directory/'artifact.json').receipt;trained=evaluated['training']
        checkpoint=artifact['checkpoint']['sha256']
        with RunLedger(self.directory/'receipts.sqlite') as ledger:
            ids=[ledger.record(TrainingReceipt(self.config.run_id,self.recipe.model_id,self.config_sha256,
                self.corpus['sha256'],checkpoint,self.parent_sha256,trained['status'],trained['step'],trained['tokens'])),
                ledger.record(EvaluationReceipt(self.config.run_id,checkpoint,self.corpus['sha256'],
                    json.dumps(evaluated['evaluation'],sort_keys=True,allow_nan=False))),
                ledger.record(ArtifactReceipt(self.config.run_id,self.recipe.model_id,checkpoint,
                    artifact['tokenizer_sha256'],self.recipe.sha256))]
        report={'schema':'hypnosis-training-result/1','status':trained['status'],'run_id':self.config.run_id,
            'model_id':self.recipe.model_id,'config_sha256':self.config_sha256,'corpus_sha256':self.corpus['sha256'],
            'parent_sha256':self.parent_sha256,'recipe_sha256':self.recipe.sha256,'job':job_settings(self.config),
            'before':_read(self.directory/'before.json'),**evaluated,'receipt_ids':ids,
            'wall_seconds_this_invocation':time.monotonic()-self.started}
        _write(self.directory/'result.json',report);self.emit('registered',status=trained['status'])
        if self.config.profile=='balanced-v2':
            from .checkpoints import index_run
            index_run(self.directory,self.directory/'history.sqlite',self.directory)
        return {'status':trained['status'],'checkpoint_sha256':checkpoint,'receipt_ids':ids}


def run_job(corpus,destination,config,*,parent_artifact=None,continue_artifact=None,recipe=None,retry=False,observer=None,stop=None):
    """Run/resume an explicit local job. Retry never means a fresh optimizer."""
    from thoughtform.recipes import HERO,HERO_CODING,ModelRecipe
    from func_seq import StepFailedError
    if type(config) is not JobConfig: raise TypeError('Use JobConfig')
    if recipe is None:
        if config.profile=='pilot-v1': recipe=HERO if config.model_id=='hero' else HERO_CODING
        else:
            from thoughtform.recipes import recipe_for
            recipe=recipe_for(config.model_id,config.profile)
    if type(recipe) is not ModelRecipe or recipe.model_id!=config.model_id: raise ValueError('Recipe/model identity differs')
    job=_Job(corpus,destination,config,recipe,parent_artifact,observer,stop,continue_artifact)
    script=training_workflow(config.run_id,job.identity,prepare=job.prepare,train=job.train,
                             evaluate=job.evaluate,register=job.register)
    try:
        result=script.run(checkpoint=job.directory/'workflow.json',retry=retry)
    except StepFailedError as error:
        if isinstance(error.__cause__,TrainingPaused):
            return {'schema':'hypnosis-training-result/1','status':'paused','run_id':config.run_id}
        raise
    if result.status!='completed': return {'status':str(result.status),'run_id':config.run_id}
    return _read(job.directory/'result.json')


def benchmark_job(corpus,destination,*,steps=5,profile='pilot-v1'):
    """Measure a tiny fresh-model sample using the exact job preparation policy."""
    from thoughtform.recipes import HERO,initialize,recipe_for
    from thoughtformula import fit,parameter_count
    if type(steps) is not int or not 1<=steps<=10: raise ValueError('Benchmark at most ten steps')
    recipe=recipe_for('hero',profile)
    job=_Job(corpus,destination,JobConfig('pilot-probe',max_steps=steps,max_seconds=20,profile=profile),
             recipe,None,None,None)
    tokenizer,pairs,config,selection=job.setup()
    model=initialize(recipe,tokenizer,seed=config.seed)
    result=fit(model,pairs,config)
    if result.state.step!=steps: raise ValueError('Benchmark did not complete within its bound')
    return {'steps':steps,'seconds':result.state.elapsed_seconds,
            'step_seconds':result.state.elapsed_seconds/steps,'parameters':parameter_count(model),
            'vocabulary_size':len(tokenizer.vocab),'selection':selection,'recipe_sha256':recipe.sha256}
