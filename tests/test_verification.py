import asyncio
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from hypnosis.verification import Candidate,Verification,RepairLimits,verify_and_repair
from hypnosis.runtime import RunControl

class VerificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_failure_then_repair_preserves_diff_and_private_receipt(self):
        with TemporaryDirectory() as d:
            path=Path(d)/'result.txt'
            def produce():path.write_text('wrong');return Candidate({'narration':'passed!'},'PRIVATE initial diff')
            def verify(candidate):
                raw=path.read_bytes();return Verification(raw==b'correct','file_match',hashlib.sha256(raw).hexdigest())
            def repair(candidate,failure,attempt):
                self.assertFalse(failure.passed);path.write_text('correct');return Candidate({'artifact':'result'},'PRIVATE fixed diff')
            report=await verify_and_repair(produce,verify,repair=repair)
            self.assertTrue(report.passed);self.assertEqual(len(report.attempts),2)
            self.assertEqual(report.candidate.diff,'PRIVATE fixed diff')
            self.assertNotIn('PRIVATE',str(report.receipt()));self.assertEqual(path.read_text(),'correct')

    async def test_exhaustion_failure_uncertainty_and_wrong_verifier_type(self):
        false=lambda c:Verification(False,'failed')
        report=await verify_and_repair(lambda:Candidate('passed narration'),false,repair=lambda *a:Candidate('again'),limits=RepairLimits(max_attempts=2))
        self.assertEqual((report.status,report.code,len(report.attempts)),('limited','attempt_budget',2))
        def broken(c):raise RuntimeError('PRIVATE exception')
        report=await verify_and_repair(lambda:Candidate('x'),broken)
        self.assertEqual(report.code,'verifier_error');self.assertNotIn('PRIVATE',str(report.receipt()))
        report=await verify_and_repair(lambda:Candidate('x',uncertain_effects=True),false,repair=lambda *a:self.fail('must not replay'))
        self.assertEqual(report.code,'uncertain_effects')
        report=await verify_and_repair(lambda:Candidate('x',tool_receipts=({'effect':'uncertain'},)),false)
        self.assertEqual(report.code,'uncertain_effects')
        report=await verify_and_repair(lambda:Candidate('x'),lambda c:{'passed':True})
        self.assertFalse(report.passed);self.assertEqual(report.code,'verifier_type')

    async def test_budgets_cancel_and_direct_pass(self):
        report=await verify_and_repair(lambda:Candidate('ok'),lambda c:Verification(True))
        self.assertTrue(report.passed)
        async def slow():await asyncio.sleep(1);return Candidate('x')
        report=await verify_and_repair(slow,lambda c:Verification(True),limits=RepairLimits(max_seconds=.005))
        self.assertEqual(report.status,'limited')
        report=await verify_and_repair(lambda:Candidate('too large'),lambda c:self.fail(),limits=RepairLimits(max_output_bytes=1))
        self.assertEqual(report.code,'output_budget')
        control=RunControl();control.cancel()
        report=await verify_and_repair(lambda:self.fail(),lambda c:self.fail(),control=control)
        self.assertEqual(report.status,'canceled')
