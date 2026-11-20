from dataclasses import replace
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from hypnosis.records import TrainingReceipt, RunLedger


@unittest.skipUnless(importlib.util.find_spec('backpack_store'),'optional records profile is not installed')
class RecordTests(unittest.TestCase):
    def test_fresh_process_reopens_typed_receipts_and_retry_is_idempotent(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'runs.sqlite'
            value=TrainingReceipt('fixture','hero','1'*64,'2'*64,'3'*64,None,'completed',4,32)
            with RunLedger(path) as ledger:
                identifier=ledger.record(value)
                self.assertEqual(ledger.record(value),identifier)
                with self.assertRaises(ValueError): ledger.record(replace(value,steps=5))
            code='''import sys
from hypnosis.records import RunLedger, TrainingReceipt
with RunLedger(sys.argv[1]) as ledger:
    records=ledger.recall(TrainingReceipt,'fixture')
    assert len(records)==1 and records[0].value.steps==4
    assert records[0].id==sys.argv[2]
'''
            subprocess.run([sys.executable,'-c',code,str(path),identifier],check=True,env=os.environ.copy())

    def test_nonfinite_or_unbounded_structural_receipts_are_refused(self):
        from hypnosis.records import EvaluationReceipt
        for raw in ('{"loss":NaN}', '[]', 'x'*32769):
            with self.assertRaises(ValueError): EvaluationReceipt('fixture','1'*64,'2'*64,raw)
