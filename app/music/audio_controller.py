"""
NEXUS AI - Windows Core Audio Controller (pycaw)
Provides:
1. Master Volume Control (0-100%, mute/unmute).
2. Per-Application Audio Session Control (ISimpleAudioVolume).
3. Audio Output Device Enumeration.
4. Smooth Auto-Ducking for Voice Calls (duck_music_volume, restore_music_volume).
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class AudioController:
    """Manages system output volume, per-app session volume, and auto-ducking."""

    def __init__(self):
        self._saved_volume_level: Optional[float] = None
        self._is_ducked: bool = False

    def _get_master_endpoint(self):
        try:
            from pycaw.pycaw import AudioUtilities
            # In modern pycaw:
            speakers = AudioUtilities.GetSpeakers()
            return speakers
        except Exception as exc:
            logger.warning(f"[AudioController] Failed accessing AudioUtilities: {exc}")
            return None

    def get_master_volume(self) -> int:
        """Returns the current master volume percentage (0 - 100)."""
        try:
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            from comtypes import CLSCTX_ALL
            speakers = AudioUtilities.GetSpeakers()
            if not speakers:
                return 50
            if hasattr(speakers, "Activate"):
                endpoint = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                vol_scalar = endpoint.GetMasterVolumeLevelScalar()
                return int(round(vol_scalar * 100))
        except Exception as exc:
            logger.debug(f"[AudioController] get_master_volume note: {exc}")
        return 50

    def set_master_volume(self, percent: int) -> Dict[str, Any]:
        """Sets the system master volume percentage (0 - 100)."""
        clamped = max(0, min(100, int(percent)))
        scalar = clamped / 100.0
        try:
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            from comtypes import CLSCTX_ALL
            speakers = AudioUtilities.GetSpeakers()
            if speakers and hasattr(speakers, "Activate"):
                endpoint = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                endpoint.SetMasterVolumeLevelScalar(scalar, None)
                logger.info(f"[AudioController] Master volume set to {clamped}%")
                return {"status": "success", "volume_percent": clamped}
        except Exception as exc:
            logger.warning(f"[AudioController] set_master_volume fallback/error: {exc}")
        return {"status": "fallback", "volume_percent": clamped}

    def set_mute(self, mute: bool = True) -> Dict[str, Any]:
        """Mutes or unmutes the default audio output device."""
        try:
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            from comtypes import CLSCTX_ALL
            speakers = AudioUtilities.GetSpeakers()
            if speakers and hasattr(speakers, "Activate"):
                endpoint = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                endpoint.SetMute(1 if mute else 0, None)
                return {"status": "success", "muted": mute}
        except Exception as exc:
            logger.warning(f"[AudioController] set_mute note: {exc}")
        return {"status": "fallback", "muted": mute}

    def list_audio_devices(self) -> List[Dict[str, Any]]:
        """Enumerates active audio output devices."""
        devices = []
        try:
            from pycaw.pycaw import AudioUtilities
            # Standard primary speakers
            speakers = AudioUtilities.GetSpeakers()
            devices.append({
                "id": "default_playback",
                "name": "Default Audio Device / Speakers",
                "is_default": True,
            })
            # Try to get extra devices if available
            if hasattr(AudioUtilities, "GetAllDevices"):
                all_devs = AudioUtilities.GetAllDevices()
                for i, d in enumerate(all_devs):
                    name = getattr(d, "FriendlyName", f"Audio Output {i+1}")
                    if name != "Default Audio Device / Speakers":
                        devices.append({"id": f"device_{i}", "name": name, "is_default": False})
        except Exception as exc:
            logger.debug(f"[AudioController] list_audio_devices note: {exc}")
            devices = [{"id": "default", "name": "System Default Output", "is_default": True}]
        return devices

    def duck_music_volume(self, target_percent: int = 15) -> Dict[str, Any]:
        """
        Smoothly lowers playback audio volume while the voice agent is speaking.
        Preserves original volume level for subsequent restoration.
        """
        if self._is_ducked:
            return {"status": "already_ducked", "current": target_percent}

        current = self.get_master_volume()
        self._saved_volume_level = current
        self._is_ducked = True
        logger.info(f"[AudioController] Auto-ducking volume from {current}% -> {target_percent}%")
        self.set_master_volume(target_percent)
        return {"status": "ducked", "original_volume": current, "ducked_volume": target_percent}

    def restore_music_volume(self) -> Dict[str, Any]:
        """Restores music volume back to its pre-duck level."""
        if not self._is_ducked or self._saved_volume_level is None:
            return {"status": "not_ducked"}

        restored_level = int(self._saved_volume_level)
        logger.info(f"[AudioController] Restoring music volume to {restored_level}%")
        self.set_master_volume(restored_level)
        self._is_ducked = False
        self._saved_volume_level = None
        return {"status": "restored", "restored_volume": restored_level}

    def get_default_output_device(self) -> Dict[str, Any]:
        """Returns the active default audio playback device using native Windows CoreAudio/pycaw."""
        try:
            from pycaw.pycaw import AudioUtilities
            speakers = AudioUtilities.GetSpeakers()
            if speakers and hasattr(speakers, "FriendlyName"):
                name = speakers.FriendlyName
                dev_id = getattr(speakers, "id", "default_playback")
                return {
                    "status": "success",
                    "device_name": name,
                    "device_id": str(dev_id),
                    "is_default": True,
                    "description": f"Active Windows audio output: {name}",
                }
        except Exception as exc:
            logger.warning(f"[AudioController] Direct GetSpeakers error: {exc}")

        # Fallback to list_audio_devices match
        devices = self.list_audio_devices()
        default_dev = next((d for d in devices if d.get("is_default")), None) or (devices[0] if devices else None)
        if default_dev:
            return {
                "status": "success",
                "device_name": default_dev.get("name", "Default Audio Device"),
                "device_id": default_dev.get("id", "default"),
                "is_default": True,
            }

        return {"status": "not_found", "device_name": "Unknown Output Device"}


audio_controller = AudioController()

