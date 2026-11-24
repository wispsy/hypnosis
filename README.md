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

Selected tools use Hidden Moves catalogs; context uses Workspace and Parse MD;
durable jobs use func_seq; records use Backpack; training stays in Thoughtformula.
Measured harness trials use actual verifier outcomes and a heldout regression
gate with explicit promotion. Ollama remains deferred. Importing the package
never activates providers, trains weights or downloads data.

## Harness workbench

```sh
uv sync --extra application
uv run hypnosis application-demo
uv run hypnosis app
uv run hypnosis stream --text 'Incremental process output.'
```

The application profile composes Carets 0.2.0's shared shell and typed snapshot
tables. The offline workflow retrieves a selected scratch document, calls an
explicit tool, verifies and repairs a saved artifact, and compares configurations
on validation/heldout cases. These are real service integrations using a small
deterministic exercise; they do not claim general autonomous problem solving.
`app` presents jobs, tools, context references, verification attempts, trials,
checkpoint metadata and private local output. Use 1–7 to change section, Tab to
change focus, arrows to navigate, c to cancel and q to quit. Press p to review a
promotion; the dialog defaults to Cancel and requires selecting Confirm.

Select `--database PATH` to retain structural receipts. Select both
`--checkpoint-database PATH --checkpoint-root PATH` to browse an existing
checkpoint collection read-only. With `--extra models` as well, `--artifact PATH`
loads an explicitly selected local Hero/Hero Coding sidecar for a bounded native
syntax probe. No generated Python is executed and syntax is not a functional
correctness test. No model weights change. See [application composition](docs/application.md),
[tools](docs/tools.md), [context](docs/context.md), [verification](docs/verification.md),
[trials](docs/optimization.md), [jobs](docs/orchestration.md) and
[process streams](docs/process-streams.md).

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

Source IDs are admitted by explicit reviewed catalogs. The internally generated
v1 pilot remains reproducible under [source review #13](https://github.com/wispsy/hypnosis/issues/13).
The later approved Python vault/tutorials, docs and wiki snapshots are tracked
under [source review #27](https://github.com/wispsy/hypnosis/issues/27); future
sources and recipe changes retain their own review. Fingerprints
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

## Homegrown training

Install the `training` extra to select the complete pinned component profile.
The default import and demo remain lightweight.

```sh
hypnosis prepare sources.json .corpora/pilot --documents-per-source 128
hypnosis train .corpora/pilot .runs/hero hero.json
hypnosis train-terminal .corpora/pilot .runs/hero-live hero-live.json
hypnosis train .corpora/pilot .runs/hero-coding coding.json \
  --parent-artifact .runs/hero/artifact.json
```

Create the parent `.corpora` and `.runs` directories explicitly. A source file is
a JSON list of approved `source_id`, local `path` and, for Wikipedia, `index`
selections. The approved generated source is `{"source_id":"internal-v1",
"path":"recipe"}`. New IDs remain rejected pending source review.

A job file is a closed JSON object such as:

```json
{"run_id":"hero-pilot","model_id":"hero","max_steps":1000,
 "max_seconds":240,"block_size":32,"seed":7,"shuffle":false}
```

Hero Coding selects `"model_id":"hero-coding"` and an explicit Hero sidecar.
It preserves parent weights/tokenizer as a starting point, resets Adam for its own
trajectory and selects only approved internal Python exercises. Hero uses the
selected training split; tokenizer fitting sees training material only, with a
predeclared printable ASCII alphabet. Unknown text exclusions are counted.
Curriculum and shuffle runs consume the same fixed document windows.

Each new destination binds corpus/source/config/recipe/parent identities.
func_seq owns prepare/train/evaluate/register progress, Thoughtformula owns
lossless `.tft` numerical state and `.mgpt` inference exports, Thoughtform owns
the passive sidecar, and Backpack holds structural receipts. `result.json`
contains before/after held-out measurements and explicit denominators. Weights,
source corpora and local job directories stay outside Git.

Carets shows the same worker's progress. `c` cancels cooperatively at an optimizer
boundary and saves `latest.tft`; `q` requests cancellation before exiting. Use
`--retry` explicitly after reviewing an interrupted workflow. Completed stages
are not replayed. Changed job identities and reused foreign destinations are
refused. A new specialization and exact numerical resume are separate operations.
Time limits are checked at step boundaries; the bounded pilot launcher also
applies a hard combined process deadline. These pilot artifacts are experimental.

Wikipedia citation names are scoped by reference group. Explicit conflicting
bodies retain their own spans/URLs; an empty reuse of an ambiguous name stays
unresolved. Reused long bodies inherit truncation metadata. Preserved citation
associations remain provenance, not a verdict that the reference supports a claim.

Approved Python material sources now include `python-vault-tutorials`,
`python-vault-reference`, `psf-wiki-python` and `python314-docs`. Their approval
is recorded in issue #27. `bind_source(Source(...))` returns a complete selected
snapshot fingerprint; put that fingerprint in the selected Source before corpus
preparation. Changed/added selected files are rejected. Markdown uses Parse MD
source spans and code blocks; documentation members stream from the text archive
without extraction. References and derivation remain attached, and related page
chunks share a held-out group. Alternate documentation formats are not duplicate
training samples. Downloaded examples are data and are never executed.

The `balanced-v2` job profile selects the named larger recipes and interleaves
weighted source/document windows. Every selected source receives a quota; small
original sets may be deliberately oversampled, with unique/repeated counts
recorded. Tokenizer merges use a bounded balanced training sample, and its
alphabet includes all selected training characters. Hero Coding inherits that
frozen vocabulary. Actual consumed source windows/tokens and separate coding/
general held-out measurements are reported. `pilot-v1` remains the default and
retains its original config, tokenizer and window identities for old jobs and
matched comparisons. Losses across different tokenizers are not directly comparable.

Balanced-v2 jobs retain immutable `checkpoints/step-.../model.tft` snapshots and
verified sidecars at the selected checkpoint interval. Latest recovery state is
separate. A job keeps at most 128 history snapshots and 512 MiB of native history;
reaching either ceiling saves a final limited result without deleting history.
Typed Backpack collections retain model/profile/tokenizer/data/parent/continuation
identities and support bounded pages:

```sh
hypnosis index-checkpoints .runs/my-run .runs/checkpoints.sqlite .runs
hypnosis checkpoints .runs/checkpoints.sqlite .runs --model-id hero --profile balanced-v2
hypnosis train .corpora/selected .runs/hero-next next.json \
  --continue-artifact .runs/my-run/artifact.json
```

Continuation preserves full weights, Adam and numerical order from a balanced-v2
checkpoint. It requires identical corpus, recipe, tokenizer, windows, learning
rate and ordering policy. Its step/time settings are additional budgets in a new
run directory; cumulative and per-job counters are both recorded. Specialization
uses `--parent-artifact` instead and resets Adam. These operations cannot be
combined. Every history/final context is passive data; no source code is loaded
from it. Index refresh is idempotent and does not train or mutate checkpoint bytes.


### MediaWiki excerpt profile

The optional `data` and `training` profiles use `parse-mw==0.1.0` for typed
MediaWiki syntax. Hypnosis retains citation policy: exact original character
spans, named/grouped reuse, ambiguous definitions and bounded evidence URLs.
A small reference-span adapter handles self-closing and grouped references
before parsing; no template expansion, URL retrieval or external parser runs.
Comments and unexpanded templates are omitted from plain excerpts, link labels
and literal regions remain text. Up to 128 citation records and 4,096 scanned
references are admitted per article; input is capped at 4 Mi characters and the
syntax tree at 100,000 nodes/64 levels. Nested/unclosed references or conflicting
name/group attributes refuse rather than inventing citation provenance.
