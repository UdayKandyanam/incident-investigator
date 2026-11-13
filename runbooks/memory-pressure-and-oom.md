# Memory pressure and OOM kills

## Symptoms

A container shows a last termination reason of OOMKilled and restarts. On a
node under memory pressure, pods may also be evicted, and the node reports
a MemoryPressure condition. Restarts repeat because the workload hits the
same memory wall after every start.

## Checks

Compare the container memory limit with the usage the process reaches
before it dies. A steady climb to the limit looks like a leak or an
unbounded cache. An instant spike looks like one oversized request or a
batch job loading a whole file into memory.

Check whether one pod is being killed or every pod on the node. One pod
points at that workload and its limit. Many pods plus a node MemoryPressure
condition points at an overcommitted node, and the fix is capacity or
requests set honestly, not a bigger limit on one container.

## Fix

Raise the memory limit only when the working set genuinely needs it, and
pair the change with a request so the scheduler can place the pod honestly.
For a leak, restart buys time but the fix is in the code: cap the cache,
stream the large input, or page the result set. The sample report generator
service, for instance, should stream its export instead of holding it all
in memory.

## Prevention

Alert on containers running above 85 percent of their memory limit for
fifteen minutes, before the kill. Review limits after any change that adds
caching. Keep node level alerts on MemoryPressure so capacity problems are
seen as capacity problems.
