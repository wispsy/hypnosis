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

## Observed 21 November 2026 session

The [sanitized measurement receipt](results-2026-11-21.json) records the frozen
runtime, source/corpus identities, measured denominators and checkpoint hashes.
The combined session finished with status `completed` in 3521.7 seconds
against its original one-hour wall-clock ceiling. Individual longer jobs stop
with `limited` status at their selected time boundaries; their final native
artifacts and evaluations are retained. Diagnostic/recovery time is included.

### New model family

The larger family has 240,355 parameters and an 837-token vocabulary.
Initial Hero mixed validation/test loss was 6.99305 / 6.89705. All nine selected
Hero source families received actual training windows. Training character
exclusions are zero; held-out exclusions/coverage and token counts are explicit
in the receipt. Each loss uses a fixed selection of at most sixteen windows.

| Phase | Additional steps | Additional tokens | Native training seconds | Mixed validation loss | Mixed test loss | Coding test loss | General test loss |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| hero-foundation | 2,123 | 62,765 | 867.7 | 2.54686 | 2.55696 | 2.43069 | 3.00382 |
| hero-continued | 2,105 | 63,833 | 873.8 | 2.39658 | 2.35761 | 2.22103 | 2.71329 |
| hero-coding | 2,474 | 76,133 | 1058.9 | 2.35747 | 2.06115 | 1.69076 | 3.06745 |

Continued Hero retains **4,228 cumulative steps and 126,598 cumulative tokens**.
The second row reports only its additional work. Complete native weights, Adam
and order state continue into a separate destination; the foundation remains
available. Hero Coding starts a new specialization optimizer from continued Hero.

Coding specialization changes the fixed general test loss from 2.71329 to 3.06745.
The generalist and coding checkpoints remain separate candidates; no model
is automatically promoted or substituted for another.

Syntax probes are parsed without execution:

- hero-foundation: 0 parsed / 1 attempted; 1 nonempty.
- hero-continued: 0 parsed / 1 attempted; 1 nonempty.
- hero-coding: 0 parsed / 1 attempted; 1 nonempty.

These single-seed text-window and syntax measurements do not establish factual
accuracy, working generated code, useful assistant behavior or autonomous
operation of the harness. New-family losses are not compared numerically with
the smaller v1 tokenizer family.

### Matched v1 shuffle follow-up

The comparison matches the available window pool, tokenizer, recipe, initial
evaluation and **1,478 steps**. Consumed ordering and token totals differ:
44,662 tokens in the original ordered run and 45,233 in the shuffled run.
This is a step-matched comparison, not a token-matched comparison.

| Ordering | Validation loss | Test loss |
| --- | ---: | ---: |
| Original ordered | 4.17054 | 4.37284 |
| Shuffled | 2.32032 | 2.60326 |

Shuffling performed better in this bounded old-family experiment. No ordered
curriculum advantage or general capability claim follows from it. The larger
family uses its separately selected source-interleaved order.

### Retained collection and provenance

The shared collection contains **34 artifact records representing 31 unique native checkpoint hashes**.
Intermediate/final aliases can reference the same native bytes. Records include
the preserved v1 models, matched shuffle follow-up and newly retained v2 history.
Model/profile, recipe, tokenizer, corpus, parent and continuation identities remain
queryable. Native `.tft` training state is distinct from quantized `.mgpt` inference.
Local snapshots, the shared Backpack index, frozen wheel and controller are retained;
source text, raw vocabulary, full inventories and weights are not published.

The initial probe returned empty stdout. An inspected, bounded repeat succeeded,
and controller recovery kept the original deadline. The cause of the empty output
is not established; no completed training stage was replayed. The receipt records
the measured runtime wheel/source/controller hashes and exact dependency revisions.
The archived recovery patch reproduces the measured controller from `e89bb00`.

No full Wikipedia extraction or external-drive expansion was needed. Future
training uses another explicitly bounded progression and owner-selected material;
changed data/tokenizers require explicit lineage rather than exact-continuation claims.
