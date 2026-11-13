#!/usr/bin/env bash
# Reproduces the "s_<id> was not declared" failure of issue #27 with a refresh alone.
# Needs: rpp installed and RPP_CPP_CORE_PATH set (as in the CI job of this repository).
# Uses a throw-away RPP home, so an existing ~/.rpp is not touched.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
home="$(mktemp -d)/.rpp"

rpp --rpp-home "$home" init-home > /dev/null
rpp --rpp-home "$home" registry config set RPP_CPP_CORE_PATH "$RPP_CPP_CORE_PATH" > /dev/null

echo "== register (expected: succeeds)"
rpp --rpp-home "$home" library register "$here/mini" 2>&1 | tail -3
echo "== refresh (fails on develop)"
rpp --rpp-home "$home" library refresh mini > "$home/../refresh.log" 2>&1
code=$?
grep -E "was not declared" "$home/../refresh.log" | head -3
echo "refresh exit code: $code"
