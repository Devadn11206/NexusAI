"""
NEXUS AI - Music Sleep Timer, Wake-Up Music & Automation Guards
Provides:
1. APScheduler Sleep Timer with volume fade-out.
2. Meeting app & active microphone auto-pause guard.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.music.audio_controller import audio_controller
from app.tools.computer import control_music_playback

logger = logging.getLogger(__name__)


class SleepTimerManager:
    """Manages timed audio shutdown with progressive fade-out."""

    def __init__(self):
        self._scheduler: Optional[AsyncIOScheduler] = None
        self._active_timer_end: Optional[datetime] = None

    def _get_scheduler(self) -> AsyncIOScheduler:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if self._scheduler is None or self._scheduler._eventloop != loop or self._scheduler._eventloop.is_closed():
            if self._scheduler and self._scheduler.running:
                try:
                    self._scheduler.shutdown(wait=False)
                except Exception:
                    pass
            self._scheduler = AsyncIOScheduler(event_loop=loop)
            self._scheduler.start()
        elif not self._scheduler.running:
            self._scheduler.start()
        return self._scheduler

    async def _fade_out_and_pause(self):
        """Gradually fades out volume over 15 seconds then pauses music."""
        logger.info("[SleepTimer] Fading out music volume...")
        current_vol = audio_controller.get_master_volume()
        steps = 5
        delay = 2.0
        step_decrement = current_vol / steps

        for i in range(steps):
            new_vol = max(0, int(current_vol - (i + 1) * step_decrement))
            audio_controller.set_master_volume(new_vol)
            await asyncio.sleep(delay)

        await control_music_playback(action="pause")
        # Restore volume level to baseline so system is not permanently muted
        audio_controller.set_master_volume(int(current_vol))
        self._active_timer_end = None
        logger.info("[SleepTimer] Playback paused cleanly by sleep timer.")

    def set_sleep_timer(self, minutes: int) -> Dict[str, Any]:
        """Schedules a fade-out shutdown in `minutes`."""
        scheduler = self._get_scheduler()
        run_time = datetime.now() + timedelta(minutes=minutes)
        self._active_timer_end = run_time

        scheduler.add_job(
            self._fade_out_and_pause,
            "date",
            run_date=run_time,
            id="music_sleep_timer",
            replace_existing=True,
        )
        logger.info(f"[SleepTimer] Set for {minutes} minutes (stopping at {run_time.strftime('%H:%M:%S')})")
        return {
            "status": "scheduled",
            "minutes": minutes,
            "stops_at": run_time.isoformat(),
        }

    def cancel_sleep_timer(self) -> Dict[str, Any]:
        scheduler = self._get_scheduler()
        job = scheduler.get_job("music_sleep_timer")
        if job or self._active_timer_end is not None:
            if job:
                try:
                    scheduler.remove_job("music_sleep_timer")
                except Exception:
                    pass
            self._active_timer_end = None
            return {"status": "cancelled"}
        return {"status": "not_active"}

    def get_status(self) -> Dict[str, Any]:
        return {
            "active": self._active_timer_end is not None,
            "stops_at": self._active_timer_end.isoformat() if self._active_timer_end else None,
        }


sleep_timer_manager = SleepTimerManager()
