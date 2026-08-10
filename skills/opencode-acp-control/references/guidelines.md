# Transport and lifecycle guidelines

## Ownership model

The helper is the sole lifecycle owner:

```text
controller shell
├── runtime directory
├── stdin.fifo
├── stdout.fifo
├── FD 3: permanent stdin writer
├── FD 4: permanent stdout reader
└── exact OpenCode child PID
```

OpenCode is forked before the controller opens FD 3, so the child cannot
inherit the FIFO's permanent write end. This invariant is essential: if the
child inherited that descriptor, closing FD 3 in the controller would not
produce EOF.

`run.py send` opens a short-lived writer, writes one newline-delimited frame,
and closes it. FD 3 remains open, so the final-writer count never reaches zero
during the session. A file lock serializes senders and prevents frame
interleaving.

The controller owns FD 4 and continuously drains `stdout.fifo` into
`frames.ndjson`. Short-lived readers poll that regular file by line cursor and
therefore never contend for the stdout FIFO.

## Shutdown order

Normal shutdown follows this order:

1. Signal only the controller recorded for this runtime.
2. Close FD 3.
3. Let OpenCode observe stdin EOF and exit normally.
4. After a grace period, send `TERM` only if the exact child remains alive.
5. Wait for the child.
6. Close FD 4.
7. Unlink both FIFO nodes.
8. Retain regular logs only when `--keep-runtime` was requested; otherwise
   remove the marked runtime directory.

`run.py stop` verifies the controller command line contains both the bundled
helper path and the runtime path before signalling it. This reduces the risk of
killing an unrelated process after PID reuse.

## Crash recovery

`SIGKILL`, kernel failure, or an aggressive process supervisor cannot run shell
traps. The kernel still closes all process descriptors, so no live FD leaks
remain. If `run.py stop` confirms that both verified processes have disappeared,
it finishes unlinking stale FIFO nodes and marks the runtime `stopped:external`.
After a host or power failure, FIFO nodes and logs may remain on disk.

For a stale runtime:

1. Run `run.py status`.
2. Confirm both processes are not alive.
3. Run `run.py clean --runtime-dir ...`.

`clean` requires the private owner marker and refuses to remove a runtime while
either recorded process is alive.

## Security boundaries

- Runtime directories are created with mode `0700`; FIFO nodes use `0600`.
- Never share a runtime directory between users.
- Treat frames and stderr logs as sensitive because prompts, file content, and
  tool results may appear in them.
- Do not point `clean` or `stop` at a directory that was not returned by
  `start`.
- A transport handle authorizes sending messages to its OpenCode process. Keep
  it scoped to the calling agent session.

## Transport preflight

A `ready` state only proves that the FIFO endpoints and processes opened. The
required end-to-end preflight is:

1. Confirm controller and OpenCode liveness.
2. Send `initialize` as request ID 0.
3. Read until response ID 0 arrives.
4. Verify `result.protocolVersion` is supported.

An exit before step 3 is a transport/startup failure. A JSON-RPC `error`
response at step 3 proves the transport worked and the request was rejected at
the protocol layer.
