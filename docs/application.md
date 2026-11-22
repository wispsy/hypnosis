# Application composition

The `application` optional profile installs the selected library components.
`hypnosis application-demo` and `hypnosis app` call the same application services.
The first emits a single structural JSON receipt; the second runs one Carets
Program/TerminalSession with a shared AppShell/Theme and snapshot table controls.
Existing demo, terminal, preparation, training and checkpoint commands remain.

## Use

```sh
uv sync --extra application
uv run hypnosis application-demo --run-id experiment-1 --database local-receipts.db
uv run hypnosis app
```

The default exercise is explicitly offline and deterministic. It retrieves one
selected scratch document with an expected hash, invokes the selected `add`
capability, writes an initially wrong answer, inspects the actual saved bytes,
and repairs once. Baseline/candidate trials use disjoint validation and heldout
exercise identities. No corpus is selected or trained by this workflow.

The workbench displays jobs, tools, context classification/provenance, actual
verification attempts, trial gates, checkpoint metadata and private local output.
1–7 select sections; Tab changes focus; arrows/Page/Home/End navigate tables.
c cancels; q requests settlement and exit. Output/event tails are bounded and
control characters are displayed safely. p opens promotion review, starting on
Cancel. Tab to Confirm and Enter records a hash-checked decision; it does not
silently change the live configuration or weights. Each invocation owns one run.

`--database` explicitly selects structural Backpack persistence. Choose a new
run ID for a new headless experiment; conflicting writes under an existing run
are refused. `app` uses run ID `application` for its single session. Omit the
database for ephemeral experiments, or choose a separate database per session.
The checkpoint view reads at most 50 records from the existing collection when
both `--checkpoint-database` and `--checkpoint-root` are supplied. It does not
rewrite, delete, continue, promote or retrain a checkpoint.

## Native model probes

Install both `application` and `models`, then select `--artifact` and optionally
`--prompt`. Thoughtform validates the local artifact/checkpoint/tokenizer lineage;
there is no network model lookup. Generation runs through the existing owned
sync adapter, with at most 32 new tokens per call. Native verification parses a
nonempty Python candidate without execution. It may fail, and reports actual
syntax outcomes. This is not an instruction-following or functional-coding claim.
Shared model work stays sequential. A model artifact is never a dynamic plugin.

## Extend with trusted services

`ApplicationServices` accepts an explicit Workspace, ContextSource tuple,
selected Hidden Moves catalog, producer/verifier/repair callbacks, and optional
TrialCase/evaluator pairs. `run_application(plan, services, ...)` coordinates
retrieval, solving and measurement through existing func_seq stages. The caller
provides immutable task/provider source identities and a HarnessConfig. Domain
callbacks enforce their selected authority and artifact policy; retrieved text
never changes tool selection or imports a provider.

Hierarchical context/tool/candidate/trial allocations sum to the selected root
provider-output budget. The coordinator independently bounds structural output,
elapsed time and declared work units. Tool output is cumulative across calls;
uncertain tool effects stop automatic repair. Thread cancellation waits for owned
work to settle, so a native step cannot be forcibly interrupted. ProcessRun is
the separate owned-process transport when termination is needed.

Receipts contain identities, counts, hashes and structural outcomes. Private
prompts, file paths, retrieved bodies, candidate values/diffs and raw exception
messages stay out of default persistence and stdout. The private local output
pane is intentionally separate from the receipt. Linux/macOS native evidence
uses real pseudo-terminals and single-key cancellation/restoration. Windows
qualification is headless/synthetic; native console support remains unclaimed.
