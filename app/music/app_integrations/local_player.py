"""
NEXUS AI - Local Windows Media Library Scanner & Player
Indexes local music folders (~/Music) and reads ID3 metadata via mutagen.
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class LocalPlayerIntegration:
    """Discovers and plays local audio files on Windows."""

    def __init__(self, music_dir: Optional[str] = None):
        user_music = Path(os.environ.get("USERPROFILE", "")) / "Music"
        self.music_dir = Path(music_dir) if music_dir else user_music

    def scan_library(self, max_tracks: int = 100) -> List[Dict[str, Any]]:
        """Scans local music directory for mp3, flac, wav files and extracts tags."""
        tracks = []
        if not self.music_dir.exists():
            return tracks

        exts = {".mp3", ".flac", ".wav", ".m4a"}
        for f in self.music_dir.rglob("*"):
            if f.suffix.lower() in exts and f.is_file():
                title = f.stem
                artist = "Unknown Artist"
                album = ""
                try:
                    import mutagen
                    meta = mutagen.File(str(f), easy=True)
                    if meta:
                        title = meta.get("title", [title])[0]
                        artist = meta.get("artist", [artist])[0]
                        album = meta.get("album", [""])[0]
                except Exception:
                    pass

                tracks.append({
                    "title": title,
                    "artist": artist,
                    "album": album,
                    "path": str(f),
                    "filename": f.name,
                })
                if len(tracks) >= max_tracks:
                    break
        return tracks

    def play(self, file_path_or_query: str) -> Dict[str, Any]:
        """Plays a local file by path or name search."""
        target_file = None
        p = Path(file_path_or_query)
        if p.exists() and p.is_file():
            target_file = p
        else:
            # Search by title query
            library = self.scan_library()
            q = file_path_or_query.lower()
            for item in library:
                if q in item["title"].lower() or q in item["artist"].lower():
                    target_file = Path(item["path"])
                    break

        if target_file and target_file.exists():
            os.startfile(str(target_file))
            return {"status": "success", "player": "local", "file": target_file.name}

        return {"status": "not_found", "query": file_path_or_query}


local_player_integration = LocalPlayerIntegration()
