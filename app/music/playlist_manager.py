"""
NEXUS AI - Playlist & Playback Queue Manager
Manages active queue state, track transitions, shuffling, repeat modes, and persistence.
"""

import random
from typing import Dict, Any, List, Optional
from app.music.music_memory import music_memory


class PlaylistManager:
    """Maintains active playback queue and tracks order."""

    def __init__(self):
        self._queue: List[Dict[str, Any]] = []
        self._current_index: int = 0
        self._shuffle: bool = False
        self._repeat_mode: str = "off"  # 'off', 'all', 'one'

    def set_queue(self, tracks: List[Dict[str, Any]], start_index: int = 0) -> None:
        self._queue = list(tracks)
        self._current_index = max(0, min(len(self._queue) - 1, start_index))

    def add_to_queue(self, track: Dict[str, Any], play_next: bool = False) -> None:
        if play_next and self._queue:
            self._queue.insert(self._current_index + 1, track)
        else:
            self._queue.append(track)

    def get_current_track(self) -> Optional[Dict[str, Any]]:
        if 0 <= self._current_index < len(self._queue):
            return self._queue[self._current_index]
        return None

    def get_queue(self) -> List[Dict[str, Any]]:
        return list(self._queue)

    def next_track(self) -> Optional[Dict[str, Any]]:
        if not self._queue:
            return None
        if self._repeat_mode == "one":
            return self.get_current_track()
        if self._shuffle:
            self._current_index = random.randint(0, len(self._queue) - 1)
        else:
            self._current_index += 1
            if self._current_index >= len(self._queue):
                if self._repeat_mode == "all":
                    self._current_index = 0
                else:
                    self._current_index = len(self._queue)
                    return None
        return self.get_current_track()

    def previous_track(self) -> Optional[Dict[str, Any]]:
        if not self._queue:
            return None
        if self._current_index > 0:
            self._current_index -= 1
        return self.get_current_track()

    def set_shuffle(self, enable: bool) -> None:
        self._shuffle = enable

    def set_repeat(self, mode: str) -> None:
        self._repeat_mode = mode if mode in ("off", "all", "one") else "off"

    def get_state(self) -> Dict[str, Any]:
        return {
            "queue_length": len(self._queue),
            "current_index": self._current_index,
            "current_track": self.get_current_track(),
            "shuffle": self._shuffle,
            "repeat": self._repeat_mode,
        }


playlist_manager = PlaylistManager()

