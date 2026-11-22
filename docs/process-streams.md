# Owned process streams

`hypnosis stream --text ...` emits the selected
[wispsy.run-event/1 contract](https://github.com/wispsy/wispsy/blob/main/docs/cohesion-block-b/stream-contract.md).
Existing commands retain their single-document JSON format. Stream records are
flushed incrementally, with escaped text and distinct application exit codes.
The initial producer is deterministic and offline; no model is downloaded.

ProcessRun accepts one explicit argument vector, never a shell command. Consume
its async stream inside `contextlib.aclosing`; leaving early closes and reaps only
the owned child. stdout uses bounded reads and OS pipe pressure. stderr drains
concurrently to a bounded private tail, while receipts expose its count, hash
and truncation flag. Source text and raw stderr are absent from receipts.

The decoder rejects unknown/missing/duplicate fields, nonfinite values, wrong
types, invalid UTF-8/BOM, oversized or unterminated records, sequence changes,
missing outcomes and trailing records. A completed event alone is insufficient:
the whole stream must validate and the producer must exit zero. Failed/limited/
canceled records require their contract exit status. Signal termination remains
distinct. Earlier effects remain explicitly partial on an unsuccessful run.

Cancellation and elapsed-time limits terminate, then kill after a bounded grace
period, and await owned process teardown. A stalled downstream consumer still
must close its iterator; there is no automatic retry, rollback, descendant-process
management or exactly-once guarantee. Native inference threads remain cooperative;
use a separately owned process when a hard process lifetime is needed.

Tests use actual subprocesses for first-record-before-exit delivery, multibyte
framing, invalid/oversized records, nonzero and partial exits, stderr flooding,
slow-consumer backpressure, downstream close, cancellation and deadlines. POSIX
also tests a child ignoring SIGTERM. Windows tests are process/headless fixtures;
they do not claim native terminal-console support.
