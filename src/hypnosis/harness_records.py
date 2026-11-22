"""Structural application/trial receipts using the existing Backpack engine."""
from dataclasses import dataclass
import json

from .records import _identifier, _sha
from .tools import digest


@dataclass(frozen=True)
class HarnessReceipt:
    run_id: str
    kind: str
    identity_sha256: str
    report_sha256: str
    summary_json: str

    def __post_init__(self):
        _identifier(self.run_id)
        _sha(self.identity_sha256)
        _sha(self.report_sha256)
        if self.kind not in ('trial', 'promotion', 'application') or type(self.summary_json) is not str or len(self.summary_json.encode()) > 1048576:
            raise ValueError('Invalid bounded harness receipt')
        value = json.loads(self.summary_json)
        if type(value) is not dict or digest(value) != self.report_sha256:
            raise ValueError('Receipt summary hash mismatch')


class HarnessLedger:
    def __init__(self, path):
        from backpack_store import Backpack, DataclassCodec
        self.store = Backpack.open(path)
        try:
            self.store.register(DataclassCodec(HarnessReceipt, type_key='hypnosis.harness', schema_version=1))
        except BaseException:
            self.store.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.store.close()

    def record_report(self, run_id, report):
        from .optimization import Promotion, TrialReport
        from .application import ApplicationReport
        kinds = {TrialReport: 'trial', Promotion: 'promotion', ApplicationReport: 'application'}
        if type(report) not in kinds:
            raise TypeError('Use a typed structural report')
        summary = report.receipt()
        receipt = HarnessReceipt(run_id, kinds[type(report)], report.identity_sha256, digest(summary),
                                 json.dumps(summary, sort_keys=True, separators=(',', ':'), allow_nan=False))
        tags = ['run:'+receipt.run_id, 'kind:'+receipt.kind]
        existing = self.store.find(HarnessReceipt, tags=tags, limit=2).records
        if existing:
            if len(existing) != 1 or existing[0].value != receipt:
                raise ValueError('Conflicting harness receipt for this run/kind')
            return existing[0].id
        return self.store.put(receipt, tags=tags).id

    def recall(self, run_id, *, kind='trial'):
        _identifier(run_id)
        if kind not in ('trial', 'promotion', 'application'):
            raise ValueError('Unknown receipt kind')
        return self.store.find(HarnessReceipt, tags=['run:'+run_id, 'kind:'+kind], limit=2).records
