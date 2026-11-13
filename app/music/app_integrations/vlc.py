"""
NEXUS AI - VLC Media Player Integration
Provides local file playback & stream control via python-vlc or subprocess.
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class VLCIntegration:
    """Manages VLC playback instance."""

    def __init__(self):
        self._player = None
        try:
            import vlc
            self._instance = vlc.Instance("--no-xlib" if hasattr(vlc, "Instance") else "")
            self._player = self._instance.media_player_new()
        except Exception as e:
            logger.debug(f"[VLC] VLC native player not available: {e}")

    def play_file(self, file_path: str) -> Dict[str, Any]:
        p = Path(file_path)
        if not p.exists():
            return {"status": "failed", "error": f"File not found: {file_path}"}

        if self._player:
            try:
                import vlc
                media = self._instance.media_new(str(p))
                self._player.set_media(media)
                self._player.play()
                return {"status": "success", "player": "vlc", "file": p.name}
            except Exception as e:
                logger.warning(f"[VLC] Play failed: {e}")

        # Fallback to os default startfile for local media
        import os
        os.startfile(str(p))
        return {"status": "success", "player": "system_default", "file": p.name}

    def pause(self) -> Dict[str, Any]:
        if self._player:
            self._player.pause()
            return {"status": "success", "action": "pause"}
        return {"status": "unsupported"}

    def stop(self) -> Dict[str, Any]:
        if self._player:
            self._player.stop()
            return {"status": "success", "action": "stop"}
        return {"status": "unsupported"}


vlc_integration = VLCIntegration()

