
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
BINARY="$SCRIPT_DIR/binder_test"
LOG="$(mktemp)"

if [[ $EUID -ne 0 ]]; then
    echo "Run this test with sudo:"
    echo "sudo $0"
    exit 1
fi

if [[ ! -x "$BINARY" ]]; then
    echo "Compile the test first:"
    echo "cc -std=c11 -Wall -Wextra -Werror -O2 -o \"$BINARY\" \"$SCRIPT_DIR/binder_test.c\""
    exit 1
fi

"$BINARY" server >"$LOG" 2>&1 &
SERVER_PID=$!

cleanup() {
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
    rm -f "$LOG"
}
trap cleanup EXIT

ready=0

for _ in $(seq 1 50); do
    if grep -q '^READY$' "$LOG"; then
        ready=1
        break
    fi

    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        cat "$LOG"
        echo "Binder server exited before becoming ready."
        exit 1
    fi

    sleep 0.1
done

if [[ $ready -ne 1 ]]; then
    cat "$LOG"
    echo "Timed out waiting for Binder server."
    exit 1
fi

"$BINARY" client

wait "$SERVER_PID"
cat "$LOG"

echo "Binder IPC test completed."
