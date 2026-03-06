#!/usr/bin/env bash
# WASI v4.0.0 — Extract 24h Post-Release Summary from monitor log
# Usage: bash scripts/extract-24h-report.sh [logfile]
# Default: latest log in logs/

set -e

if [ -n "$1" ]; then
    LOG="$1"
else
    LOG=$(ls -t logs/monitor-*.log 2>/dev/null | head -1)
fi

if [ -z "$LOG" ] || [ ! -f "$LOG" ]; then
    echo "ERROR: No monitor log found. Run scripts/monitor-24h.sh first."
    exit 1
fi

echo "============================================"
echo "  WASI v4.0.0 — Post-Release 24h Summary"
echo "============================================"
echo ""
echo "Log: $LOG"
echo "Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""

# Total checks
TOTAL=$(grep -c '^\[' "$LOG" 2>/dev/null || echo 0)
echo "--- CHECKS ---"
echo "Total checks executed: $TOTAL"

# 5xx errors
COUNT_5XX=$(grep -oP 'health=5\d\d|fx=5\d\d|credit=5\d\d' "$LOG" 2>/dev/null | wc -l | tr -d ' ')
echo "5xx errors: $COUNT_5XX"

# Timeouts (code 000)
COUNT_TIMEOUT=$(grep -oP '=000\(' "$LOG" 2>/dev/null | wc -l | tr -d ' ')
echo "Timeouts: $COUNT_TIMEOUT"

# Alerts
COUNT_ALERTS=$(grep -c 'ALERT' "$LOG" 2>/dev/null || true)
COUNT_ALERTS=${COUNT_ALERTS:-0}
COUNT_ALERTS=$(echo "$COUNT_ALERTS" | tr -d ' ')
echo "Alerts triggered: $COUNT_ALERTS"

# Rollback triggered?
ROLLBACK=$(grep -c 'ROLLBACK' "$LOG" 2>/dev/null || true)
ROLLBACK=${ROLLBACK:-0}
ROLLBACK=$(echo "$ROLLBACK" | tr -d ' ')
echo "Rollback triggered: $([ "$ROLLBACK" -gt 0 ] && echo 'YES' || echo 'NO')"

echo ""
echo "--- LATENCY ---"

# Extract all health latencies
grep -o 'health=200([0-9.]*' "$LOG" 2>/dev/null | sed 's/health=200(//' | sort -n > /tmp/wasi_lat.tmp

if [ -s /tmp/wasi_lat.tmp ]; then
    COUNT_OK=$(wc -l < /tmp/wasi_lat.tmp)
    MIN=$(head -1 /tmp/wasi_lat.tmp)
    MAX=$(tail -1 /tmp/wasi_lat.tmp)
    P50_IDX=$(( COUNT_OK * 50 / 100 + 1 ))
    P95_IDX=$(( COUNT_OK * 95 / 100 + 1 ))
    P50=$(sed -n "${P50_IDX}p" /tmp/wasi_lat.tmp)
    P95=$(sed -n "${P95_IDX}p" /tmp/wasi_lat.tmp)
    AVG=$(awk '{sum+=$1} END {printf "%.3f", sum/NR}' /tmp/wasi_lat.tmp)

    echo "Healthy responses: $COUNT_OK / $TOTAL"
    echo "Min: ${MIN}s"
    echo "Max: ${MAX}s"
    echo "Avg: ${AVG}s"
    echo "p50: ${P50}s"
    echo "p95: ${P95}s"
else
    echo "No healthy responses recorded."
fi

echo ""
echo "--- UPTIME ---"
HEALTH_OK=$(grep -c 'health=200' "$LOG" 2>/dev/null || true)
HEALTH_OK=${HEALTH_OK:-0}
HEALTH_OK=$(echo "$HEALTH_OK" | tr -d ' ')
if [ "$TOTAL" -gt 0 ]; then
    UPTIME=$(awk "BEGIN {printf \"%.2f\", $HEALTH_OK / $TOTAL * 100}")
    echo "Uptime: ${UPTIME}% ($HEALTH_OK / $TOTAL healthy)"
else
    echo "Uptime: N/A (no checks)"
fi

echo ""
echo "--- VERDICT ---"
if [ "$COUNT_5XX" -eq 0 ] && [ "$COUNT_TIMEOUT" -eq 0 ] && [ "$ROLLBACK" -eq 0 ]; then
    echo "STABLE — v4.0.0 production validated over 24h window"
    echo "Recommendation: close monitoring window, proceed with client onboarding"
elif [ "$ROLLBACK" -gt 0 ]; then
    echo "ROLLBACK TRIGGERED — review incident and root cause before resuming"
else
    echo "ISSUES DETECTED — review alerts in log before closing monitoring window"
    echo ""
    echo "Alert details:"
    grep 'ALERT' "$LOG" 2>/dev/null | tail -10
fi

echo ""
echo "============================================"

rm -f /tmp/wasi_lat.tmp
