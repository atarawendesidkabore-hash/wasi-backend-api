#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# WASI Pilot KPI Snapshot
# Usage: bash scripts/pilot-kpi-snapshot.sh [username] [password]
# Captures: availability, latency, data freshness, credit state,
#           endpoint responsiveness, security posture.
# Run at T+0 (baseline) and T+7 (week-1 report).
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

API="https://wasi-backend-api.onrender.com"
USER="${1:-seed_check}"
PASS="${2:-SeedCheck2026x}"
TS=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
OUTFILE="docs/pilot-kpi-$(date -u '+%Y%m%d-%H%M').md"

echo "WASI Pilot KPI Snapshot — $TS"
echo "Target: $API"
echo ""

# ── Auth ─────────────────────────────────────────────────────────
TOKEN=$(curl -s -X POST "$API/api/auth/login" \
  -d "username=$USER&password=$PASS" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

if [ -z "$TOKEN" ]; then
  echo "FATAL: login failed"
  exit 1
fi

# ── Probe function ───────────────────────────────────────────────
probe() {
  local label="$1"
  local url="$2"
  local method="${3:-GET}"
  local start end elapsed code body

  start=$(date +%s%N)
  if [ "$method" = "POST" ]; then
    body=$(curl -s -w "\n%{http_code}" -X POST "$url" -H "Authorization: Bearer $TOKEN" 2>/dev/null)
  else
    body=$(curl -s -w "\n%{http_code}" "$url" -H "Authorization: Bearer $TOKEN" 2>/dev/null)
  fi
  end=$(date +%s%N)
  code=$(echo "$body" | tail -1)
  elapsed=$(( (end - start) / 1000000 ))
  echo "$label|$code|${elapsed}ms"
}

# ── Availability & Latency ───────────────────────────────────────
echo "=== Endpoint Probes ==="
echo "Endpoint|HTTP|Latency"
echo "---|---|---"
probe "Health" "$API/api/health"
probe "Indices" "$API/api/indices/latest"
probe "Composite" "$API/api/composite/report"
probe "Markets" "$API/api/markets/latest"
probe "FX Rates" "$API/v1/market/fx?base=XOF&symbols=EUR,USD"
probe "Commodities" "$API/api/v2/data/commodities/latest"
probe "IMF Macro CI" "$API/api/v2/data/macro/CI"
probe "Bank Credit NG" "$API/api/v2/bank/credit-context/NG"
probe "Signals Live" "$API/api/v2/signals/live"
probe "Country NG" "$API/api/country/NG/index"
echo ""

# ── Data Freshness ───────────────────────────────────────────────
echo "=== Data Freshness ==="
curl -s "$API/api/indices/latest" -H "Authorization: Bearer $TOKEN" \
  | python3 -c "
import sys,json
d = json.load(sys.stdin)
idx = d.get('indices', {})
conf = d.get('confidence_indicators', {})
print(f'Indices period: {d.get(\"period_date\", \"?\")}')
print(f'Countries with data: {len(idx)}')
green = sum(1 for v in conf.values() if v == 'green')
yellow = sum(1 for v in conf.values() if v == 'yellow')
red = sum(1 for v in conf.values() if v == 'red')
print(f'Confidence: {green} green, {yellow} yellow, {red} red')
"

curl -s "$API/api/composite/report" -H "Authorization: Bearer $TOKEN" \
  | python3 -c "
import sys,json
d = json.load(sys.stdin)
latest = d.get('latest', {})
print(f'Composite: {latest.get(\"composite_value\", \"N/A\")}')
print(f'Countries in composite: {latest.get(\"countries_included\", \"?\")}')
print(f'Trend: {latest.get(\"trend_direction\", \"?\")}')
history = d.get('history_12m', [])
print(f'History depth: {len(history)} months')
"

curl -s "$API/api/v2/data/commodities/latest" -H "Authorization: Bearer $TOKEN" \
  | python3 -c "
import sys,json
d = json.load(sys.stdin)
prices = d.get('prices', [])
print(f'Commodities: {len(prices)} tracked')
for p in prices:
    print(f'  {p[\"code\"]}: USD {p[\"price_usd\"]:.2f} ({p.get(\"period\",\"?\")})')
"
echo ""

# ── Credit Economy ───────────────────────────────────────────────
echo "=== Credit State ==="
curl -s "$API/api/auth/me" -H "Authorization: Bearer $TOKEN" \
  | python3 -c "
import sys,json
d = json.load(sys.stdin)
print(f'User: {d[\"username\"]}')
print(f'Balance: {d[\"x402_balance\"]} credits')
print(f'Tier: {d[\"tier\"]}')
print(f'Active: {d[\"is_active\"]}')
"
echo ""

# ── Security Posture ─────────────────────────────────────────────
echo "=== Security Posture ==="
echo -n "Unauth /indices: "
curl -s -o /dev/null -w "%{http_code}" "$API/api/indices/latest"
echo ""
echo -n "Unauth /composite: "
curl -s -o /dev/null -w "%{http_code}" "$API/api/composite/report"
echo ""
echo -n "Admin seed (locked): "
curl -s -o /dev/null -w "%{http_code}" -X POST "$API/api/admin/seed" -H "X-Admin-Key: probe"
echo ""

HEADERS=$(curl -s -I "$API/" 2>/dev/null)
for h in "x-content-type-options" "x-frame-options" "strict-transport-security" "x-xss-protection" "content-security-policy" "referrer-policy" "permissions-policy"; do
  val=$(echo "$HEADERS" | grep -i "^$h:" | head -1 | tr -d '\r')
  if [ -n "$val" ]; then
    echo "PRESENT: $val"
  else
    echo "MISSING: $h"
  fi
done
echo ""

echo "=== Snapshot Complete ($TS) ==="
