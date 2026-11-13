"""
NEXUS AI - Autonomous Scheduler & Background Cron Engine
Manages scheduled background jobs and persistent recurring workflows.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime

from app.config import settings
from app.core.security import resolve_safe_workspace_path

logger = logging.getLogger(__name__)


class CronSchedulerEngine:
    """
    Asynchronous cron engine that manages recurring tasks,
    loads scheduled triggers from ./workspace/config/cron_tasks.json,
    and dispatches execution tasks into the background.
    """

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = (
            Path(config_path) if config_path else resolve_safe_workspace_path("config/cron_tasks.json")
        )
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._is_active = False
        self._registered_jobs: Dict[str, Dict[str, Any]] = {}

    def load_scheduled_jobs(self) -> List[Dict[str, Any]]:
        """Reads persistent cron tasks from JSON configuration."""
        if not self.config_path.exists():
            return []
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                jobs = json.load(f)
                return jobs if isinstance(jobs, list) else []
        except Exception as exc:
            logger.error(f"[SchedulerEngine] Failed reading cron config: {exc}")
            return []

    def save_scheduled_jobs(self, jobs: List[Dict[str, Any]]) -> None:
        """Persists cron tasks into JSON configuration."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(jobs, f, indent=2)

    def register_job(
        self,
        job_id: str,
        name: str,
        interval_seconds: int,
        handler: Callable[[], Any],
        description: str = "",
    ) -> None:
        """Registers an in-memory job with recurring interval."""
        self._registered_jobs[job_id] = {
            "name": name,
            "interval": interval_seconds,
            "handler": handler,
            "description": description,
            "last_run": None,
        }
        logger.info(f"[SchedulerEngine] Registered job '{job_id}' (every {interval_seconds}s)")

    async def _job_runner_loop(self, job_id: str, interval_seconds: int, handler: Callable[[], Any]):
        """Runs periodic job execution loop asynchronously."""
        while self._is_active:
            try:
                await asyncio.sleep(interval_seconds)
                if not self._is_active:
                    break
                logger.info(f"[SchedulerEngine] Executing cron job: '{job_id}'")
                res = handler()
                if asyncio.iscoroutine(res):
                    await res
                if job_id in self._registered_jobs:
                    self._registered_jobs[job_id]["last_run"] = datetime.utcnow().isoformat()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"[SchedulerEngine] Error executing job '{job_id}': {exc}", exc_info=True)

    def start(self) -> None:
        """Starts all registered background scheduler loops."""
        if self._is_active:
            return
        self._is_active = True
        for j_id, j_info in self._registered_jobs.items():
            task = asyncio.create_task(
                self._job_runner_loop(j_id, j_info["interval"], j_info["handler"])
            )
            self._running_tasks[j_id] = task
        logger.info(f"[SchedulerEngine] Cron scheduler started with {len(self._running_tasks)} active loops.")

    def stop(self) -> None:
        """Stops all running scheduler loops cleanly."""
        self._is_active = False
        for j_id, task in self._running_tasks.items():
            task.cancel()
        self._running_tasks.clear()
        logger.info("[SchedulerEngine] Cron scheduler stopped.")


scheduler_engine = CronSchedulerEngine()

