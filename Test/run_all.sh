#!/usr/bin/env bash
# Hardware-independent regression suite.
#
# Added with the MG100 connection fix: the static plugin-default guard only
# prevents a recurrence if somebody actually runs it, and there was no runner
# in the repo (only an ad-hoc /tmp script). Add new test_*.py files here.
#
# Usage: bash Test/run_all.sh        (backend must be running on :8000)
set -u
cd "$(dirname "$0")/.." || exit 1

SUITE=(
  test_codegen
  test_result_parsing
  test_ws_monitor
  test_parser_unique_and_trend
  test_serial_multiline
  test_can_comlog
  test_blocking
  test_dash_since
  test_update_service
  test_feedback
  test_mgw100_connect
)

# Hardware-only suites are skipped (not failed) when no MG100 is attached —
# otherwise a disconnected bench looks like a product regression.
hardware_available() {
  python3 - <<'PY' 2>/dev/null
import requests, sys
try:
    d = requests.get("http://localhost:8000/api/devices/", timeout=10).json()["data"]["items"]
    sys.exit(0 if any(x.get("protocol") == "mini_gateway100" and x.get("status") == "connected" for x in d) else 1)
except Exception:
    sys.exit(1)
PY
}

if hardware_available; then
  HARDWARE=(test_mg100_skill_syntax)
else
  HARDWARE=()
  printf '  %-36s SKIP (no MG100 hardware attached)\n' 'test_mg100_skill_syntax'
fi

failed=0
for t in "${SUITE[@]}" "${HARDWARE[@]}"; do
  printf '  %-36s ' "$t"
  if timeout 400 python3 "Test/$t.py" >/tmp/aitestlab_test_$t.log 2>&1 && ! grep -q '^FAILED' /tmp/aitestlab_test_$t.log; then
    echo PASS
  else
    echo FAIL
    echo "      see /tmp/aitestlab_test_$t.log"
    failed=$((failed + 1))
  fi
done

echo
if [ "$failed" -gt 0 ]; then
  echo "$failed suite(s) FAILED"
  exit 1
fi
echo "All $((${#SUITE[@]} + ${#HARDWARE[@]})) suites passed (${#HARDWARE[@]} hardware)."
