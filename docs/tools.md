# Selected tools

Create a public Hidden Moves `CapabilityCatalog` from configured trusted targets
and explicit names, then pass it to `ToolExecutor(catalog, ToolPolicy(names))`.
A `ToolRequest(id, name, arguments)` snapshots finite JSON using Hidden Moves;
its argument property returns a fresh value. Catalog schemas/binding/serialization
remain authoritative. Policy names must be a subset of that selected catalog.

Unknown or disallowed names fail before invocation. Input, output, call and shared
run time limits are explicit. Outputs are returned privately to the caller;
`outcome.receipt()` contains only identity, hashes, sizes, timing and structural
status. Target configuration, credentials, arguments, result text and exception
messages are excluded. Authorization is the caller's explicit selected policy;
provider annotations are descriptions rather than a substitute for authority.

Async tools cooperate with cancellation. Synchronous calls use the existing owned
worker adapter and settle before returning after cancellation/deadlines. Python
threads cannot be forcibly terminated: a time limit initiates cancellation and
ownership settlement can exceed it. A started failed/canceled/late call reports
uncertain effects; it is never replayed automatically or described as undone.
External task cancellation propagates after cleanup, retaining `last_receipt`.
Use isolated caller-approved processes when a hard process deadline is required.

Provider code is trusted application configuration. Retrieved instructions or
model text never load providers, import Python or broaden the selected catalog.
Install the explicit `tools` extra; normal imports/demo remain lightweight.
