# Hero session v2

The owner approved the current Python vault/tutorials, community wiki clone and
Python 3.14 documentation and delegated this session's progression in issue #27.
The implementation plan records the selected source/window weights and snapshots.
Raw source text, full source inventories and weights remain local.

The selected combined experiment ceiling is one hour:

1. Three-step larger-family probe.
2. Old 1,478-step shuffled baseline, bounded to eight minutes. Compare only when
   corpus/window/tokenizer/recipe/initial-evaluation identities match v1.
3. New balanced Hero foundation for fifteen minutes.
4. Exact Hero continuation for another fifteen minutes, preserving Adam and order.
5. Hero Coding specialization for up to eighteen minutes with a lower learning rate.

The remaining time covers checkpoint/evaluation/collection work. Every child has
the remaining hard combined deadline. Native jobs also stop at optimizer boundaries.
Schedule receipts include UTC and fixed-offset PST (UTC−08:00), independent of
the host's optional time-zone database.
Run the controller with an installed frozen `training` profile so development or
branch changes cannot alter a running session:

```sh
python experiments/hero-session-v2/run.py .corpora/selected .runs/hero-session-v2 \
  --pilot-corpus .corpora/hero-pilot-v1 --previous-pilot .runs/hero-pilot-20261120
```

An interrupted controller can use `--resume` after inspecting the saved phase and
native workflow state. It retains the original session deadline and phase settings;
it does not grant more runtime. A completed session reopens without training.
Controller ownership and uncertain native effects follow func_seq's lock/recovery
contract. An active or stale lock must be resolved by inspecting its owner before
recovery; there is no automatic replay of uncertain training effects. Exit receipts
retain child return codes and output sizes even when result delivery fails.

Periodic immutable snapshots and final sidecars enter `.runs/checkpoints.sqlite`.
Model/profile/tokenizer/recipe/corpus/parent/continuation identity stays explicit.
Per-job budgets are additional for continuation; reported cumulative counters
must not be added together as if they were independent training work.

Source quotas prevent starvation, and selected training characters define the
new family's frozen vocabulary. Code/general held-out losses and syntax probes
are separate measurements. Losses across tokenizer families are not directly
comparable. Single-seed results do not establish factual accuracy, functional
coding or autonomous training-agent ability; nothing is automatically promoted.

## Measurement export

`report.py` exports a finished local session through a closed set of aggregate
fields. It includes measured losses/coverage/denominators, actual source counts,
checkpoint hashes and frozen runtime identities. Private paths, source text,
selected document IDs, raw vocabulary and full inventories are excluded. The
output is a new file; an existing report is never overwritten.

```sh
python experiments/hero-session-v2/report.py \
  .runs/selected/session.json .runs/selected/runtime.json \
  .runs/selected/controller-recovery.json .runs/selected/controller.py \
  experiments/hero-session-v2/results-selected.json
```

The 21 November measured runtime is the installed wheel built from `e89bb00`,
with its exact dependency revisions recorded in the receipt. The archived
`controller-recovery-2026-11-21.patch`, applied to that commit's controller,
reconstructs the measured recovery controller SHA. Subsequent ownership/recovery
and portable time-display fixes do not change its training mathematics. The
matching wheel and controller are also retained in the local session directory.

Continuation source-window/token counts describe the cumulative native trajectory.
Per-job counters and the report's totals avoid counting the foundation twice.
`unique_windows` counts sampled document/window positions before deliberate
oversampling; it is not a claim that every encoded token sequence differs.
Collection record counts include intermediate/final aliases; the report also
counts unique native checkpoint hashes.
