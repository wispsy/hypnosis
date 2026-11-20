from dataclasses import replace
import asyncio
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import subprocess
import sys
from threading import Event

AVAILABLE=all(importlib.util.find_spec(name) for name in ('thoughtformula','backpack_store','func_seq'))
if AVAILABLE:
    import thoughtformula
    AVAILABLE=hasattr(thoughtformula,'TrainingConfig')


@unittest.skipUnless(AVAILABLE,'optional training profile is not installed')
class TrainingJobTests(unittest.TestCase):
    def fixture(self,directory):
        from hypnosis.data import Source,DataLimits,prepare_corpus
        from thoughtform.recipes import HERO
        corpus=Path(directory)/'corpus'
        prepare_corpus([Source('internal-v1','recipe')],corpus,
            limits=DataLimits(documents_per_source=80,max_documents=80))
        recipe=replace(HERO,width=8,layers=1,heads=2,kv_heads=1,hidden=12,lora_rank=2)
        return corpus,recipe

    def test_parent_child_lineage_installed_receipts_and_no_stage_replay(self):
        from hypnosis.training import JobConfig,run_job
        from hypnosis.records import RunLedger,TrainingReceipt
        from thoughtform.artifacts import load_artifact
        with TemporaryDirectory() as directory:
            root=Path(directory);corpus,recipe=self.fixture(root)
            config=JobConfig('hero-fixture',max_steps=3,block_size=4,evaluation_sequences=1,max_seconds=30)
            events=[]
            result=run_job(corpus,root/'hero',config,recipe=recipe,observer=events.append)
            self.assertEqual(result['status'],'completed');self.assertEqual(result['training']['step'],3)
            count=len(events)
            self.assertEqual(run_job(corpus,root/'hero',config,recipe=recipe,observer=events.append),result)
            self.assertEqual(len(events),count)
            before=(root/'hero/model.tft').read_bytes()
            child=replace(recipe,model_id='hero-coding',role='coding',parent_model_id='hero')
            specialized=run_job(corpus,root/'coding',replace(config,run_id='coding-fixture',model_id='hero-coding',max_steps=2),
                recipe=child,parent_artifact=root/'hero/artifact.json')
            parent=load_artifact(root/'hero/artifact.json')
            self.assertEqual(specialized['parent_sha256'],parent.receipt['checkpoint']['sha256'])
            self.assertEqual(before,(root/'hero/model.tft').read_bytes())
            with RunLedger(root/'coding/receipts.sqlite') as ledger:
                self.assertEqual(ledger.recall(TrainingReceipt,'coding-fixture')[0].value.steps,2)

    def test_pause_requires_explicit_retry_and_retains_numerical_progress(self):
        from func_seq import RecoveryRequiredError
        from hypnosis.training import JobConfig,run_job
        from thoughtformula import load_training_checkpoint
        with TemporaryDirectory() as directory:
            root=Path(directory);corpus,recipe=self.fixture(root)
            config=JobConfig('resume-fixture',max_steps=30,block_size=4,evaluation_sequences=1,max_seconds=30)
            stop=Event()
            def observe(value):
                if value['kind']=='step' and value['step']==25: stop.set()
            paused=run_job(corpus,root/'run',config,recipe=recipe,stop=stop.is_set,observer=observe)
            self.assertEqual(paused['status'],'paused')
            self.assertEqual(load_training_checkpoint(root/'run/latest.tft')[3].step,25)
            with self.assertRaises(RecoveryRequiredError): run_job(corpus,root/'run',config,recipe=recipe)
            result=run_job(corpus,root/'run',config,recipe=recipe,retry=True)
            self.assertEqual(result['training']['step'],30)
            with self.assertRaises(ValueError): run_job(corpus,root/'run',replace(config,max_steps=4),recipe=recipe)

    def test_passive_job_file_rejects_unknown_code_and_unbounded_settings(self):
        from hypnosis.training import JobConfig,load_job
        with TemporaryDirectory() as directory:
            path=Path(directory)/'job.json';path.write_text(json.dumps({'run_id':'fixture','callable':'os:system'}))
            with self.assertRaises(TypeError): load_job(path)
        for settings in ({'max_seconds':901},{'max_steps':True},{'shuffle':1}):
            with self.assertRaises((ValueError,TypeError)): JobConfig('fixture',**settings)

    def test_real_training_progress_through_carets(self):
        from carets import KeyMsg
        from carets.testing import TestProgram
        from hypnosis.execution import job_progress
        from hypnosis.terminal import HarnessTerminal
        from hypnosis.training import JobConfig,run_job
        async def check(root,corpus,recipe):
            def job(emit,stop):
                return run_job(corpus,root/'terminal',JobConfig('terminal-fixture',max_steps=1,
                    block_size=4,evaluation_sequences=1,max_seconds=30),recipe=recipe,observer=emit,stop=stop)
            model=HarnessTerminal(lambda:job_progress(job))
            async with TestProgram(model) as app:
                model.program=app.program
                await app.send(KeyMsg('enter'))
                async def wait():
                    while model.status not in ('completed','failed'):
                        await asyncio.sleep(0.01)
                await asyncio.wait_for(wait(),10)
                self.assertEqual(model.status,'completed')
                self.assertIn('registered',model.output)
                await app.resize(22,5);app.assert_fits(22,5)
            self.assertTrue((root/'terminal/result.json').exists())
        with TemporaryDirectory() as directory:
            root=Path(directory);corpus,recipe=self.fixture(root)
            asyncio.run(check(root,corpus,recipe))

    def test_actual_prepare_and_train_commands_have_one_json_stdout_result(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);sources=root/'sources.json';settings=root/'config.json'
            sources.write_text(json.dumps([{'source_id':'internal-v1','path':'recipe'}]))
            settings.write_text(json.dumps({'run_id':'cli-fixture','max_steps':0,'evaluation_sequences':1}))
            command=[sys.executable,'-m','hypnosis']
            prepared=subprocess.run([*command,'prepare',str(sources),str(root/'corpus')],
                capture_output=True,text=True,timeout=30)
            self.assertEqual(prepared.returncode,0,prepared.stderr)
            self.assertEqual(json.loads(prepared.stdout)['status'],'completed')
            trained=subprocess.run([*command,'train',str(root/'corpus'),
                str(root/'run'),str(settings)],capture_output=True,text=True,timeout=30)
            self.assertEqual(trained.returncode,0,trained.stderr)
            self.assertEqual(json.loads(trained.stdout)['training']['step'],0)
            from hypnosis.pilot_results import collect_completed_job
            before=(root/'run/model.tft').read_bytes()
            report=collect_completed_job(root/'run',root/'corpus',settings)
            self.assertEqual(report,json.loads(trained.stdout))
            self.assertEqual(before,(root/'run/model.tft').read_bytes())
            # A durable report alone cannot authorize replay of uncertain effects.
            progress=root/'run/workflow.json';value=json.loads(progress.read_text())
            value['status']='paused';progress.write_text(json.dumps(value))
            with self.assertRaises(ValueError): collect_completed_job(root/'run',root/'corpus',settings)
