from dataclasses import replace
import importlib.util
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

AVAILABLE=all(importlib.util.find_spec(name) for name in ('thoughtformula','thoughtform','backpack_store','func_seq'))


@unittest.skipUnless(AVAILABLE,'optional full training profile is not installed')
class CheckpointTests(unittest.TestCase):
    def fixture(self,root):
        from thoughtform.recipes import HERO
        from hypnosis.data import Source,DataLimits,prepare_corpus
        corpus=root/'corpus'
        prepare_corpus([Source('internal-v1','recipe')],corpus,limits=DataLimits(documents_per_source=80,max_documents=80))
        return corpus,replace(HERO,width=8,layers=1,heads=2,kv_heads=1,hidden=12,lora_rank=2)

    def test_retained_history_and_continuation_preserve_weights_adam_and_source(self):
        from hypnosis.training import JobConfig,run_job
        from thoughtform.artifacts import load_artifact
        from thoughtformula.pretraining import parameters
        from hypnosis.checkpoints import index_run,CheckpointCollection
        with TemporaryDirectory() as directory:
            root=Path(directory);corpus,recipe=self.fixture(root)
            config=JobConfig('first',profile='balanced-v2',max_steps=2,max_sequences=20,
                             block_size=4,evaluation_sequences=1,checkpoint_interval=1)
            first=run_job(corpus,root/'first',config,recipe=recipe)
            snapshots=sorted((root/'first/checkpoints').glob('step-*/artifact.json'))
            self.assertEqual(len(snapshots),2)
            original=(root/'first/model.tft').read_bytes()
            continued=run_job(corpus,root/'continued',replace(config,run_id='continued'),recipe=recipe,
                              continue_artifact=root/'first/artifact.json')
            self.assertEqual((continued['training']['step'],continued['training']['steps_this_job']),(4,2))
            self.assertEqual(original,(root/'first/model.tft').read_bytes())
            from_snapshot=run_job(corpus,root/'from-snapshot',replace(config,run_id='from-snapshot'),
                recipe=recipe,continue_artifact=snapshots[0])
            self.assertEqual(from_snapshot['training']['step'],3)
            continuous=run_job(corpus,root/'continuous',replace(config,run_id='continuous',max_steps=4),recipe=recipe)
            left=load_artifact(root/'continued/artifact.json');right=load_artifact(root/'continuous/artifact.json')
            for key,tensor in parameters(left.model).items():
                other=parameters(right.model)[key]
                self.assertEqual((tensor.data,tensor.m,tensor.v),(other.data,other.m,other.v),key)
            database=root/'collection.sqlite'
            self.assertEqual(index_run(root/'first',database,root)['added'],3)
            self.assertEqual(index_run(root/'first',database,root)['added'],0)
            index_run(root/'continued',database,root)
            with CheckpointCollection(database,root) as collection:
                records=collection.page(model_id='hero')['checkpoints']
                self.assertEqual(len(records),6)
                self.assertTrue(any(value['continued_from_sha256']==first['training']['checkpoint_sha256'] for value in records))
            subprocess.run([sys.executable,'-c',
                'from hypnosis.checkpoints import CheckpointCollection; import sys\nwith CheckpointCollection(sys.argv[1],sys.argv[2]) as c: assert len(c.page()["checkpoints"])==6',
                str(database),str(root)],check=True)

    def test_continuation_refuses_changed_order_and_history_budget_stops_safely(self):
        from unittest.mock import patch
        from hypnosis.training import JobConfig,run_job
        with TemporaryDirectory() as directory:
            root=Path(directory);corpus,recipe=self.fixture(root)
            config=JobConfig('first',profile='balanced-v2',max_steps=3,max_sequences=20,
                block_size=4,evaluation_sequences=1,checkpoint_interval=1)
            with patch('hypnosis.checkpoints.MAX_HISTORY',1):
                result=run_job(corpus,root/'first',config,recipe=recipe)
            self.assertEqual(result['status'],'limited');self.assertTrue(result['training']['history_limited'])
            self.assertEqual(len(list((root/'first/checkpoints').glob('step-*/artifact.json'))),1)
            from func_seq import StepFailedError
            with self.assertRaises(StepFailedError) as failed:
                run_job(corpus,root/'bad',replace(config,run_id='bad',seed=8),recipe=recipe,
                        continue_artifact=root/'first/artifact.json')
            self.assertIn('Continuation',str(failed.exception.__cause__) or str(failed.exception))
