"""
NEXUS AI - Music Listening History, Skip Tracking & Favorite Memory
Persisted in ./workspace/memory/music_memory.db via SQLite.
"""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from app.core.security import resolve_safe_workspace_path

logger = logging.getLogger(__name__)


class MusicMemory:
    """Manages listening habits, playback tracking, skips, and favorite artists/genres."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = (
            Path(db_path) if db_path else resolve_safe_workspace_path("memory/music_memory.db")
        )
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS listening_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    artist TEXT,
                    album TEXT,
                    service TEXT,
                    duration_sec INTEGER DEFAULT 0,
                    completed INTEGER DEFAULT 1,
                    skipped INTEGER DEFAULT 0,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS favorites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_type TEXT NOT NULL, -- 'track', 'artist', 'genre', 'language'
                    item_value TEXT NOT NULL UNIQUE,
                    play_count INTEGER DEFAULT 1,
                    rating INTEGER DEFAULT 5,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def log_playback(
        self,
        title: str,
        artist: str = "Unknown Artist",
        album: str = "",
        service: str = "youtube_music",
        duration_sec: int = 180,
        completed: bool = True,
        skipped: bool = False,
    ) -> int:
        """Records a played track and updates favorite artist/track metrics."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO listening_history (title, artist, album, service, duration_sec, completed, skipped)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (title, artist, album, service, duration_sec, 1 if completed else 0, 1 if skipped else 0))
            hist_id = cursor.lastrowid

            if not skipped and artist and artist != "Unknown Artist":
                cursor.execute("""
                    INSERT INTO favorites (item_type, item_value, play_count)
                    VALUES ('artist', ?, 1)
                    ON CONFLICT(item_value) DO UPDATE SET
                        play_count = play_count + 1,
                        updated_at = CURRENT_TIMESTAMP
                """, (artist,))

            conn.commit()
            return hist_id

    def log_skip(self, title: str, artist: str = "") -> None:
        """Records a skip event for recommendation penalization."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE listening_history
                SET skipped = 1, completed = 0
                WHERE id = (
                    SELECT id FROM listening_history
                    WHERE title = ? ORDER BY id DESC LIMIT 1
                )
            """, (title,))
            conn.commit()

    def get_recent_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Returns the most recent listening entries."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, title, artist, album, service, completed, skipped, timestamp
                FROM listening_history
                ORDER BY id DESC LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def get_top_artists(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Returns top favored artists ranked by play frequency."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT item_value AS artist, play_count
                FROM favorites
                WHERE item_type = 'artist'
                ORDER BY play_count DESC LIMIT ?
            """, (limit,))
            return [dict(r) for r in cursor.fetchall()]

    def get_preference_summary(self) -> Dict[str, Any]:
        """Provides high-level stats for LLM personal DJ prompt grounding."""
        recent = self.get_recent_history(limit=5)
        top_art = self.get_top_artists(limit=5)
        return {
            "recent_tracks": [f"{r['title']} - {r['artist']}" for r in recent],
            "top_artists": [a["artist"] for a in top_art],
        }


music_memory = MusicMemory()

