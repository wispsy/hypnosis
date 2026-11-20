# Hypnosis implementation plan

Hypnosis owns harness execution policy, context/tools, verification, experiment
management, training orchestration and measured harness optimization. Its first
user interface is a Carets application. The
[complete Cohesion Block B plan](https://github.com/wispsy/wispsy/blob/main/docs/cohesion-block-b/IMPLEMENTATION_PLAN.md)
contains the architecture, reuse register, full cross-project acceptance and
staged milestones. [Project 28](https://github.com/orgs/wispsy/projects/28) and
[owning issues](https://github.com/wispsy/hypnosis/issues) hold current execution state.

## First vertical slice — HYP-01

Build a finite invocation-owned event lifecycle over explicitly supplied async
text producers. Each run has identity, increasing event sequences and bounded
UTF-8 output, event count and elapsed time. Normal outcomes are completed,
canceled, failed or limited. Canceled consumer tasks propagate and close the
source without producing false completion. Errors expose structural codes.

Expose the same run through ordinary Python, Expose Interface commands and
Carets messages. One Program and TerminalSession own input/output and teardown;
producer work remains outside update(). Escape control text and retain a
bounded display tail. Reuse Carets streams and TestProgram for deterministic
input, resize, cancellation and restoration checks. An explicitly configured
Thoughtform adapter can stream a real tiny Transformer through one owned worker;
this validates integration and does not establish useful trained behavior.

This finite domain lifecycle does not replace a durable workflow engine. Thread
cancellation is cooperative at token boundaries, not forced interruption.

## Single-agent harness foundation

1. HYP-TOOLS-01: accept a selected Hidden Moves catalog. Validate and authorize
   tool requests before execution; never build another registry/schema engine.
2. HYP-CONTEXT-01: bounded retrieval from explicit roots/providers, selected
   skills/instructions and Parse MD documents, with source provenance and
   trusted-instruction separation. Reuse the workspace capability plugin.
3. HYP-MEMORY-01: Backpack codecs/records for runs and evaluation metadata,
   explicit transcript retention, value-safe diagnostics and process reopen.
4. HYP-WORKFLOW-01: Moveset/func_seq composition and optional Scriptty documents
   for jobs. Resume without committed replay; uncertain effects require an
   explicit retry/restart decision and matching definition/source identity.
5. HYP-VERIFY-01: caller-selected actual verifiers, bounded repairs and workspace
   diffs. A model's completion claim cannot satisfy task acceptance by itself.
6. HYP-OLLAMA-01: explicitly configured endpoint/model through Requ and optional
   Apiconn operations. Test real framing/cancellation with synthetic transport;
   require selected hardware/model before long local inference.

## Training and measured optimization

HYP-TRAIN-01 orchestrates prepare/load/train/evaluate/register stages through
existing workflows. Thoughtformula owns all gradient/optimizer/checkpoint math.
Select dataset provenance/license, source checkpoint, destination and resource
budget first. Preserve the source checkpoint and register new artifact lineage;
never train, download or promote a model implicitly.

HYP-EVAL-01 establishes versioned tasks, seeds, development/selection/held-out
splits, actual verifier outcomes, equal-budget baselines, latency/token/tool/
repair/compute metrics and reproducibility receipts. Report failures and success
denominators. HYP-OPT-01 searches bounded harness configurations with held-out
regression gates and explicit promotion. It does not modify weights as a side
effect of selecting context/tools/workflows.

HYP-ORCH-01 adds bounded multi-agent roles, dependencies, admission and shared
resource budgets after the single-agent evaluation foundation. Reuse workflow
and provider seams, propagate cancellation and serialize or isolate model caches.
Start sequentially on constrained hardware.

## Composition and acceptance

Carets owns rendering/layout/focus/themes and terminal lifecycle. Expose
Interface owns parsing. Backpack owns storage. Hidden Moves owns capabilities.
Thoughtform owns identity/model definitions. Paracosm owns world authority.
Compose Application owns reusable assembly/reference qualification. Avoid core
cycles and optional-import side effects. The current UI provides application
evidence for later Carets design tokens and the Warewolf embedding contract.

Each task has a focused branch/PR and behavior checks. Build/install both wheel
and source outside the checkout, verify exact dependency sources, and run
headless profiles on Linux/macOS/Windows. Prove native terminals separately.
Public source development is authorized; package/weight uploads, releases,
paid providers and deployment require their own concrete authorization.

## Hero homegrown training continuation

The [expanded canonical chapter](https://github.com/wispsy/wispsy/blob/main/docs/cohesion-block-b/hero-training.md)
selects Hero, her Hero Coding specialization, independent Engl records,
explicit source review and a combined 15-minute first training pilot.
[HYP-SOURCE-01](https://github.com/wispsy/hypnosis/issues/13) records the approved
internal recipe and candidate Python vault/docs/wiki sources. All future source
additions remain owner-reviewed. The supplied local datasets support bounded
compressed/indexed preparation; no full Wikipedia extraction is needed.

The direct prepare/train/evaluate/register profile reuses func_seq and Backpack
and does not require externally connected tools. Thoughtformula owns bounded
pretraining, numerical evaluation and lossless optimizer resume; Thoughtform
owns named recipes/local artifacts and parent lineage. Curriculum/shuffle and
coding-child results require held-out counts/coverage and actual runtime/step
receipts. Ollama and the selected-catalog/tool path remain deferred.

HYP-MEMORY-01: typed structural training/evaluation/artifact receipts use Backpack
public codecs and explicit storage paths. Verification closes the store, reopens
it in a separate Python process, and checks idempotent recovery and conflicts.
Raw source text, credentials and transcripts are excluded from job receipts.

HYP-WORKFLOW-01: func_seq owns stage sequencing and progress. Identity-bound
trusted stage definitions refuse incompatible recovery; tests demonstrate
committed stages are not replayed and failed effects require explicit retry.
The first profile does not depend on an external tool catalog or Ollama.

HYP-EVAL-01: provider-neutral split measurement reports availability, tokenizer
coverage/exclusions and exact selected record/token denominators. The native
Thoughtformula loss adapter and nonexecuting syntax probes support fixed-budget
experiments. Missing held-out splits are explicit unavailable results. Matched
curriculum/shuffle comparison and small-sample limits belong in pilot receipts.
HYP-CURRICULUM-01: the approved internal v1 generator is deterministic, finite,
content-hashed and split by problem group. Tests independently verify every
reference and demonstrate train/held-out separation and source-selection bounds.
It contains no external teacher output or vault-derived material.

HYP-TRAIN-01: the integrated local job composes the public Thoughtformula,
Thoughtform, func_seq and Backpack APIs. Passive settings and corpus identities
bind recovery. Tokenizer fitting is training-only, with explicit unknown-text
counts and fixed per-document windows. Hero Coding starts from a fresh loaded
Hero parent and records lineage. Native checkpoint and quantized inference
exports stay local. The same owned worker emits bounded Carets progress and
joins on cooperative cancellation. Source/CLI/Carets/parent-preservation and
nonzero-step pause/retry tests cover the complete path; installed `training`
profiles qualify the application on Linux, macOS and Windows.

HERO-PILOT-02: completed-job receipt recollection validates the native artifact and
func_seq state before reopening the identical CLI without retry authority. It
retains original delivery diagnostics and respects the combined deadline. The
matched shuffle acceptance in HERO-PILOT-01 remains open; no curriculum advantage
or model promotion is claimed. Complete local training artifacts stay in ignored
run folders. The next source/window-mixture/runtime decision is tracked in #27.

The owner-approved sanitized pilot measurements are published in
`experiments/hero-pilot-v1/results-2026-11-20.json`, with the observed limits and
unperformed comparison documented beside them. Raw source text and weights are
not distributed.

HYP-DATA-02: citation provenance preserves reference groups and explicit bodies,
marks conflicting named reuse unresolved, and propagates truncation metadata.
Authored parser fixtures qualify the behavior without touching existing corpora
or performing additional model training.
