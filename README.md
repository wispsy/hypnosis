# Hypnosis

Bounded harness execution, orchestration and a Carets terminal application.
Python 3.14+. Source development is tracked in
[Cohesion Block B](https://github.com/orgs/wispsy/projects/28).

```sh
uv sync
uv run hypnosis demo --text 'Hello from Hypnosis.'
uv run hypnosis terminal --text 'Live output in Carets.'
```

`demo` uses a deterministic offline source and prints one JSON result. `terminal`
opens a Carets application on a supported POSIX terminal: Enter starts the run,
`c` cancels and `q` quits. There is one Program/TerminalSession owner. The
application displays a bounded text tail, escapes terminal control characters,
handles resize and closes producers before terminal restoration. Interactive
output uses stderr so command results remain separate on stdout.

Ordinary Python can use `Harness.stream(factory, run_id=..., control=...)` with
an async text source. The default limits are 4,096 events (including started and
terminal), 65,536 UTF-8 output bytes and 30 seconds including consumer delay.
Outcomes distinguish completion, cooperative cancellation, source failure and
budget exhaustion. External consumer/task cancellation propagates; cleanup does
not fabricate a successful terminal event. Producer exceptions are reported by
structural codes rather than private exception text. A limit may consume one
extra source item to discover exhaustion; effects of that item are not rolled
back.

`hypnosis.execution.from_sync(factory)` moves synchronous iteration and closure
to one owned worker with one `next()` in flight. Cancellation waits for that
operation before closing on the worker. It cannot forcibly stop Python code or
guarantee a hard inference deadline. `model_text(adapter, prompt)` adapts a
configured Thoughtform `ThoughtformulaModel` using the same mechanism. Install
`uv sync --extra models` to run the actual tiny-model integration tests; callers
still supply compatible model/tokenizer instances and serialize shared model
access. No model/data download, training or inference starts on import.

Tools will reuse Hidden Moves catalogs; persistent workflows use Moveset,
func_seq and Scriptty; records use Backpack; HTTP providers use Requ/Apiconn;
training algorithms stay in Thoughtformula. The current offline vertical slice
does not yet implement autonomous tools, Ollama, persistent jobs, model training
or adaptive search. Their acceptance criteria are in the owning issues.

Verify with `PYTHONPATH=src python -m unittest discover -s tests`. CI builds and
checks wheel/source installations outside the checkout on Linux, macOS and
Windows, with and without the optional real-model profile. Native Windows
terminal interaction is not claimed by those headless checks.

See [the repository plan](IMPLEMENTATION_PLAN.md) and the
[complete family plan](https://github.com/wispsy/wispsy/blob/main/docs/cohesion-block-b/IMPLEMENTATION_PLAN.md).

## Approved homegrown training data

The optional `data` profile reads explicitly selected local TinyStories,
Wikipedia multistream bz2/index, Wiktextract and UD files. `hypnosis.data` exposes
bounded corpus preparation with source snapshots, grouped held-out splits,
deduplication, citation markers and reproducible corpus receipts. It never
extracts the full Wikipedia dump or fetches reference URLs.

Source IDs are admitted by the reviewed pilot catalog in
[source review #13](https://github.com/wispsy/hypnosis/issues/13). The internally
generated v1 pilot recipe is selected; the Python vault, Python docs/wiki and
other future sources require their own reviewed snapshots/recipes. Fingerprints
are labeled stat-plus-head/tail samples, not full-dump checksum verification.
Exact selected corpus/block hashes retain reproducibility. Keep corpus outputs
in caller-owned ignored local artifact directories.

The optional `records` profile uses Backpack Store directly. `RunLedger` persists
versioned `TrainingReceipt`, `EvaluationReceipt` and `ArtifactReceipt` values at
an explicit local SQLite path. Records hold identities and measurements, without
source text or transcripts. A repeated matching write is idempotent for workflow
recovery; a conflicting receipt is refused. One workflow owns the job writer.

The optional `workflow` profile composes explicit trusted prepare, train,
evaluate and register callables with func_seq. `WorkflowIdentity` binds corpus,
source selection, recipe and job configuration into its version. Its existing
checkpoint preserves completed stages and requires explicit retry/restart after
an uncertain interrupted effect. Native numerical checkpoints remain separate.

`evaluation.measure_split` retains explicit held-out split denominators and
reports unknown-token exclusions, selected records, sequence/token counts and
missing splits without substituting training examples. The Thoughtformula
adapter reports token-weighted next-token loss/perplexity. Bounded syntax probes
parse generated continuations without executing them. These measures do not
establish factual accuracy, working code or autonomous agent capability.
`hypnosis.curriculum.generated_documents` implements the explicitly approved
`wispsy-internal-curriculum/v1` pilot: exact addition/multiplication answers and
Python addition, even-number filtering and list-sum references. Seeds and recipe
hashes identify the generated material. Related arithmetic and Python variants
share a split group. Reference code is authored and independently checked;
model-generated code is never executed. New recipes and sources require review.
