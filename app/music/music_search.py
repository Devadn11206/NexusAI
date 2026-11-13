"""
NEXUS AI - Cross-Platform Music Search, Metadata Resolver & Lyrics Finder
"""

import urllib.parse
import httpx
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class MusicSearchEngine:
    """Provides song search across streaming platforms and lyrics lookup."""

    @staticmethod
    def resolve_search_url(service: str, query: str) -> str:
        q_enc = urllib.parse.quote_plus(query)
        srv = service.lower().replace("-", "_")
        if "spotify" in srv:
            return f"https://open.spotify.com/search/{q_enc}"
        elif "soundcloud" in srv:
            return f"https://soundcloud.com/search?q={q_enc}"
        else:
            return f"https://music.youtube.com/search?q={q_enc}"

    @staticmethod
    async def get_lyrics(track_title: str, artist: str = "") -> Dict[str, Any]:
        """
        Fetches lyrics from public lyrics API (e.g. lyrics.ovh or fallback).
        """
        clean_title = urllib.parse.quote(track_title.split("(")[0].strip())
        clean_artist = urllib.parse.quote(artist.strip()) if artist else ""

        if clean_artist:
            url = f"https://api.lyrics.ovh/v1/{clean_artist}/{clean_title}"
            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        lyrics = resp.json().get("lyrics", "")
                        return {"status": "success", "lyrics": lyrics[:1500]}
            except Exception as e:
                logger.debug(f"[MusicSearch] Lyrics fetch error: {e}")

        return {
            "status": "unavailable",
            "message": f"Lyrics for '{track_title}' could not be fetched automatically.",
        }


music_search = MusicSearchEngine()

