"""A bounded longer session over approved corpora and retained model families."""
import argparse
from datetime import datetime,timedelta,timezone
from importlib import metadata
import json
from pathlib import Path
import subprocess
import sys
import time
from zoneinfo import ZoneInfo


def write(path,value):
    path.write_text(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n')


def _run(corpus,destination,pilot_corpus,previous_pilot,*,budget=3600,smoke=False,resume=False):
    if type(budget) is not int or not 600<=budget<=3600: raise ValueError('Select a 10–60 minute session ceiling')
    from hypnosis.data import load_corpus
    from hypnosis.checkpoints import index_run,CheckpointCollection
    corpus=Path(corpus).resolve();destination=Path(destination).resolve()
    pilot_corpus=Path(pilot_corpus).resolve();previous_pilot=Path(previous_pilot).resolve()
    current,_documents=load_corpus(corpus);load_corpus(pilot_corpus)
    original=json.loads((previous_pilot/'hero/result.json').read_text())
    prior=None
    if destination.exists() and resume:
        prior=json.loads((destination/'session.json').read_text())
        if prior['corpus_sha256']!=current['sha256'] or prior['budget_seconds']!=budget or prior['fixture_smoke']!=smoke:
            raise ValueError('Session resume identity differs')
        if prior['status']=='completed':
            print(json.dumps({'status':'completed','reopened':True}),flush=True)
            return prior
    else: destination.mkdir(parents=False,exist_ok=False)
    collection_root=destination.parent;database=collection_root/'checkpoints.sqlite'
    for name in ('hero','hero-coding'):
        index_run(previous_pilot/name,database,collection_root)
    started=time.monotonic();deadline=started+budget;now=datetime.now(timezone.utc)
    schedule={'started_utc':now.isoformat(),'budget_seconds':budget,
        'scheduled_stop_pst':(now+timedelta(seconds=budget)).astimezone(ZoneInfo('America/Los_Angeles')).strftime('%Y-%m-%d %I:%M:%S %p %Z')}
    if prior is not None:
        elapsed=(now-datetime.fromisoformat(prior['started_utc'])).total_seconds()
        started-=elapsed;deadline=started+budget
        schedule={key:prior[key] for key in ('started_utc','budget_seconds','scheduled_stop_pst')}
        if deadline<=time.monotonic(): raise TimeoutError('Original session deadline has passed')
    summary={'schema':'hero-session/2',**schedule,'fixture_smoke':smoke,'corpus_sha256':current['sha256'],
        'corpus':{k:current[k] for k in ('documents','splits','bytes')},'runs':{},'status':'running',
        'software':{'python':sys.version.split()[0],'packages':{name:metadata.version(name) for name in
            ('hypnosis','thoughtform','thoughtformula','parse-md','engl','backpack-store','func-seq')}},
        'limits':['single seed','next-token loss and syntax do not prove factual or functional correctness',
                  'different tokenizer families are not directly compared','no automatic promotion or model-weight publication']}
    write(destination/'session.json',summary);print(json.dumps(schedule),flush=True)
    def execute(name,args,*,selected_corpus=None,settings=None,parent=None,continued=None):
        remaining=deadline-time.monotonic()
        if remaining<=1: raise TimeoutError('Session deadline reached')
        stdout=destination/(name+'.stdout.json');stderr=destination/(name+'.progress.jsonl')
        with stdout.open('w') as output,stderr.open('w') as errors:
            process=subprocess.run([sys.executable,'-u',*args],stdout=output,stderr=errors,timeout=remaining)
        write(destination/(name+'.exit.json'),{'returncode':process.returncode,
              'stdout_bytes':stdout.stat().st_size,'stderr_bytes':stderr.stat().st_size})
        if stdout.stat().st_size>1024*1024: raise ValueError('Child result exceeds its byte ceiling')
        try: value=json.loads(stdout.read_text())
        except json.JSONDecodeError:
            if selected_corpus is None: raise
            from hypnosis.pilot_results import collect_completed_job
            value=collect_completed_job(destination/name,selected_corpus,settings,parent_artifact=parent,
                continue_artifact=continued,timeout=max(0.1,deadline-time.monotonic()))
            write(destination/(name+'.recollected.json'),value)
        if process.returncode not in (0,1) or value.get('status') not in ('completed','limited'):
            raise RuntimeError(name+' failed; local diagnostics retained')
        return value
    def train(name,config,selected_corpus,*,parent=None,continued=None):
        settings=destination/(name+'.config.json')
        if settings.exists():
            original_settings=json.loads(settings.read_text())
            if any(original_settings.get(key)!=value for key,value in config.items() if key!='max_seconds'):
                raise ValueError('Existing phase settings differ')
            config=original_settings
        else: write(settings,config)
        args=['-m','hypnosis','train',str(selected_corpus),str(destination/name),str(settings)]
        if parent is not None: args+=['--parent-artifact',str(parent)]
        if continued is not None: args+=['--continue-artifact',str(continued)]
        print(json.dumps({'starting':name,'seconds':config['max_seconds'],'model':config['model_id']}),flush=True)
        report=execute(name,args,selected_corpus=selected_corpus,settings=settings,parent=parent,continued=continued)
        summary['runs'][name]=report
        summary['elapsed_seconds']=time.monotonic()-started
        summary['collection']=index_run(destination/name,database,collection_root)
        write(destination/'session.json',summary)
        print(json.dumps({'finished':name,'status':report['status'],'steps':report['training']['step']}),flush=True)
        return report
    try:
        probe_code='''from hypnosis.training import benchmark_job
import json,sys
print(json.dumps({'status':'completed',**benchmark_job(sys.argv[1],sys.argv[2],steps=3,profile='balanced-v2')}))
'''
        cache=destination/'probe.result.json'
        if cache.exists(): summary['probe']=json.loads(cache.read_text())
        else:
            summary['probe']=execute('probe',['-c',probe_code,str(corpus),str(destination/'probe')])
            write(cache,summary['probe'])
        baseline={**original['job'],'run_id':'hero-shuffle-session-v2','shuffle':True,'max_steps':original['training']['step'],
                  'max_seconds':min(480,budget*0.133)}
        shuffled=train('pilot-shuffle',baseline,pilot_corpus)
        summary['matched_pilot']={'matched':all((
            shuffled['training']['step']==original['training']['step'],
            shuffled['training']['selection']['pairs_sha256']==original['training']['selection']['pairs_sha256'],
            shuffled['training']['selection']['tokenizer_sha256']==original['training']['selection']['tokenizer_sha256'],
            shuffled['recipe_sha256']==original['recipe_sha256'],
            shuffled['before']==original['before'])),
            'original_checkpoint_sha256':original['training']['checkpoint_sha256'],
            'original_heldout':original['evaluation']['heldout'],'shuffled_heldout':shuffled['evaluation']['heldout']}
        write(destination/'session.json',summary)
        config={'profile':'balanced-v2','model_id':'hero','max_steps':2 if smoke else 100000,'max_seconds':30 if smoke else min(900,budget*0.25),
                'block_size':32,'learning_rate':0.0015,'seed':7,'shuffle':False,'max_sequences':8192,
                'evaluation_sequences':16,'checkpoint_interval':250}
        if smoke: config.update(block_size=4,max_sequences=20,evaluation_sequences=1,checkpoint_interval=1)
        train('hero-foundation',{**config,'run_id':'hero-foundation-v2'},corpus)
        train('hero-continued',{**config,'run_id':'hero-continued-v2'},corpus,
              continued=destination/'hero-foundation/artifact.json')
        train('hero-coding',{**config,'run_id':'hero-coding-v2','model_id':'hero-coding',
            'learning_rate':0.00075,'max_seconds':30 if smoke else max(1,min(1080,budget*0.30,deadline-time.monotonic()-40))},corpus,
            parent=destination/'hero-continued/artifact.json')
        summary['status']='completed'
    except (subprocess.TimeoutExpired,TimeoutError):
        summary['status']='limited';summary['reason']='combined session deadline'
    except Exception as error:
        summary['status']='failed';summary['error_type']=type(error).__name__
        raise
    finally:
        summary['elapsed_seconds']=time.monotonic()-started
        summary['finished_utc']=datetime.now(timezone.utc).isoformat()
        # Retain any complete snapshots even if a child did not reach registration.
        for name in ('pilot-shuffle','hero-foundation','hero-continued','hero-coding'):
            if (destination/name/'job.json').exists():
                try: index_run(destination/name,database,collection_root)
                except (ValueError,OSError) as error:
                    summary.setdefault('index_failures',[]).append({'run':name,'error_type':type(error).__name__})
        with CheckpointCollection(database,collection_root) as collection:
            summary['collection_page']=collection.page(limit=200)
        write(destination/'session.json',summary)
        print(json.dumps({'status':summary['status'],'elapsed_seconds':summary['elapsed_seconds'],
                          'checkpoint_records':len(summary['collection_page']['checkpoints'])}),flush=True)
    return summary


def run(corpus,destination,pilot_corpus,previous_pilot,*,budget=3600,smoke=False,resume=False):
    from func_seq import CheckpointStore
    path=Path(destination).resolve()
    # Reuse the workflow library's ownership contract, including stale-lock refusal.
    with CheckpointStore(path.with_name(path.name+'.session')).owned():
        return _run(corpus,destination,pilot_corpus,previous_pilot,budget=budget,smoke=smoke,resume=resume)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus');parser.add_argument('destination')
    parser.add_argument('--pilot-corpus',required=True);parser.add_argument('--previous-pilot',required=True)
    parser.add_argument('--budget',type=int,default=3600)
    parser.add_argument('--smoke',action='store_true',help='Exercise the same lifecycle with two-step fixture jobs.')
    parser.add_argument('--resume',action='store_true',help='Keep the original deadline; never retry uncertain training effects automatically.')
    options=parser.parse_args()
    result=run(options.corpus,options.destination,options.pilot_corpus,options.previous_pilot,budget=options.budget,smoke=options.smoke,resume=options.resume)
    if result['status']!='completed': raise SystemExit(1)
