from dataclasses import replace
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hypnosis.optimization import HarnessConfig, TrialCase, TrialLimits, search_configurations
from hypnosis.runtime import RunControl
from hypnosis.tools import digest
from hypnosis.verification import Candidate, Verification, verify_and_repair


class OptimizationTests(unittest.IsolatedAsyncioTestCase):
    async def trial(self, **kwargs):
        configs = (HarnessConfig('baseline'), HarnessConfig('overfit', repair_attempts=2), HarnessConfig('improved', repair_attempts=3))
        cases = (TrialCase('validation', 'validation', 'a'*64, 'c'*64), TrialCase('heldout', 'heldout', 'b'*64, 'd'*64))
        async def evaluate(config, case, control):
            passed = ((config.id != 'baseline') if case.split == 'validation' else config.id != 'overfit')
            return await verify_and_repair(lambda: Candidate('PRIVATE generated material'), lambda c: Verification(passed, 'fixture', digest(passed)), control=control)
        return await search_configurations(configs, cases, evaluate, provider_id='fixture-v1', provider_sha256='e'*64, task_sha256='f'*64, **kwargs)

    async def test_heldout_regression_gate_explicit_promotion_and_reproduction(self):
        report = await self.trial()
        self.assertEqual(report.recommendation, 'improved')
        self.assertFalse(report.trials[1]['eligible'])
        with self.assertRaises(ValueError):
            report.promote('overfit', expected_report_sha256=digest(report.receipt()))
        with self.assertRaises(ValueError):
            report.promote('improved', expected_report_sha256='0'*64)
        decision = report.promote('improved', expected_report_sha256=digest(report.receipt()))
        self.assertEqual(decision.config_id, 'improved')
        self.assertNotIn('PRIVATE', json.dumps(report.receipt()))
        repeated = await self.trial()
        self.assertEqual(repeated.identity_sha256, report.identity_sha256)
        self.assertEqual(repeated.recommendation, report.recommendation)
        self.assertEqual([t['validation_passed'] for t in repeated.trials], [t['validation_passed'] for t in report.trials])

    async def test_shared_budgets_cancel_and_narrated_scores_refused(self):
        report = await self.trial(limits=TrialLimits(max_evaluations=3))
        self.assertEqual((report.status, report.recommendation, report.evaluations), ('limited', None, 3))
        report = await self.trial(limits=TrialLimits(max_output_bytes=1))
        self.assertEqual((report.status, report.output_bytes), ('limited', 0))
        control = RunControl()
        control.cancel()
        report = await self.trial(control=control)
        self.assertEqual(report.status, 'canceled')
        cases = (TrialCase('v', 'validation', 'a'*64, 'c'*64), TrialCase('h', 'heldout', 'b'*64, 'd'*64))
        report = await search_configurations((HarnessConfig('baseline'),), cases, lambda *args: {'passed': True}, provider_id='fixture', provider_sha256='e'*64, task_sha256='f'*64)
        self.assertEqual(report.status, 'failed')
        with self.assertRaises(ValueError):
            await search_configurations((HarnessConfig('baseline'),), (cases[0], replace(cases[1], source_sha256='a'*64)), lambda *args: self.fail(), provider_id='fixture', provider_sha256='e'*64, task_sha256='f'*64)

    @unittest.skipUnless(importlib.util.find_spec('backpack_store'), 'records extra required')
    async def test_backpack_receipts_reopen_and_conflicts_are_refused(self):
        from hypnosis.harness_records import HarnessLedger
        report = await self.trial()
        with TemporaryDirectory() as temporary:
            path = Path(temporary)/'receipts.db'
            with HarnessLedger(path) as ledger:
                first = ledger.record_report('fixture', report)
                self.assertEqual(first, ledger.record_report('fixture', report))
            with HarnessLedger(path) as ledger:
                self.assertEqual(len(ledger.recall('fixture')), 1)
                self.assertNotIn('PRIVATE', ledger.recall('fixture')[0].value.summary_json)
                with self.assertRaises(ValueError):
                    ledger.record_report('fixture', replace(report, evaluations=1))
