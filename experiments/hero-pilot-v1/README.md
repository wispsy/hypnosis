# Hero pilot v1

This local experiment compares one curriculum-ordered Hero run with one shuffled
run using the same seed, tokenizer, training windows and optimizer-step budget.
Hero Coding then specializes from the curriculum Hero checkpoint using only the
explicitly approved internal Python recipe. It is a small learning/pipeline
experiment, not a useful assistant or functional coding benchmark.

Prepare an approved local corpus with `hypnosis prepare`, create the parent run
directory, then use the installed `training` profile:

```sh
python experiments/hero-pilot-v1/run.py .corpora/selected .runs/hero-pilot-v1
```

The launcher prints its scheduled stop time in Pacific time, benchmarks five
steps on the selected corpus, chooses equal Hero step budgets, and bounds all
three jobs plus the probe to **900 seconds combined**. Every child process has
the remaining combined deadline; a timeout kills the active child. Its last
completed native checkpoint remains local for explicitly reviewed recovery.
Individual jobs also check time and pause at optimizer boundaries.

Each destination is new. Source snapshots, corpus hashes, tokenizer coverage,
fixed held-out source/family windows, native/inference hashes, parent lineage,
before/after loss/perplexity and syntax-only counts are recorded. Source text and
weights remain in ignored local directories. Only a sanitized measurement
receipt belongs in this directory. A single seed and small samples cannot
establish a curriculum advantage or broad knowledge/coding ability.

Completed-job result collection uses `hypnosis.pilot_results` if child stdout is
missing or malformed. It verifies the selected native artifact and durable report,
requires func_seq's completed state, and reopens the identical command without
retry authority. The original delivery diagnostics remain available. Recollection
shares the original combined deadline and never grants permission to repeat an
uncertain optimizer stage. This handles delivery failure without asserting an
unreproduced root cause. Raw sources and checkpoints remain local; the owner
approved publication of the sanitized measurement report below.

## First bounded execution — 20 November 2026

The [sanitized receipt](results-2026-11-20.json) records two learned checkpoints
within the original 11:52:44 AM PST deadline. Corpus preparation retained 925
records (490 train, 282 validation, 153 test). The bounded training-window pool
reached internal exercises and TinyStories; it did not consume every prepared
Wikipedia/UD/Wiktionary record. Coverage and exclusions are explicit in the receipt.

| Model | Steps | Trained tokens | Native training time | Validation loss before → after | Mixed test loss before → after |
| --- | ---: | ---: | ---: | ---: | ---: |
| Hero | 1,478 | 44,662 | 277.4 s | 5.1385 → 4.1705 | 5.2191 → 4.3728 |
| Hero Coding | 500 | 14,320 | 89.4 s | 4.1705 → 3.8959 | 4.3728 → 5.0441 |

Both models use 86,900 parameters and a 140-entry tokenizer. Evaluation selects
16 fixed source/family windows per split: 451 validation and 448 test tokens.
Neither model passed its one syntax probe. Hero Coding regressed on the mixed
test. These single-seed samples do not qualify a general assistant, functional
coding model or autonomous operation of training tools. No model is promoted.

Hero's stdout collection failed after its complete result was persisted. Reopening
the identical completed job recovered the result without replaying stages. Hero
Coding used the remaining original wall-clock time. **No shuffled baseline ran**,
so no curriculum advantage is claimed. Safe recollection is implemented in
[#26](https://github.com/wispsy/hypnosis/issues/26); the underlying delivery fault
was not deterministically reproduced. The matched comparison remains open in
[#16](https://github.com/wispsy/hypnosis/issues/16) and requires a new runtime
selection. [#27](https://github.com/wispsy/hypnosis/issues/27) collects the next
authored-source, source-mixture and runtime decisions.

Native `.tft` and quantized `.mgpt` artifacts reload with matching tokenizers and
step counts. Inference exports embed neither raw corpus segments nor RAG source
documents. The report contains measurements and hashes; it distributes no source
text, generated continuations, tokenizer vocabulary, credentials or weights.
