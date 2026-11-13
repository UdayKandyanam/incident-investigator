# Crash loops

## Symptoms

A pod is in CrashLoopBackOff and the restart count keeps climbing. The
container starts, exits, and is restarted with a growing backoff delay. The
previous container usually left a termination reason and an exit code.

## Checks

Read the logs from the previous container instance, not the current one.
The last lines before the exit usually name the problem: a missing file, a
failed database connection, a config value the process rejects at startup.

Check the exit code. Exit code 1 is a general application error. Exit code
137 means the process was killed, which points at memory or a node level
kill rather than the application itself. A container that exits in under a
second is failing at startup, often on config or a dependency check.

Compare what changed. A crash loop that starts right after a deployment is
usually the new build or its config. One that starts with no deployment is
usually a dependency that went away.

## Fix

Roll back the deployment if the loop started with a release. Fix the config
or the missing dependency if the cause is outside the build. Watch the
restart count stop climbing and the pod stay ready for several minutes
before calling it resolved. The sample billing-worker, for example, should
show a flat restart count across two checks ten minutes apart.

## Prevention

Add a startup probe so a process that cannot initialise is caught before it
receives traffic. Keep termination logs on, so the exit reason survives the
restart and the next investigation starts with evidence instead of a guess.
