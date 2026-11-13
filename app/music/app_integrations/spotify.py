"""
NEXUS AI - Spotify Player Integration
Supports Spotify Web API (via spotipy) with seamless fallback to DRM-enabled Chrome Playwright.
"""

import os
import logging
from typing import Dict, Any, Optional
from app.tools.browser import BrowserEngine

logger = logging.getLogger(__name__)


class SpotifyIntegration:
    """Manages playback through Spotify API or persistent Widevine Chrome instance."""

    def __init__(self):
        self.client_id = os.getenv("SPOTIFY_CLIENT_ID")
        self.client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        self.sp = None
        if self.client_id and self.client_secret:
            try:
                import spotipy
                from spotipy.oauth2 import SpotifyOAuth
                self.sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
                    client_id=self.client_id,
                    client_secret=self.client_secret,
                    redirect_uri="http://localhost:8888/callback",
                    scope="user-modify-playback-state user-read-playback-state",
                ))
            except Exception as e:
                logger.info(f"[Spotify] Spotipy auth init note: {e}")

    async def play(self, query: Optional[str] = None) -> Dict[str, Any]:
        """Plays track via Spotify Web API or visual Chrome browser."""
        if self.sp:
            try:
                if query:
                    results = self.sp.search(q=query, limit=1, type="track")
                    items = results.get("tracks", {}).get("items", [])
                    if items:
                        uri = items[0]["uri"]
                        self.sp.start_playback(uris=[uri])
                        return {"status": "success", "player": "spotify_api", "track": items[0]["name"]}
                else:
                    self.sp.start_playback()
                    return {"status": "success", "player": "spotify_api", "action": "resume"}
            except Exception as exc:
                logger.warning(f"[Spotify] Web API playback failed ({exc}); falling back to Chrome.")

        # Fallback to BrowserEngine
        engine = BrowserEngine(headless=False)
        return await engine.play_web_music(service="spotify", query=query)


spotify_integration = SpotifyIntegration()

