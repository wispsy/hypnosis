# Bounded role jobs

`coordinate()` takes trusted RoleJob callbacks, explicit role/source identities,
a configuration hash, dependencies and JobLimits. Each callback receives the
run's cooperative RunControl. No role, callable or provider is loaded from text.
The full DAG is validated before work. Failed dependencies block children.

Sequential execution is the default. Parallel work requires both a larger
concurrency limit and different resource keys. The default `shared-model` key
serializes mutable model caches; use distinct keys only for isolated resources.
Admission reserves cumulative declared units before starting a job and never
oversubscribes the shared budget. Units are explicit work estimates, not measured
GPU time or an operating-system resource quota. Accepted JSON outputs share a
byte limit. Oversized results are discarded; trusted callbacks must also bound
their own allocations and external effects. One elapsed-time budget covers the
run; synchronous work settles cooperatively through the owned worker adapter.

func_seq journals each deterministic wave, including child outcomes. An explicit
checkpoint path can contain private result values and stays local. Completed
stages are not replayed; changed definitions are refused. Reviewing uncertain
interrupted effects before explicitly selecting `retry=True` remains the caller's
responsibility. Cancellation joins all owned children before returning. Public
receipts expose hashes, codes, reserved units and accepted sizes, not result text
or exception messages. No training or model provider is activated by this API.
