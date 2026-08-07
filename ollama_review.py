"""
WASI Platform — Ollama Full Codebase Review Script

Reads every Python source file in the project, batches them by layer,
and sends each batch to a local Ollama model for a structured code review.

Usage:
    python ollama_review.py                          # defaults to llama3
    python ollama_review.py --model codellama        # use a specific model
    python ollama_review.py --model deepseek-coder-v2 --output review.md

Prerequisites:
    pip install requests
    ollama must be running locally (ollama serve)
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package required. Run: pip install requests")
    sys.exit(1)

# ── Configuration ─────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
SRC_DIR = PROJECT_ROOT / "src"
TESTS_DIR = PROJECT_ROOT / "tests"
OLLAMA_URL = "http://localhost:11434/api/generate"

# Organize files into logical review batches
FILE_GROUPS = {
    "1. Entry Point & Config": [
        "src/main.py",
        "src/config.py",
        "src/bootstrap.py",
    ],
    "2. Database Connection & Core Models": [
        "src/database/connection.py",
        "src/database/models.py",
        "src/database/seed.py",
    ],
    "3. Database — USSD & CBDC Models": [
        "src/database/ussd_models.py",
        "src/database/cbdc_models.py",
        "src/database/cbdc_payment_models.py",
    ],
    "4. Database — Financial Models": [
        "src/database/forecast_models.py",
        "src/database/forecast_v2_models.py",
        "src/database/tokenization_models.py",
        "src/database/valuation_models.py",
        "src/database/microloan_models.py",
        "src/database/sovereign_models.py",
        "src/database/investment_models.py",
        "src/database/etf_models.py",
    ],
    "5. Database — Auxiliary Models": [
        "src/database/legislative_models.py",
        "src/database/fx_models.py",
        "src/database/corridor_models.py",
        "src/database/alert_models.py",
        "src/database/reconciliation_models.py",
        "src/database/world_news_models.py",
        "src/database/engagement_models.py",
        "src/database/royalty_models.py",
    ],
    "6. Core Engines": [
        "src/engines/composite_engine.py",
        "src/engines/index_calculation.py",
        "src/engines/forecast_engine.py",
        "src/engines/transport_engine.py",
        "src/engines/risk_engine.py",
        "src/engines/valuation_engine.py",
    ],
    "7. CBDC Engines": [
        "src/engines/cbdc_ledger_engine.py",
        "src/engines/cbdc_monetary_policy_engine.py",
        "src/engines/cbdc_compliance_engine.py",
        "src/engines/cbdc_settlement_engine.py",
        "src/engines/cbdc_fx_engine.py",
        "src/engines/cbdc_payment_router.py",
        "src/engines/cbdc_ussd_engine.py",
    ],
    "8. Other Engines": [
        "src/engines/tokenization_engine.py",
        "src/engines/legislative_engine.py",
        "src/engines/fx_analytics_engine.py",
        "src/engines/corridor_engine.py",
        "src/engines/divergence_engine.py",
        "src/engines/ml_engine.py",
        "src/engines/ussd_engine.py",
        "src/engines/investment_engine.py",
        "src/engines/etf_engine.py",
        "src/engines/microloan_engine.py",
        "src/engines/sovereign_veto_engine.py",
        "src/engines/intelligence_engine.py",
        "src/engines/engagement_engine.py",
        "src/engines/royalty_engine.py",
        "src/engines/reconciliation_engine.py",
        "src/engines/world_news_engine.py",
    ],
    "9. Security & Utilities": [
        "src/utils/security.py",
        "src/utils/credits.py",
        "src/utils/ml_guardrails.py",
        "src/utils/cbdc_crypto.py",
        "src/utils/cbdc_audit.py",
        "src/utils/cbdc_cobol.py",
        "src/utils/periods.py",
        "src/utils/pagination.py",
        "src/utils/phone_hash.py",
        "src/utils/logging_config.py",
    ],
    "10. Middleware": [
        "src/middleware/x402_payment_verification.py",
        "src/middleware/request_id.py",
        "src/middleware/error_handler.py",
    ],
    "11. Auth & Core Routes": [
        "src/routes/auth.py",
        "src/routes/health.py",
        "src/routes/indices.py",
        "src/routes/composite.py",
        "src/routes/country.py",
        "src/routes/payment.py",
    ],
    "12. V2 Routes": [
        "src/routes/transport.py",
        "src/routes/bank.py",
        "src/routes/live_signals.py",
        "src/routes/data_admin.py",
        "src/routes/ussd.py",
        "src/routes/trade.py",
        "src/routes/markets.py",
    ],
    "13. V3 Routes — CBDC": [
        "src/routes/cbdc_wallet.py",
        "src/routes/cbdc_transaction.py",
        "src/routes/cbdc_admin.py",
        "src/routes/cbdc_monetary_policy.py",
        "src/routes/cbdc_payments.py",
    ],
    "14. V3 Routes — Financial": [
        "src/routes/forecast.py",
        "src/routes/tokenization.py",
        "src/routes/legislative.py",
        "src/routes/valuation.py",
        "src/routes/fx.py",
        "src/routes/microloan.py",
        "src/routes/sovereign.py",
        "src/routes/investment.py",
        "src/routes/etf.py",
    ],
    "15. V3 Routes — Intelligence & Ops": [
        "src/routes/risk.py",
        "src/routes/corridor.py",
        "src/routes/alerts.py",
        "src/routes/reconciliation.py",
        "src/routes/world_news.py",
        "src/routes/engagement.py",
        "src/routes/royalty.py",
        "src/routes/intelligence.py",
        "src/routes/public_terminal.py",
    ],
    "16. V4 Routes & Guardrails": [
        "src/routes/forecast_v4.py",
        "src/routes/v1_guardrails.py",
        "src/routes/data_truth_routes.py",
    ],
    "17. Schedulers & Tasks": [
        "src/tasks/composite_update.py",
        "src/tasks/wasi_data_scheduler.py",
        "src/tasks/data_ingestion.py",
        "src/tasks/news_sweep.py",
        "src/tasks/forecast_task.py",
        "src/tasks/forecast_v2_task.py",
        "src/tasks/ussd_aggregation.py",
        "src/tasks/tokenization_aggregation.py",
        "src/tasks/cbdc_monetary_policy_task.py",
        "src/tasks/cbdc_settlement_task.py",
        "src/tasks/cbdc_compliance_task.py",
        "src/tasks/engagement_task.py",
        "src/tasks/legislative_sweep.py",
        "src/tasks/fx_analytics_task.py",
        "src/tasks/fx_rate_update.py",
        "src/tasks/corridor_assessment.py",
        "src/tasks/reconciliation_task.py",
        "src/tasks/alert_evaluation.py",
    ],
    "18. Scrapers & Pipelines": [
        "src/pipelines/scrapers/resilience.py",
        "src/pipelines/scrapers/worldbank_scraper.py",
        "src/pipelines/scrapers/imf_scraper.py",
        "src/pipelines/scrapers/commodity_scraper.py",
        "src/pipelines/scrapers/comtrade_scraper.py",
        "src/pipelines/scrapers/acled_scraper.py",
        "src/pipelines/scrapers/fx_scraper.py",
        "src/pipelines/scrapers/legislative_scraper.py",
        "src/pipelines/scrapers/ngx_scraper.py",
        "src/pipelines/scrapers/gse_scraper.py",
        "src/pipelines/scrapers/brvm_scraper.py",
        "src/pipelines/scrapers/bceao_scraper.py",
    ],
    "19. Schemas": [
        "src/schemas/auth.py",
        "src/schemas/forecast.py",
        "src/schemas/forecast_v2.py",
        "src/schemas/ussd.py",
        "src/schemas/tokenization.py",
        "src/schemas/etf.py",
        "src/schemas/investment.py",
    ],
    "20. Infrastructure": [
        "requirements.txt",
        "Dockerfile",
        "docker-compose.yml",
        "render.yaml",
        "gunicorn.conf.py",
        "alembic.ini",
    ],
}

# ── Review prompts ────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a senior software architect reviewing the WASI (West African Shipping Index) platform.
This is a FastAPI + SQLAlchemy + APScheduler backend serving economic intelligence for 16 ECOWAS countries.

The platform includes:
- WASI composite index (weighted across 16 countries)
- eCFA CBDC digital currency (BCEAO monetary policy)
- Data scrapers (World Bank, IMF, ACLED, UN Comtrade, commodities)
- 42 ETF products, microloans, sovereign credit ratings
- USSD integration for feature phones
- Data tokenization (3 pillars: Citizen UBDI, Business CITD, Faso Meabo)
- ML guardrails (G1-G7), forecasting engine, engagement/gamification

For each batch of code you receive, provide a structured review:

## FINDINGS

For each issue found:
- **[CRITICAL/HIGH/MEDIUM/LOW]** Brief title
  - File: filename.py:line_number
  - Issue: What's wrong
  - Fix: How to fix it

## MISSING FUNCTIONALITY
- Features referenced but not implemented
- Dead code or placeholder stubs
- Broken cross-references between modules

## SECURITY CONCERNS
- Authentication/authorization gaps
- Input validation issues
- Data exposure risks

## ARCHITECTURE NOTES
- Design patterns that should be refactored
- Performance concerns
- Consistency issues

Be specific with line numbers. Don't flag style/formatting issues. Focus on bugs, security, missing logic, and architectural problems."""

BATCH_PROMPT = """Review this batch of WASI platform source code: **{group_name}**

{file_contents}

Provide your findings in the structured format described. Be specific with file names and line numbers. Only flag real issues — not style preferences."""

FINAL_PROMPT = """You have now reviewed all 20 batches of the WASI platform codebase. Here is a summary of your batch-level findings:

{all_findings}

Now provide a FINAL COMPREHENSIVE REPORT:

## EXECUTIVE SUMMARY
- Overall architecture assessment (1 paragraph)
- Production readiness score (1-10)
- Top 5 critical items to fix before production

## CROSS-CUTTING ISSUES
- Issues that span multiple modules
- Consistency problems across the codebase
- Integration gaps between components

## MISSING PIECES
- Features that appear planned but not implemented
- Dead endpoints or orphan code
- Database models without corresponding routes/engines

## PRIORITIZED ACTION PLAN
Numbered list of fixes ordered by impact (highest first), with estimated effort (S/M/L):
1. [CRITICAL] ... (effort: S)
2. [HIGH] ... (effort: M)
...

## WHAT'S DONE WELL
- Architectural strengths
- Good patterns worth keeping"""


def read_file_safe(filepath: str) -> str | None:
    """Read a file, return contents or None if missing."""
    full_path = PROJECT_ROOT / filepath
    if not full_path.exists():
        return None
    try:
        return full_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"# ERROR reading file: {e}"


def build_batch_content(group_name: str, files: list[str]) -> str:
    """Concatenate file contents for a batch."""
    parts = []
    for filepath in files:
        content = read_file_safe(filepath)
        if content is None:
            parts.append(f"\n### {filepath} — FILE NOT FOUND\n")
            continue
        # Truncate very large files to ~4000 lines to fit context
        lines = content.split("\n")
        if len(lines) > 4000:
            content = "\n".join(lines[:4000]) + f"\n# ... TRUNCATED ({len(lines)} total lines)"
        parts.append(f"\n### {filepath}\n```python\n{content}\n```\n")

    return "".join(parts)


def query_ollama(prompt: str, model: str, system: str = "") -> str:
    """Send a prompt to Ollama and return the response."""
    payload = {
        "model": model,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 4096,
            "num_ctx": 32768,
        },
    }

    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=600)
        resp.raise_for_status()
        return resp.json().get("response", "(empty response)")
    except requests.ConnectionError:
        return "ERROR: Cannot connect to Ollama. Is it running? (ollama serve)"
    except requests.Timeout:
        return "ERROR: Ollama request timed out (10 min limit). Try a smaller model."
    except Exception as e:
        return f"ERROR: {e}"


def main():
    parser = argparse.ArgumentParser(description="WASI Platform — Ollama Code Review")
    parser.add_argument("--model", default="llama3", help="Ollama model name (default: llama3)")
    parser.add_argument("--output", default="OLLAMA_REVIEW.md", help="Output file (default: OLLAMA_REVIEW.md)")
    parser.add_argument("--batch", type=int, default=0, help="Run only batch N (1-20). 0 = all.")
    parser.add_argument("--skip-final", action="store_true", help="Skip the final summary pass")
    args = parser.parse_args()

    print(f"WASI Ollama Review — model: {args.model}, output: {args.output}")
    print(f"Project root: {PROJECT_ROOT}")
    print()

    # Check Ollama is reachable
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=5)
        models = [m["name"] for m in r.json().get("models", [])]
        if not any(args.model in m for m in models):
            print(f"WARNING: Model '{args.model}' not found. Available: {', '.join(models)}")
            print(f"Pull it with: ollama pull {args.model}")
            sys.exit(1)
        print(f"Ollama connected. Available models: {', '.join(models)}")
    except Exception:
        print("ERROR: Cannot connect to Ollama at localhost:11434")
        print("Start it with: ollama serve")
        sys.exit(1)

    groups = list(FILE_GROUPS.items())
    if args.batch:
        if args.batch < 1 or args.batch > len(groups):
            print(f"ERROR: --batch must be 1-{len(groups)}")
            sys.exit(1)
        groups = [groups[args.batch - 1]]

    all_findings = []
    output_parts = [
        f"# WASI Platform — Ollama Code Review\n\n",
        f"**Model:** {args.model}  \n",
        f"**Date:** {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}  \n",
        f"**Batches:** {len(groups)} of {len(FILE_GROUPS)}  \n\n",
        "---\n\n",
    ]

    for i, (group_name, files) in enumerate(groups, 1):
        batch_num = args.batch if args.batch else i
        print(f"\n{'='*60}")
        print(f"BATCH {batch_num}/{len(FILE_GROUPS)}: {group_name}")
        print(f"Files: {', '.join(files)}")
        print(f"{'='*60}")

        content = build_batch_content(group_name, files)
        content_size = len(content)
        print(f"Content size: {content_size:,} chars")

        if content_size > 100_000:
            print(f"WARNING: Batch is very large ({content_size:,} chars). May exceed context window.")
            print("Consider using a model with 128k context (e.g., llama3.1:70b)")

        prompt = BATCH_PROMPT.format(group_name=group_name, file_contents=content)

        print("Sending to Ollama... (this may take 1-5 minutes per batch)")
        t0 = time.time()
        response = query_ollama(prompt, args.model, SYSTEM_PROMPT)
        elapsed = time.time() - t0
        print(f"Response received in {elapsed:.1f}s ({len(response):,} chars)")

        if response.startswith("ERROR:"):
            print(f"  {response}")

        all_findings.append(f"### Batch {batch_num}: {group_name}\n{response}")

        output_parts.append(f"## Batch {batch_num}: {group_name}\n\n")
        output_parts.append(f"*Files: {', '.join(files)}*\n\n")
        output_parts.append(response + "\n\n---\n\n")

    # Final comprehensive pass
    if not args.skip_final and not args.batch:
        print(f"\n{'='*60}")
        print("FINAL PASS: Cross-cutting analysis")
        print(f"{'='*60}")

        findings_text = "\n\n".join(all_findings)
        # Truncate if too long for context
        if len(findings_text) > 80_000:
            findings_text = findings_text[:80_000] + "\n\n... (truncated for context limit)"

        final_prompt = FINAL_PROMPT.format(all_findings=findings_text)

        print("Sending final analysis to Ollama... (may take 3-10 minutes)")
        t0 = time.time()
        final_response = query_ollama(final_prompt, args.model, SYSTEM_PROMPT)
        elapsed = time.time() - t0
        print(f"Final response received in {elapsed:.1f}s")

        output_parts.append("## FINAL COMPREHENSIVE REPORT\n\n")
        output_parts.append(final_response + "\n")

    # Write output
    output_path = PROJECT_ROOT / args.output
    output_path.write_text("".join(output_parts), encoding="utf-8")
    print(f"\nReview saved to: {output_path}")
    print(f"Total size: {output_path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
