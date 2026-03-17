import subprocess, sys

msg = """feat: complete Phase 7-11 - interaction, charts, alerts, performance, weekly report

Phase 7: interaction UX (deep-analysis jump, market overview bar, SSE progress, card collapse)
Phase 8: Chart.js visualization (profitability/growth/safety charts, valuation band, sparkline)
Phase 9: alert system (AlertRule model, CRUD API, checker engine, Telegram push, scheduler)
Phase 10: performance dashboard (win rate, profit factor, daily trend chart, multi-stock compare)
Phase 11: weekly report + data sources (announcement, fund flow, LLM prompt integration)

All 100 tasks in INTEGRATION_PLAN.md completed."""

subprocess.run(["git", "add", "-A"], check=True)
result = subprocess.run(["git", "commit", "-m", msg], capture_output=True, text=True)
print(result.stdout)
if result.returncode != 0:
    print(result.stderr)
    sys.exit(result.returncode)
