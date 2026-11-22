# Context selection

Construct the existing `hidden_moves_workspace.Workspace` with an explicit root
and file list, then select `ContextSource` records through `ContextSelector`.
Search is the Workspace plugin's literal search; reads/continuations use its
expected SHA-256 and line/column references. No directories, links or providers
are discovered from document contents. Parse MD supplies Markdown structure.

Caller instructions remain a separate input. Retrieved instructions/skills/
knowledge default to untrusted data. Only an explicit caller configuration can
mark an instruction source trusted; document headings/frontmatter cannot do so.
This provenance boundary does not claim a model is immune to prompt injection:
tool authority stays independently fixed by the selected catalog/policy.

`ContextBudget` bounds rendered prompt UTF-8 bytes, source count and read/search
calls. Optional token caps require the caller's real tokenizer counter. Framing
is included in the measured text budget; model-specific provider templates remain
the provider's responsibility. Binary prefix packing can leave unused capacity
with a non-monotonic tokenizer, but final output must satisfy the exact cap.
Instructions that exceed the budget fail before reads rather than being dropped.

Selected fragments carry source hashes, line/column provenance and truncation.
Long-line continuation never inserts artificial newlines. A read budget can return
a useful explicitly truncated prefix. Per-file identities prevent mixing changed
pages; they are not a transaction over the whole filesystem. Workspace's own
selection, symlink, UTF-8 and file-size rules remain authoritative.

Private prompts, paths and excerpt text remain in the bundle for the configured
consumer. `receipt()` excludes them and retains only hashes, ranges, kinds, counts
and budget outcomes. No context is admitted to model training by retrieval.
