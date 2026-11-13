"""
NEXUS AI - AI Personal DJ & Multi-Hour Playlist Recommendation Engine
Synthesizes user context, mood, era, language, and listening memory into cohesive tracklists.
"""

import logging
from typing import Dict, Any, List, Optional
from app.music.mood_detector import mood_detector
from app.music.music_memory import music_memory

logger = logging.getLogger(__name__)

# Curated high-quality seed database for instant, zero-latency local generation
DJ_SEED_CATALOG = {
    "focus": {
        "english": [
            {"title": "Weightless", "artist": "Marconi Union", "duration_sec": 480},
            {"title": "Daydream in Blue", "artist": "I Monster", "duration_sec": 220},
            {"title": "Intro", "artist": "The xx", "duration_sec": 127},
            {"title": "Resonance", "artist": "HOME", "duration_sec": 212},
            {"title": "First Breath After Coma", "artist": "Explosions In The Sky", "duration_sec": 578},
            {"title": "Night Owl", "artist": "Galimatias", "duration_sec": 210},
            {"title": "Clair de Lune", "artist": "Flight Facilities", "duration_sec": 458},
            {"title": "A Walk", "artist": "Tycho", "duration_sec": 316},
        ],
        "tamil": [
            {"title": "Nenjukkul Peidhidum (Instrumental)", "artist": "Harris Jayaraj", "duration_sec": 340},
            {"title": "Enna Solla (Lo-Fi)", "artist": "Anirudh Ravichander", "duration_sec": 215},
            {"title": "Moongil Thottam (Acoustic)", "artist": "A.R. Rahman", "duration_sec": 270},
            {"title": "Marakkuma Nenjam", "artist": "A.R. Rahman", "duration_sec": 254},
            {"title": "Kannazhaga (Chill Mix)", "artist": "Anirudh Ravichander", "duration_sec": 210},
        ],
        "hindi": [
            {"title": "Kun Faya Kun (Instrumental)", "artist": "A.R. Rahman", "duration_sec": 470},
            {"title": "Kabira (Acoustic Chill)", "artist": "Pritam", "duration_sec": 230},
            {"title": "Ilahi (Guitar Theme)", "artist": "Pritam", "duration_sec": 210},
            {"title": "Ghar (Reprise)", "artist": "Pritam", "duration_sec": 220},
        ]
    },
    "workout": {
        "english": [
            {"title": "Till I Collapse", "artist": "Eminem", "duration_sec": 298},
            {"title": "Stronger", "artist": "Kanye West", "duration_sec": 311},
            {"title": "Can't Hold Us", "artist": "Macklemore & Ryan Lewis", "duration_sec": 258},
            {"title": "Eye of the Tiger", "artist": "Survivor", "duration_sec": 245},
            {"title": "Lose Yourself", "artist": "Eminem", "duration_sec": 326},
        ],
        "tamil": [
            {"title": "Hukum - Thalaivar Alappara", "artist": "Anirudh Ravichander", "duration_sec": 207},
            {"title": "Badass", "artist": "Anirudh Ravichander", "duration_sec": 229},
            {"title": "Vaathi Coming", "artist": "Anirudh Ravichander", "duration_sec": 230},
            {"title": "Aaluma Doluma", "artist": "Anirudh Ravichander", "duration_sec": 260},
        ]
    },
    "chill": {
        "english": [
            {"title": "Sunset Lover", "artist": "Petit Biscuit", "duration_sec": 237},
            {"title": "Coffee", "artist": "beabadoobee", "duration_sec": 126},
            {"title": "Space Song", "artist": "Beach House", "duration_sec": 320},
            {"title": "Sunflower", "artist": "Rex Orange County", "duration_sec": 252},
        ],
        "tamil": [
            {"title": "Kadhale Kadhale", "artist": "Govind Vasantha", "duration_sec": 195},
            {"title": "The Life of Ram", "artist": "Govind Vasantha", "duration_sec": 345},
            {"title": "Unakkenna Venum Sollu", "artist": "Harris Jayaraj", "duration_sec": 308},
        ]
    }
}


class RecommendationEngine:
    """Orchestrates AI-driven playlist creation matching target duration and mood profile."""

    def __init__(self):
        pass

    def generate_ai_playlist(self, prompt: str, duration_minutes: Optional[int] = None) -> Dict[str, Any]:
        """
        Decomposes request into a curated, ordered tracklist that fills the target duration.
        """
        profile = mood_detector.detect_mood_and_context(prompt)
        target_mins = duration_minutes or profile.get("duration_minutes", 60)
        target_seconds = target_mins * 60

        mood = profile.get("mood", "focus")
        lang = profile.get("language", "english")

        # Select pool of candidate tracks
        pool = DJ_SEED_CATALOG.get(mood, {}).get(lang, [])
        if not pool:
            # Fallback to English focus if combination isn't found
            pool = DJ_SEED_CATALOG.get(mood, {}).get("english") or DJ_SEED_CATALOG["focus"]["english"]

        # Fill tracklist until reaching or slightly exceeding target duration
        tracklist: List[Dict[str, Any]] = []
        accumulated_sec = 0
        pool_idx = 0

        while accumulated_sec < target_seconds and pool:
            seed = pool[pool_idx % len(pool)]
            track = {
                "title": seed["title"],
                "artist": seed["artist"],
                "duration_sec": seed["duration_sec"],
                "query": f"{seed['title']} {seed['artist']}",
                "track_index": len(tracklist) + 1,
            }
            tracklist.append(track)
            accumulated_sec += seed["duration_sec"]
            pool_idx += 1

        hours = round(accumulated_sec / 3600, 1)
        logger.info(f"[DJEngine] Built {len(tracklist)}-track playlist for '{prompt}' ({hours} hrs).")

        return {
            "status": "success",
            "playlist_name": f"{profile['mood'].title()} Session ({profile['language'].title()})",
            "prompt": prompt,
            "mood": mood,
            "language": lang,
            "target_duration_minutes": target_mins,
            "actual_duration_seconds": accumulated_sec,
            "track_count": len(tracklist),
            "tracks": tracklist,
        }


recommendation_engine = RecommendationEngine()

