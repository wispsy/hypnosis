"""Three bounded local experiments with a hard combined subprocess deadline."""
import argparse
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import subprocess
import sys
import time
from zoneinfo import ZoneInfo


def run(corpus,destination,*,budget=900):
    if type(budget) is not int or not 60<=budget<=900: raise ValueError('Pilot budget must be 60–900 seconds')
    destination=Path(destination);destination.mkdir(parents=False,exist_ok=False)
    corpus=Path(corpus).resolve()
    started=time.monotonic();deadline=started+budget
    now=datetime.now(timezone.utc);stop=now+timedelta(seconds=budget)
    schedule={'started_utc':now.isoformat(),'scheduled_stop_pst':stop.astimezone(ZoneInfo('America/Los_Angeles')).strftime('%Y-%m-%d %I:%M:%S %p %Z'),
              'budget_seconds':budget}
    (destination/'schedule.json').write_text(json.dumps(schedule,indent=2)+'\n')
    print(json.dumps(schedule),flush=True)
    def child(name,arguments):
        remaining=deadline-time.monotonic()
        if remaining<=1: raise TimeoutError('Combined pilot deadline reached')
        with (destination/(name+'.stdout.json')).open('w') as output, (destination/(name+'.progress.jsonl')).open('w') as errors:
            completed=subprocess.run([sys.executable,'-u',*arguments],stdout=output,stderr=errors,timeout=remaining)
        if completed.returncode not in (0,1): raise RuntimeError(name+' failed; inspect its local progress log')
        path=destination/(name+'.stdout.json')
        if path.stat().st_size>1024*1024: raise ValueError('Child result exceeds the byte ceiling')
        try: result=json.loads(path.read_text())
        except json.JSONDecodeError:
            if name=='probe': raise
            from hypnosis.pilot_results import collect_completed_job
            result=collect_completed_job(destination/name,corpus,destination/(name+'.config.json'),
                parent_artifact=destination/'hero/artifact.json' if name=='hero-coding' else None,
                timeout=max(0.1,deadline-time.monotonic()))
            (destination/(name+'.recollected.json')).write_text(json.dumps(result,sort_keys=True)+'\n')
            print(json.dumps({'recollected':name,'original_returncode':completed.returncode,
                              'original_stdout_bytes':path.stat().st_size}),flush=True)
        if result.get('status') not in ('completed','limited') and name!='probe': raise RuntimeError(name+' did not complete')
        return result
    probe_code='''import json,sys
from hypnosis.training import benchmark_job
print(json.dumps(benchmark_job(sys.argv[1],sys.argv[2]),allow_nan=False))
'''
    probe=child('probe',['-c',probe_code,str(corpus),str(destination/'probe')])
    # Identical Hero step budgets. Timing is measured on this exact corpus/vocab.
    hero_steps=min(1600,max(50,int(min(240,budget*0.26)/probe['step_seconds'])))
    coding_steps=min(1200,max(50,int(min(180,budget*0.20)/probe['step_seconds'])))
    reports={}
    for name,model,shuffle,steps,seconds in (
        ('hero','hero',False,hero_steps,min(300,budget*0.33)),
        ('hero-shuffle','hero',True,hero_steps,min(300,budget*0.33)),
        ('hero-coding','hero-coding',False,coding_steps,min(230,budget*0.25))):
        config={'run_id':name+'-pilot-v1','model_id':model,'max_steps':steps,'max_seconds':seconds,
                'block_size':32,'seed':7,'shuffle':shuffle,'max_sequences':2048,'evaluation_sequences':16,
                'checkpoint_interval':100}
        settings=destination/(name+'.config.json');settings.write_text(json.dumps(config,indent=2)+'\n')
        arguments=['-m','hypnosis','train',str(corpus),str(destination/name),str(settings)]
        if model=='hero-coding': arguments+=['--parent-artifact',str(destination/'hero/artifact.json')]
        print(json.dumps({'starting':name,'steps':steps,'seconds_ceiling':seconds}),flush=True)
        reports[name]=child(name,arguments)
        print(json.dumps({'finished':name,'steps':reports[name]['training']['step'],
                          'status':reports[name]['status']}),flush=True)
    left,right=reports['hero'],reports['hero-shuffle']
    matched=(left['training']['step']==right['training']['step']==hero_steps and
        left['training']['selection']['pairs_sha256']==right['training']['selection']['pairs_sha256'] and
        left['training']['selection']['tokenizer_sha256']==right['training']['selection']['tokenizer_sha256'])
    summary={'schema':'hero-pilot/1',**schedule,'elapsed_seconds':time.monotonic()-started,
        'probe':probe,'runs':reports,'comparison':{'matched_steps_data_tokenizer':matched,
            'initialization_seed':7,'single_seed':True,'selection_policy':'fixed source/family held-out strata'},
        'limitations':['small model and short run','single seed; no statistical significance estimate',
            'bounded corpus excerpts and held-out windows','loss and syntax do not establish factual or functional correctness',
            'no autonomous model-training agent qualification','no model weights or source text published']}
    (destination/'summary.json').write_text(json.dumps(summary,indent=2,sort_keys=True,allow_nan=False)+'\n')
    print(json.dumps({'status':'completed','elapsed_seconds':summary['elapsed_seconds'],
                      'matched_comparison':matched}),flush=True)
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus');parser.add_argument('destination')
    parser.add_argument('--budget',type=int,default=900)
    arguments=parser.parse_args()
    try: run(arguments.corpus,arguments.destination,budget=arguments.budget)
    except subprocess.TimeoutExpired:
        print(json.dumps({'status':'limited','reason':'combined-process-deadline'}),flush=True)
        raise SystemExit(1)
