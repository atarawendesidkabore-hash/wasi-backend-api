# Worker Architecture Assessment

## Current State
- 29 scheduled jobs running on a single APScheduler AsyncIOScheduler in the main FastAPI process
- No external queue system (no Celery, Redis Queue, dramatiq)
- All jobs registered in `src/tasks/composite_update.py`
- Bootstrap (startup) runs up to 5 external scrapers sequentially (~2-3 min)

## Job Inventory

| Job ID | Schedule | File | Est. Duration | Blocking? | Lock? |
|--------|----------|------|---------------|-----------|-------|
| composite_update | 6h interval | composite_update.py | ~5s | sync DB | yes |
| news_sweep | 1h interval | news_sweep.py | ~10s | HTTP+regex | yes |
| ussd_aggregation | 4h interval | ussd_aggregation.py | ~15s | sync DB | yes |
| route_corridor_bridge | 4h interval | ussd_aggregation.py | ~5s | sync DB | no |
| ecfa_domestic_settlement | 15min interval | cbdc_settlement_task.py | ~15s | sync DB | yes |
| ecfa_cross_border_settlement | 4h interval | cbdc_settlement_task.py | ~20s | sync DB | yes |
| ecfa_daily_limit_reset | 00:01 UTC cron | cbdc_settlement_task.py | ~2s | sync DB | no |
| ecfa_auto_unfreeze | 00:02 UTC cron | cbdc_settlement_task.py | ~2s | sync DB | no |
| ecfa_aml_sweep | 1h interval | cbdc_compliance_task.py | ~5s | sync DB | no |
| ecfa_monetary_aggregates | 23:55 UTC cron | cbdc_settlement_task.py | ~5s | sync DB | no |
| ecfa_daily_interest | 00:05 UTC cron | cbdc_monetary_policy_task.py | ~10s | sync DB | no |
| ecfa_reserve_check | 06:00 UTC cron | cbdc_monetary_policy_task.py | ~5s | sync DB | no |
| ecfa_facility_maturation | 1h interval | cbdc_monetary_policy_task.py | ~3s | sync DB | no |
| forecast_update | 04:00 UTC cron | forecast_task.py | ~40s | CPU (numpy) | yes |
| forecast_v2_update | 04:30 UTC cron | forecast_v2_task.py | ~60s | CPU (numpy) | yes |
| fx_rate_update | 6h interval | fx_rate_update.py | ~5s | HTTP | yes |
| tokenization_aggregation | 4h interval | tokenization_aggregation.py | ~30s | sync DB+pandas | yes |
| tokenization_disbursement | 20:00 UTC cron | tokenization_aggregation.py | ~10s | sync DB | no |
| legislative_sweep | 6h interval | legislative_sweep.py | ~30s | HTTP+regex | yes |
| fx_analytics_update | 6h interval | fx_analytics_task.py | ~10s | HTTP | yes |
| corridor_assessment | 6h interval | corridor_assessment.py | ~5s | sync DB | yes |
| alert_evaluation | 5min interval | alert_evaluation.py | ~5s | sync DB+HTTP webhooks | no |
| run_reconciliation | 2h interval | reconciliation_task.py | ~10s | sync DB scan | yes |
| world_news_sweep | 05:00 UTC cron | world_news_sweep.py | ~30s | HTTP+API | no |
| token_blacklist_cleanup | 30min interval | security.py | ~1s | sync DB | no |
| refresh_token_cleanup | 03:00 UTC cron | auth_cleanup.py | ~1s | sync DB | no |

## Risk Analysis

### Event Loop Blocking
- All tasks use `async def` but most do synchronous DB operations via SQLAlchemy ORM
- CPU-bound tasks (forecast_update, forecast_v2_update) with numpy/polyfit block the event loop
- HTTP-requesting tasks (news_sweep, legislative_sweep, world_news_sweep) use synchronous `requests` library

### High-Frequency Overlap Risk
- alert_evaluation (5 min) + ecfa_domestic_settlement (15 min) are the most frequent heavy jobs
- During peak overlap windows, up to 3-4 tasks could be executing simultaneously
- Threading locks prevent re-entrant execution but don't prevent event loop starvation

### Startup Latency
- Bootstrap phase runs 5 external scrapers sequentially: World Bank (~90s), IMF (~15s), Commodities (~5s), USSD scrapers (~30s), ACLED (~10s)
- Mitigated by SKIP_SCRAPERS=True and LIGHT_STARTUP=True config flags

## Immediate Mitigations (No New Dependencies)

### 1. Wrap CPU-bound tasks in asyncio.to_thread()
```python
# Before (blocks event loop):
async def forecast_update():
    result = engine.run_all_forecasts()  # CPU-bound

# After (runs in thread pool):
async def forecast_update():
    result = await asyncio.to_thread(engine.run_all_forecasts)
```
Applies to: forecast_update, forecast_v2_update, tokenization_aggregation

### 2. Add max_instances=1 to all jobs
```python
scheduler.add_job(task, trigger, max_instances=1, ...)
```
Belt-and-suspenders alongside threading locks.

### 3. Increase jitter on high-frequency jobs
```python
# alert_evaluation: jitter=60 (currently likely 0)
# ecfa_domestic_settlement: jitter=120
```
Reduces probability of task overlap with API request bursts.

### 4. Stagger daily cron jobs
Currently: 00:01, 00:02, 00:05 are clustered.
Spread to: 00:01, 00:15, 00:30 to reduce midnight spike.

## Future Migration Path (Document Only)

### Phase A: Thread Pool Workers
- Move to `run_in_executor()` for all sync tasks
- Use FastAPI's built-in thread pool (default: 40 threads)
- Zero new dependencies

### Phase B: Dedicated Worker Process
- Adopt `arq` (async Redis queue) or `dramatiq` (for simplicity)
- Separate worker process handles heavy tasks
- API process stays responsive
- Requires Redis (or RabbitMQ for dramatiq)

### Phase C: Horizontal Scaling
- Multiple worker instances behind Redis broker
- Independent scaling of API and worker pods
- Kubernetes-native with health checks

## Summary

| Metric | Current | Target |
|--------|---------|--------|
| Jobs | 29 | 29 |
| Workers | 1 (in-process) | 1 (Phase A), N (Phase C) |
| Event loop blocking | Yes (11 tasks) | No (all threaded) |
| Max concurrent heavy tasks | 4 | 1 per type |
| Startup time | 2-3 min | <30s (SKIP_SCRAPERS) |
