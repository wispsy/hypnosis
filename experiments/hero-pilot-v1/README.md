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
unreproduced root cause. Local measurements require a separately selected public
report operation before they are copied into this repository.
