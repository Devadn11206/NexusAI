"""
NEXUS AI - Natural Language Music Mood & Intent Detector
Maps conversational queries to musical attributes, genres, tempos, eras, and languages.
"""

import re
from typing import Dict, Any, List

# Keyword maps
MOOD_KEYWORDS = {
    "focus": ["focus", "study", "code", "work", "deep work", "programming", "reading", "machine learning", "ml"],
    "chill": ["chill", "relax", "relaxing", "calm", "peaceful", "unwind", "lofi", "ambient", "night", "sleep"],
    "workout": ["workout", "gym", "cardio", "pump", "energy", "energetic", "motivation", "running", "fitness"],
    "party": ["party", "dance", "celebrate", "club", "upbeat", "banger", "fun"],
    "melancholic": ["sad", "heartbreak", "rainy", "emotional", "crying", "alone", "blues"],
    "acoustic": ["acoustic", "unplugged", "coffee", "indie", "folk", "guitar"],
}

ERA_KEYWORDS = {
    "2020s": ["2020s", "recent", "latest", "trending", "viral", "new"],
    "2010s": ["2010s", "2010", "2012", "2015", "edm era"],
    "2000s": ["2000s", "y2k", "2000", "nostalgia", "throwback"],
    "90s": ["90s", "1990s", "golden era", "grunge"],
    "80s": ["80s", "1980s", "synthwave", "retro"],
}

LANGUAGE_KEYWORDS = {
    "tamil": ["tamil", "anirudh", "ar rahman", "yuvan", "kollywood", "harris jayaraj"],
    "hindi": ["hindi", "bollywood", "arijit", "pritam", "shreya", "neha", "badshah"],
    "punjabi": ["punjabi", "diljit", "sidhu", "ap dhillon", "karan aujla"],
    "telugu": ["telugu", "tollywood", "thaman", "devi sri prasad", "dsp"],
    "malayalam": ["malayalam", "mollywood", "sushin shyam"],
    "korean": ["k-pop", "kpop", "bts", "blackpink", "newjeans"],
    "english": ["english", "hollywood", "pop", "hip hop", "rock"],
}


class MoodDetector:
    """Analyzes text prompts to extract music mood, era, language, and activity context."""

    @staticmethod
    def detect_mood_and_context(prompt: str) -> Dict[str, Any]:
        p_lower = prompt.lower()

        # Detect Mood
        detected_mood = "focus"
        for mood, terms in MOOD_KEYWORDS.items():
            if any(term in p_lower for term in terms):
                detected_mood = mood
                break

        # Detect Era
        detected_era = "2020s"
        for era, terms in ERA_KEYWORDS.items():
            if any(term in p_lower for term in terms):
                detected_era = era
                break

        # Detect Language/Region
        detected_lang = "english"
        for lang, terms in LANGUAGE_KEYWORDS.items():
            if any(term in p_lower for term in terms):
                detected_lang = lang
                break

        # Extract duration if specified (e.g., "2-hour", "30 minutes")
        duration_minutes = 60
        match_hours = re.search(r'(\d+)\s*(?:hour|hr)', p_lower)
        if match_hours:
            duration_minutes = int(match_hours.group(1)) * 60
        else:
            match_mins = re.search(r'(\d+)\s*(?:min|minute)', p_lower)
            if match_mins:
                duration_minutes = int(match_mins.group(1))

        return {
            "mood": detected_mood,
            "era": detected_era,
            "language": detected_lang,
            "duration_minutes": duration_minutes,
            "raw_prompt": prompt,
        }


mood_detector = MoodDetector()

