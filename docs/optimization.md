# Measured harness trials

HarnessConfig selects finite context, explicit tool names, repair attempts and
workflow units. `search_configurations()` compares a baseline-first list through
a trusted evaluator that applies those settings. Each evaluation returns an
actual verifier-driven RepairReport; narrated scores are refused. The optimizer
calls no model training API. Weight training remains a separately configured job.

TrialCase carries immutable source and expected-result hashes with an explicit
validation or heldout split. Duplicate cases and overlapping source hashes across
splits are refused. One evaluation/time/output budget covers all configurations.
The identity hash binds cases, configurations, provider/task sources and limits.
Use the same trusted evaluator/source implementation to reproduce a selection;
runtime timing/evidence receipts can differ while the identity remains stable.

A candidate must complete every selected case and cannot lose any baseline
heldout pass. Ranking uses validation passes then heldout passes, keeping the
first configuration on ties. An incomplete search makes no recommendation.
Review counts and hashes, then explicitly call `report.promote(config_id,
expected_report_sha256=...)`. This returns a decision receipt; it changes no live
harness or weights. A heldout-regressing candidate cannot be promoted.

HarnessLedger stores typed structural trial/promotion/application receipts in
Backpack. It opens existing public codecs and adds no storage engine. Raw prompts,
source bodies, generated values, diffs and exception messages are omitted from
reports. Different content under the same run/kind is refused; identical writes
are idempotent. Training receipts and checkpoint formats are unchanged.
