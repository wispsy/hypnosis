import importlib.util
from datetime import datetime,timedelta
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

AVAILABLE=all(importlib.util.find_spec(name) for name in ('thoughtformula','thoughtform','backpack_store','func_seq','engl'))


@unittest.skipUnless(AVAILABLE,'optional training profile is not installed')
class SessionTests(unittest.TestCase):
    def test_real_short_session_collects_baseline_continuation_and_coding_artifacts(self):
        from hypnosis.data import Source,DataLimits,prepare_corpus
        from hypnosis.training import JobConfig,run_job
        script=Path(__file__).resolve().parents[1]/'experiments/hero-session-v2/run.py'
        with TemporaryDirectory() as directory:
            root=Path(directory);corpus=root/'corpus';previous=root/'previous';previous.mkdir()
            prepare_corpus([Source('internal-v1','recipe')],corpus,limits=DataLimits(documents_per_source=40,max_documents=40))
            settings=JobConfig('old-hero',max_steps=1,max_sequences=20,block_size=4,evaluation_sequences=1)
            run_job(corpus,previous/'hero',settings)
            from dataclasses import replace
            run_job(corpus,previous/'hero-coding',replace(settings,run_id='old-coding',model_id='hero-coding'),
                    parent_artifact=previous/'hero/artifact.json')
            completed=subprocess.run([sys.executable,str(script),str(corpus),str(root/'session'),
                '--pilot-corpus',str(corpus),'--previous-pilot',str(previous),'--budget','600','--smoke'],
                capture_output=True,text=True,timeout=90)
            self.assertEqual(completed.returncode,0,completed.stderr+'\n'+completed.stdout)
            result=json.loads((root/'session/session.json').read_text())
            self.assertTrue(result['fixture_smoke']);self.assertEqual(result['status'],'completed')
            scheduled=datetime.strptime(result['scheduled_stop_pst'],'%Y-%m-%d %I:%M:%S %p PST')
            utc=datetime.fromisoformat(result['scheduled_stop_utc']).replace(tzinfo=None,microsecond=0)
            self.assertEqual(utc-scheduled,timedelta(hours=8))
            self.assertTrue(result['matched_pilot']['matched'])
            self.assertEqual(result['runs']['hero-continued']['training']['step'],4)
            self.assertEqual(result['runs']['hero-coding']['training']['step'],2)
            self.assertEqual(len(result['collection_page']['checkpoints']),12)
            before=(root/'session/hero-continued/model.tft').read_bytes()
            reopened=subprocess.run([sys.executable,str(script),str(corpus),str(root/'session'),
                '--pilot-corpus',str(corpus),'--previous-pilot',str(previous),'--budget','600','--smoke','--resume'],
                capture_output=True,text=True,timeout=15)
            self.assertEqual(reopened.returncode,0,reopened.stderr)
            self.assertTrue(json.loads(reopened.stdout)['reopened'])
            self.assertEqual(before,(root/'session/hero-continued/model.tft').read_bytes())
