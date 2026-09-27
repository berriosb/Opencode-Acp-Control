#!/usr/bin/env bash
# Own the long-lived FIFO descriptors used by an OpenCode ACP process.

set -uo pipefail

readonly OWNER_MARKER="opencode-acp-control-runtime-v1"

usage() {
    cat >&2 <<'EOF'
Usage: helper.sh start --cwd DIR --runtime-dir DIR [--opencode EXECUTABLE]

This is the internal transport controller. Use run.py for normal operation.
EOF
}

fail() {
    printf 'helper.sh: %s\n' "$*" >&2
    exit 2
}

[[ "${1:-}" == "start" ]] || {
    usage
    exit 2
}
shift

workdir=""
runtime_dir=""
opencode_bin="opencode"

while (($#)); do
    case "$1" in
        --cwd)
            (($# >= 2)) || fail "--cwd requires a value"
            workdir=$2
            shift 2
            ;;
        --runtime-dir)
            (($# >= 2)) || fail "--runtime-dir requires a value"
            runtime_dir=$2
            shift 2
            ;;
        --opencode)
            (($# >= 2)) || fail "--opencode requires a value"
            opencode_bin=$2
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            fail "unknown argument: $1"
            ;;
    esac
done

[[ -n "$workdir" ]] || fail "--cwd is required"
[[ -n "$runtime_dir" ]] || fail "--runtime-dir is required"
[[ -d "$workdir" ]] || fail "working directory does not exist: $workdir"

workdir=$(cd -- "$workdir" && pwd -P) || fail "cannot resolve working directory"

if [[ "$opencode_bin" == */* ]]; then
    [[ -x "$opencode_bin" ]] || fail "OpenCode executable is not executable: $opencode_bin"
else
    opencode_bin=$(command -v -- "$opencode_bin") || fail "OpenCode executable not found on PATH"
fi

orig_umask=$(umask)

opencode_pid=""
fd3_open=false
fd4_open=false
child_status=0
stdin_fifo=""
stdout_fifo=""
state_file=""

cleanup() {
    local original_status=$?
    local attempt

    trap - EXIT INT TERM HUP

    # FD 3 is the permanent writer. Closing it is the graceful shutdown: once
    # one-shot senders are gone, OpenCode observes EOF on stdin and disposes.
    if [[ "$fd3_open" == true ]]; then
        exec 3>&-
        fd3_open=false
    fi

    if [[ -n "$opencode_pid" ]] && kill -0 "$opencode_pid" 2>/dev/null; then
        for attempt in {1..20}; do
            kill -0 "$opencode_pid" 2>/dev/null || break
            sleep 0.05
        done
        if kill -0 "$opencode_pid" 2>/dev/null; then
            kill -TERM "$opencode_pid" 2>/dev/null || true
            for attempt in {1..20}; do
                kill -0 "$opencode_pid" 2>/dev/null || break
                sleep 0.05
            done
            if kill -0 "$opencode_pid" 2>/dev/null; then
                kill -KILL "$opencode_pid" 2>/dev/null || true
            fi
        fi
        wait "$opencode_pid" 2>/dev/null || true
    fi

    if [[ "$fd4_open" == true ]]; then
        exec 4<&-
        fd4_open=false
    fi

    # Keep regular logs for diagnosis, but never leave live FIFO endpoints.
    if [[ -n "$stdin_fifo" || -n "$stdout_fifo" ]]; then
        rm -f -- "${stdin_fifo:-}" "${stdout_fifo:-}"
    fi

    if [[ "$child_status" -eq 0 && "$original_status" -ne 0 ]]; then
        child_status=$original_status
    fi

    if [[ -n "$state_file" && -d "${runtime_dir:-}" ]]; then
        printf '%s\n' "stopped:$child_status" >"$state_file" 2>/dev/null || true
        printf 'STOPPED\t%s\t%s\n' "$runtime_dir" "$child_status"
    fi
    return "$original_status"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

umask 077
mkdir -p -- "$runtime_dir" || fail "cannot create runtime directory: $runtime_dir"
runtime_dir=$(cd -- "$runtime_dir" && pwd -P) || fail "cannot resolve runtime directory"
chmod 700 -- "$runtime_dir" || fail "cannot make runtime directory private"

stdin_fifo="$runtime_dir/stdin.fifo"
stdout_fifo="$runtime_dir/stdout.fifo"
frames_log="$runtime_dir/frames.ndjson"
stderr_log="$runtime_dir/stderr.log"
state_file="$runtime_dir/state"
controller_pid_file="$runtime_dir/controller.pid"
opencode_pid_file="$runtime_dir/opencode.pid"

[[ ! -e "$stdin_fifo" && ! -e "$stdout_fifo" ]] || \
    fail "runtime directory already contains FIFO nodes"

printf '%s\n' "$OWNER_MARKER" >"$runtime_dir/.owner"
printf '%s\n' "$workdir" >"$runtime_dir/cwd"
printf '%s\n' "$opencode_bin" >"$runtime_dir/opencode.command"
printf '%s\n' "starting" >"$state_file"
printf '%s\n' "$$" >"$controller_pid_file"
: >"$frames_log"
: >"$stderr_log"
mkfifo -m 600 -- "$stdin_fifo" "$stdout_fifo" || fail "cannot create FIFO nodes"

# Start the child before opening FD 3. This guarantees the child cannot inherit
# the permanent writer. Its stdin open blocks until the controller opens FD 3.
# Restore the caller's original umask so workspace files created by OpenCode
# are not constrained by the controller's private 077 umask.
(
    umask "$orig_umask"
    exec "$opencode_bin" acp --cwd "$workdir" \
        <"$stdin_fifo" \
        >"$stdout_fifo" \
        2>>"$stderr_log"
) &
opencode_pid=$!
printf '%s\n' "$opencode_pid" >"$opencode_pid_file"

# These two opens pair with the blocked child redirections. FD 3 remains open
# for the complete ACP lifetime, so closing a one-shot FIFO writer is not EOF.
exec 3>"$stdin_fifo"
fd3_open=true
exec 4<"$stdout_fifo"
fd4_open=true

if ! kill -0 "$opencode_pid" 2>/dev/null; then
    child_status=1
    printf '%s\n' "failed" >"$state_file"
    fail "OpenCode exited during transport startup"
fi

printf '%s\n' "ready" >"$state_file"
printf 'READY\t%s\t%s\t%s\n' "$runtime_dir" "$$" "$opencode_pid"

# Drain stdout continuously. A regular append-only queue lets separate, short
# run.py invocations poll without becoming another owner of the transport FD.
while IFS= read -r frame <&4; do
    printf '%s\n' "$frame" >>"$frames_log"
done

if wait "$opencode_pid"; then
    child_status=0
else
    child_status=$?
fi

exit "$child_status"
