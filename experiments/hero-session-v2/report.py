"""Export only the declared aggregate measurements from a completed local session."""
import argparse
from collections import Counter
from datetime import datetime,timedelta
import hashlib
import json
from pathlib import Path

METRICS=('status','loss','perplexity','coverage','documents_available','documents_representable',
         'documents_selected','documents_unknown','sequence_limit','sequences','tokens')
SELECTION=('profile','documents_available','documents_selected','documents_unknown','sequences',
           'pairs_sha256','tokenizer_sha256','tokenizer_fit_characters','selected_ids_sha256')
TRAINING=('status','step','tokens','elapsed_seconds','parameters','checkpoint_sha256','inference_sha256',
          'steps_this_job','tokens_this_job','training_seconds_this_job','continued_from_sha256','history_limited')
JOB=('profile','model_id','run_id','max_steps','max_seconds','block_size','learning_rate','seed',
     'shuffle','max_sequences','evaluation_sequences','checkpoint_interval')
IDENTITY=('schema','status','run_id','model_id','config_sha256','corpus_sha256','recipe_sha256',
          'parent_sha256','continued_from_sha256','wall_seconds_this_invocation')
SOURCES=('internal-v1','tinystories-train','tinystories-valid','simplewiki','wiktionary','ud-train',
         'ud-dev','ud-test','python-vault-tutorials','python-vault-reference','python314-docs','psf-wiki-python')
SOURCE_COUNTS=('weight','windows','unique_windows','documents_available','documents_representable','documents_unknown')
CHECKPOINT=('model_id','profile','checkpoint_sha256','config_sha256','corpus_sha256','recipe_sha256',
            'tokenizer_sha256','parent_sha256','continued_from_sha256','steps','tokens')


def pick(value,keys): return {key:value[key] for key in keys if key in value}


def counts(value): return {source:value[source] for source in SOURCES if source in value}


def heldout(value):
    result={}
    for split in ('validation','test'):
        if split in value:
            result[split]=pick(value[split],METRICS)
            result[split]['selected_sources']=counts(value[split].get('selected_sources',{}))
    return result


def evaluation(value):
    result={name:heldout(value[name]) for name in ('heldout','coding_heldout','general_heldout') if name in value}
    if 'syntax' in value:result['syntax']=pick(value['syntax'],('attempted','nonempty','parsed','failed'))
    return result


def run_report(value):
    result=pick(value,IDENTITY);result['job']=pick(value['job'],JOB)
    result['before']={'heldout':heldout(value['before'])}
    result['before'].update({key:heldout(value['before'][key]) for key in ('coding_heldout','general_heldout') if key in value['before']})
    result['evaluation']=evaluation(value['evaluation'])
    training=value['training'];public=pick(training,TRAINING)
    selection=training['selection'];public['selection']=pick(selection,SELECTION)
    public['selection']['sources']={source:pick(details,SOURCE_COUNTS) for source,details in
        selection.get('sources',{}).items() if source in SOURCES}
    # Legacy v1 selection has no per-source quotas; retain aggregate identities.
    if 'documents_selected' not in public['selection']:
        public['selection']['documents_selected']=len(selection.get('selected_ids',[]))
        public['selection']['documents_outside_window_pool']=selection['documents_available']-selection['documents_unknown']-public['selection']['documents_selected']
    consumed=training.get('consumed_sources')
    if consumed is not None:
        public['consumed_sources']={key:counts(consumed[key]) for key in ('windows','tokens') if key in consumed}
        public['consumed_sources_scope']='cumulative native optimizer trajectory'
        public['consumed_sources'].update(pick(consumed,('steps','tokens_total','start_step','end_step')))
    result['training']=public
    return result


def export_session(session,runtime,recovery,controller_sha256):
    if session['status'] not in ('completed','limited','failed'):raise ValueError('Only a finished session can be published')
    result=pick(session,('status','started_utc','finished_utc','budget_seconds','scheduled_stop_pst',
                         'elapsed_seconds','fixture_smoke','corpus_sha256'))
    result['schema']='hero-session-evidence/2'
    result['scheduled_stop_utc']=(datetime.fromisoformat(session['started_utc'])+timedelta(seconds=session['budget_seconds'])).isoformat()
    result['corpus']=pick(session['corpus'],('documents','bytes'))
    result['corpus']['splits']=pick(session['corpus']['splits'],('train','validation','test'))
    result['source_review']='https://github.com/wispsy/hypnosis/issues/27'
    result['execution_issue']='https://github.com/wispsy/hypnosis/issues/34'
    result['runtime']=pick(runtime,('python','wheel_sha256','code_commit','module_is_installed'))
    result['runtime']['controller_sha256']=controller_sha256
    packages=('hypnosis','thoughtform','thoughtformula','carets','expose-interface','engl','parse-md','func-seq','backpack-store')
    result['runtime']['sources']=pick(runtime.get('sources',{}),packages)
    result['runtime']['versions']=pick(runtime.get('versions',{}),packages)
    result['probe']=pick(session.get('probe',{}),('steps','seconds','step_seconds','parameters','vocabulary_size','recipe_sha256'))
    result['recovery']={'reason':'initial probe produced empty stdout; inspected bounded retry succeeded',
        'original_deadline_preserved':recovery['original_deadline_preserved'],
        'completed_training_stages_replayed':False,'root_cause':'not established',
        'probe_retry':pick(recovery['probe_exit'],('returncode','seconds','stdout_bytes','stderr_bytes'))}
    result['runs']={name:run_report(value) for name,value in session['runs'].items()
        if name in ('pilot-shuffle','hero-foundation','hero-continued','hero-coding')}
    training=[run['training'] for run in result['runs'].values()]
    result['training_job_totals']={'steps':sum(t.get('steps_this_job',t['step']) for t in training),
        'tokens':sum(t.get('tokens_this_job',t['tokens']) for t in training),
        'seconds':sum(t.get('training_seconds_this_job',t.get('elapsed_seconds',0)) for t in training),
        'scope':'reported session jobs only; excludes probes and prior preserved jobs'}
    matched=session.get('matched_pilot')
    if matched is not None:
        result['matched_pilot']=pick(matched,('matched','original_checkpoint_sha256'))
        result['matched_pilot'].update({name:heldout(matched[name]) for name in ('original_heldout','shuffled_heldout')})
    records=session['collection_page']['checkpoints']
    result['collection']={'records_in_page':len(records),'has_more':session['collection_page']['next_cursor'] is not None,
        'unique_native_checkpoints':len({r['checkpoint_sha256'] for r in records}),
        'by_model_profile':dict(sorted(Counter(r['model_id']+'/'+r['profile'] for r in records).items())),
        'checkpoints':[pick(r,CHECKPOINT) for r in records]}
    result['limitations']=['single seed and bounded text windows','training and held-out denominators differ',
        'tokenizer families are not directly compared','held-out loss is not factual accuracy',
        'syntax is parsed without execution and does not establish working code',
        'no autonomous training-agent qualification or automatic promotion',
        'native artifact weights, raw text, vocabulary and private inventories remain local']
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session');parser.add_argument('runtime');parser.add_argument('recovery')
    parser.add_argument('controller');parser.add_argument('destination')
    args=parser.parse_args()
    load=lambda name:json.loads(Path(name).read_text())
    value=export_session(load(args.session),load(args.runtime),load(args.recovery),
                         hashlib.sha256(Path(args.controller).read_bytes()).hexdigest())
    destination=Path(args.destination)
    with destination.open('x',encoding='utf-8') as stream:stream.write(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'status':'exported','runs':len(value['runs']),'checkpoint_records':value['collection']['records_in_page']}))
