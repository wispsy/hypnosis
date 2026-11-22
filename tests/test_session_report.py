import importlib.util
import json
from pathlib import Path
import unittest


class SessionReportTests(unittest.TestCase):
    def test_export_keeps_measurements_and_lineage_without_private_content(self):
        script=Path(__file__).resolve().parents[1]/'experiments/hero-session-v2/report.py'
        spec=importlib.util.spec_from_file_location('session_report',script)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        private='PRIVATE_TRAINING_TEXT_AND_PATH'
        metric={'status':'measured','loss':2.5,'tokens':16,'documents_unknown':1,
                'selected_ids':[private],'unknown_ids':[private],'selected_sources':{'internal-v1':1},'text':private}
        domains={'validation':metric,'test':metric}
        training={'step':4,'tokens':12,'steps_this_job':2,'tokens_this_job':6,'training_seconds_this_job':1,
            'continued_from_sha256':'c'*64,'selection':{'documents_available':5,'documents_unknown':0,'sequences':10,
            'selected_ids':[private],'unknown_ids':[private],'sources':{'internal-v1':{'windows':10,'text':private}}},
            'consumed_sources':{'windows':{'internal-v1':4},'tokens':{'internal-v1':12}},'raw':private}
        run={'status':'limited','job':{'model_id':'hero','max_steps':10,'private':private},
             'before':{**domains,'general_heldout':domains},'evaluation':{'heldout':domains,'general_heldout':domains,
             'syntax':{'attempted':1,'parsed':0,'generated':private}},'training':training,'private':private}
        checkpoint={'model_id':'hero','profile':'balanced-v2','checkpoint_sha256':'c'*64,
                    'steps':4,'tokens':12,'artifact_path':private,'private':private}
        session={'status':'completed','started_utc':'2026-11-22T02:00:00+00:00','budget_seconds':3600,
            'corpus':{'documents':20,'bytes':100,'splits':{'train':15,'validation':3,'test':2},'files':[private]},
            'runs':{'hero-continued':run},'matched_pilot':{'matched':True,'original_heldout':domains,'shuffled_heldout':domains},
            'collection_page':{'checkpoints':[checkpoint],'next_cursor':None},'private':private}
        runtime={'python':'3.14','code_commit':'c'*40,'private':private}
        recovery={'original_deadline_preserved':True,'probe_exit':{'returncode':0,'stdout_bytes':12,'private':private}}
        result=module.export_session(session,runtime,recovery,'c'*64)
        self.assertNotIn(private,json.dumps(result))
        published=result['runs']['hero-continued']
        self.assertEqual(published['before']['heldout']['test']['loss'],2.5)
        self.assertEqual(published['training']['steps_this_job'],2)
        self.assertEqual(published['training']['training_seconds_this_job'],1)
        self.assertEqual(published['training']['continued_from_sha256'],'c'*64)
        self.assertEqual(published['training']['consumed_sources']['tokens'],{'internal-v1':12})
        self.assertEqual(result['collection']['unique_native_checkpoints'],1)
        self.assertEqual(result['matched_pilot']['matched'],True)
        self.assertEqual(result['training_job_totals']['steps'],2)
        self.assertEqual(result['training_job_totals']['tokens'],6)
        with self.assertRaisesRegex(ValueError,'finished'):
            module.export_session({**session,'status':'running'},runtime,recovery,'c'*64)
