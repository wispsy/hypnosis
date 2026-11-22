# Verification and repair

`verify_and_repair` accepts configured trusted producer/verifier/repair callbacks.
The producer and repair return a `Candidate`; only the selected verifier can
return `Verification(passed=True)` after checking the real artifact. A model's
narration, or a dictionary containing a `passed` key, cannot complete a task.

Attempt, shared time and aggregate output budgets are finite. Async work cancels
cooperatively; synchronous callbacks use the existing owned adapter and settle
before returning. Pass, repair success, attempt exhaustion, cancellation and
verifier errors retain distinct outcomes. A verifier exception stops the task.
Uncertain effects in a candidate or its tool receipts stop automatic repair.

The candidate keeps its actual workspace diff privately for review. The report
retains candidate/diff/evidence hashes, attempt numbers and verifier outcomes,
without copying candidate text, diffs or private exceptions into receipts. Callers
keep their own workspace baseline/artifacts when persistent diff review is needed.
The library does not execute generated code; a caller-selected verifier has only
the authority granted by its configured implementation and selected tools.

Existing func_seq workflows remain the durable lifecycle owner. This finite repair
policy is a domain operation that can be a trusted workflow/job stage; it does
not implement a second recovery journal or silently retry uncertain effects.
