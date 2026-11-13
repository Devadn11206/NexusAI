"""
NEXUS AI - Unified Telegram Gateway & Bridge
Delegates entirely to app.gateway.telegram_poller for comprehensive 6-Module Hub control.
"""

from app.gateway.telegram_poller import run_poller
import asyncio

if __name__ == "__main__":
    asyncio.run(run_poller())


