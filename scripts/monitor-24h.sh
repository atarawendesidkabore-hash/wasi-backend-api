#!/usr/bin/env bash
# WASI v4.0.0 — 24h Post-Release Monitor
# Usage: bash scripts/monitor-24h.sh [interval_seconds] [duration_hours]
# Default: every 10 minutes for 24 hours

BASE="https://wasi-backend-api.onrender.com"
INTERVAL=${1:-600}
DURATION_H=${2:-24}
TOTAL_CHECKS=$(( DURATION_H * 3600 / INTERVAL ))
LOG="logs/monitor-$(date -u +%Y%m%d-%H%M).log"

mkdir -p logs

echo "=== WASI v4.0.0 24h MONITOR ===" | tee "$LOG"
echo "Start: $(date -u +%Y-%m-%dT%H:%M:%SZ)" | tee -a "$LOG"
echo "Interval: ${INTERVAL}s | Duration: ${DURATION_H}h | Checks: $TOTAL_CHECKS" | tee -a "$LOG"
echo "---" | tee -a "$LOG"

ERRORS_5XX=0
TIMEOUTS=0
MAX_LATENCY=0

for (( i=1; i<=TOTAL_CHECKS; i++ )); do
    TS=$(date -u +%H:%M:%S)

    # Health check
    H_RAW=$(curl -s -o /tmp/wasi_h.json -w "%{http_code} %{time_total}" \
        "$BASE/api/health" --max-time 30 2>&1)
    H_CODE=$(echo "$H_RAW" | awk '{print $1}')
    H_TIME=$(echo "$H_RAW" | awk '{print $2}')

    # FX probe (expect 401 without token)
    FX_RAW=$(curl -s -o /dev/null -w "%{http_code} %{time_total}" \
        "$BASE/v1/market/fx" --max-time 30 2>&1)
    FX_CODE=$(echo "$FX_RAW" | awk '{print $1}')
    FX_TIME=$(echo "$FX_RAW" | awk '{print $2}')

    # Credit probe (expect 401 without token)
    CD_RAW=$(curl -s -o /dev/null -w "%{http_code} %{time_total}" \
        -X POST "$BASE/v1/credit/decision" \
        -H "Content-Type: application/json" -d '{}' --max-time 30 2>&1)
    CD_CODE=$(echo "$CD_RAW" | awk '{print $1}')
    CD_TIME=$(echo "$CD_RAW" | awk '{print $2}')

    # Detect issues
    ALERT=""
    for CODE in "$H_CODE" "$FX_CODE" "$CD_CODE"; do
        case "$CODE" in
            5*) ERRORS_5XX=$((ERRORS_5XX + 1)); ALERT="$ALERT 5XX=$CODE" ;;
            000) TIMEOUTS=$((TIMEOUTS + 1)); ALERT="$ALERT TIMEOUT" ;;
        esac
    done

    # Track max latency
    for T in "$H_TIME" "$FX_TIME" "$CD_TIME"; do
        if [ "$(echo "$T > $MAX_LATENCY" | bc -l 2>/dev/null)" = "1" ]; then
            MAX_LATENCY=$T
        fi
    done

    LINE="[$TS] ($i/$TOTAL_CHECKS) health=$H_CODE(${H_TIME}s) fx=$FX_CODE(${FX_TIME}s) credit=$CD_CODE(${CD_TIME}s)"
    if [ -n "$ALERT" ]; then
        LINE="$LINE *** ALERT:$ALERT ***"
    fi

    echo "$LINE" | tee -a "$LOG"

    # Early exit on critical failure (3+ consecutive 5xx)
    if [ "$ERRORS_5XX" -ge 3 ]; then
        echo "!!! CRITICAL: $ERRORS_5XX errors 5xx — TRIGGERING ROLLBACK ALERT !!!" | tee -a "$LOG"
        echo "Run: git revert HEAD~2..HEAD --no-edit && git push origin main" | tee -a "$LOG"
        break
    fi

    if [ "$i" -lt "$TOTAL_CHECKS" ]; then
        sleep "$INTERVAL"
    fi
done

echo "---" | tee -a "$LOG"
echo "=== MONITORING COMPLETE $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" | tee -a "$LOG"
echo "Total 5xx: $ERRORS_5XX" | tee -a "$LOG"
echo "Total timeouts: $TIMEOUTS" | tee -a "$LOG"
echo "Max latency: ${MAX_LATENCY}s" | tee -a "$LOG"

if [ "$ERRORS_5XX" -eq 0 ] && [ "$TIMEOUTS" -eq 0 ]; then
    echo "VERDICT: STABLE — 24h window clear" | tee -a "$LOG"
else
    echo "VERDICT: ISSUES DETECTED — review log at $LOG" | tee -a "$LOG"
fi
