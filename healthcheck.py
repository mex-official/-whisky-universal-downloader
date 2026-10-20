"""Container health check: verifies configuration, not Telegram reachability."""
import os, sys
if os.getenv("TELEGRAM_BOT_TOKEN", "").strip():
    print("CONFIGURED")
    raise SystemExit(0)
print("NOT_CONFIGURED: TELEGRAM_BOT_TOKEN is missing")
raise SystemExit(1)
