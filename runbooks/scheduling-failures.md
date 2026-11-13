# Scheduling failures

## Symptoms

A pod stays in Pending with no node assigned. Events show FailedScheduling
messages from the scheduler. The deployment reports fewer available
replicas than desired while other pods on the cluster run normally.

## Checks

Read the FailedScheduling message closely. It names the reason: insufficient
cpu, insufficient memory, a taint no pod tolerates, or a node affinity rule
no node matches. The message is the diagnosis most of the time.

Add up the resource requests of the pending pod and compare them with the
free capacity on the nodes. A single pod asking for more cpu than any node
has free will wait forever. Check recent changes too: a raised request, a
new affinity rule, or nodes cordoned for maintenance all shrink the pool
the scheduler can use.

## Fix

Lower an oversized request to what the workload actually uses, or add
capacity when the request is honest. Remove a stale cordon after
maintenance finishes. For the sample storefront-web tier, confirm the pod
lands and the deployment returns to its full replica count.

## Prevention

Review requests against measured usage monthly, so requests stay honest
and the scheduler can pack nodes well. Alert on pods Pending for more than
ten minutes. Capacity reviews should count the largest pod in the cluster,
not just the average one.
