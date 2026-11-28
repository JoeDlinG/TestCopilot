#!/usr/bin/env bash
# Hardware-independent regression suite.
#
# Added with the MG100 connection fix: the static plugin-default guard only
# prevents a recurrence if somebody actually runs it, and there was no runner
# in the repo (only an ad-hoc /tmp script). Add new test_*.py files here.
#
# Usage: bash Test/run_all.sh        (backend must be running on :8000)
#        AITESTLAB_PYTHON=/path/to/venv/python bash Test/run_all.sh
set -u
cd "$(dirname "$0")/.." || exit 1

# Plain ``python3`` is the managed *base* interpreter on this dev box and has
# no FastAPI, which used to make every suite fail with ModuleNotFoundError.
# Resolve an interpreter that actually carries the backend dependencies.
pick_python() {
  if [ -n "${AITESTLAB_PYTHON:-}" ] && [ -x "$AITESTLAB_PYTHON" ]; then
    printf '%s' "$AITESTLAB_PYTHON"; return
  fi
  local cand
  for cand in \
    "${VIRTUAL_ENV:-}/Scripts/python.exe" \
    "${VIRTUAL_ENV:-}/bin/python" \
    "$HOME/.workbuddy/binaries/python/envs/aitestlab/Scripts/python.exe" \
    "$HOME/.workbuddy/binaries/python/envs/aitestlab/bin/python" \
    ".venv/Scripts/python.exe" ".venv/bin/python" \
    "backend/.venv/Scripts/python.exe" "backend/.venv/bin/python" \
    "python3"; do
    if [ -x "$cand" ] || command -v "$cand" >/dev/null 2>&1; then
      printf '%s' "$cand"; return
    fi
  done
  printf '%s' "python3"
}
PYTHON="$(pick_python)"
if ! "$PYTHON" -c 'import fastapi, sqlalchemy' >/dev/null 2>&1; then
  echo "ERROR: $PYTHON lacks backend dependencies (fastapi/sqlalchemy)." >&2
  echo "       Set AITESTLAB_PYTHON to the project venv interpreter." >&2
  exit 2
fi

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
  test_device_delete
  test_peakcan_prepare
  test_i18n_zh_pages
  test_plan_case_validation
  test_version_consistency
  test_boot_guards
  test_regression_guards
  test_issue33_peakcan_protocol
  test_flow_command_source
  test_startup_resilience
  test_issue34_generic_can
  test_static_runtime
  test_dbc_import_and_parse
  test_dbc_log_e2e
  test_dbc_real_assets
  test_dc_power_plugins
  test_dc_power_api_chain
)

# Hardware-only suites are skipped (not failed) when no MG100 is attached —
# otherwise a disconnected bench looks like a product regression.
hardware_available() {
  "$PYTHON" - <<'PY' 2>/dev/null
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
  HARDWARE_SKIPPED=0
else
  HARDWARE=()
  HARDWARE_SKIPPED=1
  printf '  %-36s SKIP (no MG100 hardware attached)\n' 'test_mg100_skill_syntax'
fi

failed=0
skipped=0
for t in "${SUITE[@]}" "${HARDWARE[@]}"; do
  printf '  %-36s ' "$t"
  if timeout 400 "$PYTHON" "Test/$t.py" >/tmp/aitestlab_test_$t.log 2>&1 && ! grep -q '^FAILED' /tmp/aitestlab_test_$t.log; then
    # Some suites need a specific test case / flow that lives in the workspace.
    # A "new project" replaces those cases; that is missing fixture data, not a
    # product regression, so report it honestly instead of a fake PASS.
    if grep -q '\[SKIP\]' /tmp/aitestlab_test_$t.log; then
      echo "SKIP (workspace fixture data missing)"
      skipped=$((skipped + 1))
    else
      echo PASS
    fi
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
echo "All $((${#SUITE[@]} + ${#HARDWARE[@]} - skipped)) suites passed ($skipped data-skipped, $HARDWARE_SKIPPED hardware-skipped)."
