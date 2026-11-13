"""
NEXUS AI - Upstream Gemini Multimodal Live API Session & Tool Router
Handles bidirectional WebSocket audio streaming (16kHz PCM in, 24kHz PCM out),
dispatches real-time laptop function calls, and handles barge-in interruptions.
"""

import asyncio
import base64
import json
import logging
from typing import Dict, Any, List, Optional, Callable
import websockets

from app.config import settings
from app.tools.computer import launch_application, control_music_playback, capture_desktop_screenshot
from app.tools.browser import BrowserEngine
from app.tools.developer import execute_python_code
from app.services.messaging import telegram_service

logger = logging.getLogger(__name__)

GEMINI_LIVE_WS_URL = (
    "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
)

# Laptop tools schema for Gemini Live function calling
LAPTOP_TOOL_DECLARATIONS = [
    {
        "name": "launch_application",
        "description": "Opens a native desktop application on the laptop screen in the visual foreground (e.g., spotify, chrome, notepad, vscode, explorer, calculator).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {"type": "STRING", "description": "The name or alias of the application to launch."}
            },
            "required": ["app_name"],
        },
    },
    {
        "name": "search_web",
        "description": "Opens Google Chrome visibly and searches for information on the web.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "The search query to search on Google."}
            },
            "required": ["query"],
        },
    },
    {
        "name": "control_music_playback",
        "description": "Controls audio and music playback on the laptop (play/pause, next track, volume adjustment).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "Action: play_pause, next, previous, volume_up, volume_down, mute."}
            },
            "required": ["action"],
        },
    },
    {
        "name": "capture_desktop_screenshot",
        "description": "Captures a live screenshot of the laptop screen to verify current visual state.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "filename": {"type": "STRING", "description": "Target filename for the screenshot."}
            },
        },
    },
    {
        "name": "play_music_request",
        "description": "Searches and plays a song, artist, or music query on YouTube Music or Spotify.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Song name or artist to play."},
                "service": {"type": "STRING", "description": "Service: youtube_music or spotify."}
            },
            "required": ["query"],
        },
    },
    {
        "name": "generate_ai_playlist",
        "description": "Creates an AI-curated DJ playlist matching mood, activity (e.g. studying ML, workout), or era.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "prompt": {"type": "STRING", "description": "Playlist description, e.g. '2-hour ML study playlist'"},
                "duration_minutes": {"type": "INTEGER", "description": "Target playlist duration in minutes"}
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "set_music_timer",
        "description": "Sets a sleep timer to fade out volume and pause music after a number of minutes.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "minutes": {"type": "INTEGER", "description": "Number of minutes before music stops."}
            },
            "required": ["minutes"],
        },
    },
]


def build_live_setup_payload(
    model: str = "models/gemini-2.5-flash",
    voice_name: str = "Puck",
) -> Dict[str, Any]:
    """Builds initial Gemini Live handshake setup JSON."""
    return {
        "setup": {
            "model": model,
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {
                            "voiceName": voice_name
                        }
                    }
                },
            },
            "systemInstruction": {
                "parts": [
                    {
                        "text": (
                            "You are NEXUS AI, an autonomous, intelligent voice assistant running directly on the user's laptop. "
                            "You are talking live with the user in full-duplex audio. "
                            "When the user asks you to open applications, play music, or search the web, execute the appropriate tool call immediately. "
                            "Keep your spoken answers concise, natural, friendly, and helpful."
                        )
                    }
                ]
            },
            "tools": [{"functionDeclarations": LAPTOP_TOOL_DECLARATIONS}],
        }
    }


def build_audio_chunk_payload(pcm_bytes: bytes) -> Dict[str, Any]:
    """Wraps 16kHz PCM audio bytes into a Gemini Live realtimeInput payload."""
    b64_data = base64.b64encode(pcm_bytes).decode("utf-8")
    return {
        "realtimeInput": {
            "mediaChunks": [
                {
                    "mimeType": "audio/pcm;rate=16000",
                    "data": b64_data,
                }
            ]
        }
    }


def build_tool_response_payload(call_id: str, function_name: str, response_data: Dict[str, Any]) -> Dict[str, Any]:
    """Builds toolResponse payload acknowledging function completion to Gemini Live."""
    return {
        "toolResponse": {
            "functionResponses": [
                {
                    "response": {"output": response_data},
                    "id": call_id,
                }
            ]
        }
    }


class GeminiLiveSession:
    """
    Manages bidirectional streaming audio session with Google Gemini Live API
    over persistent WebSockets.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "models/gemini-2.5-flash",
        voice_name: str = "Puck",
        on_audio_output: Optional[Callable[[bytes], Any]] = None,
        on_interrupted: Optional[Callable[[], Any]] = None,
        on_event: Optional[Callable[[Dict[str, Any]], Any]] = None,
        user_chat_id: Optional[str] = None,
    ):
        self.api_key = api_key or getattr(settings, "GEMINI_API_KEY", settings.GROQ_API_KEY)
        self.model = model
        self.voice_name = voice_name
        self.on_audio_output = on_audio_output
        self.on_interrupted = on_interrupted
        self.on_event = on_event
        self.user_chat_id = user_chat_id
        self._ws = None
        self._is_active = False

    async def _emit_event(self, event_data: Dict[str, Any]) -> None:
        """Emits structured event to callback listeners."""
        if self.on_event:
            try:
                res = self.on_event(event_data)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as exc:
                logger.debug(f"[GeminiLive] Event emit error: {exc}")

    async def connect(self) -> None:
        """Connects to Gemini Multimodal Live WebSocket and sends setup payload."""
        ws_url = f"{GEMINI_LIVE_WS_URL}?key={self.api_key}"
        logger.info(f"[GeminiLive] Establishing WebSocket to Gemini Multimodal Live...")
        self._ws = await websockets.connect(ws_url)
        self._is_active = True

        # Send initial handshake setup
        setup_payload = build_live_setup_payload(model=self.model, voice_name=self.voice_name)
        await self._ws.send(json.dumps(setup_payload))
        logger.info("[GeminiLive] Setup handshake transmitted.")

    async def send_audio_chunk(self, pcm_bytes: bytes) -> None:
        """Sends raw 16kHz PCM audio chunk from user microphone to Gemini Live."""
        if not self._ws or not self._is_active:
            return
        payload = build_audio_chunk_payload(pcm_bytes)
        await self._ws.send(json.dumps(payload))

    async def listen_loop(self) -> None:
        """Receives and processes streaming messages from Gemini Live."""
        try:
            async for raw_msg in self._ws:
                msg = json.loads(raw_msg)

                # 1. Handle Barge-In Interruption
                server_content = msg.get("serverContent", {})
                if server_content.get("interrupted") is True:
                    logger.info("[GeminiLive] User barge-in detected; flushing audio buffers.")
                    await self._emit_event({"type": "interrupted", "message": "User interrupted agent"})
                    if self.on_interrupted:
                        res = self.on_interrupted()
                        if asyncio.iscoroutine(res):
                            await res

                # 2. Extract Spoken Audio Parts (24kHz PCM) & Real-time Text
                model_turn = server_content.get("modelTurn", {})
                parts = model_turn.get("parts", [])
                for part in parts:
                    # Spoken audio bytes
                    inline_data = part.get("inlineData", {})
                    if inline_data.get("mimeType", "").startswith("audio/pcm"):
                        # Auto-duck background music while Gemini agent speaks
                        try:
                            from app.music.audio_controller import audio_controller
                            audio_controller.duck_music_volume(target_percent=15)
                        except Exception:
                            pass

                        pcm_bytes = base64.b64decode(inline_data.get("data", ""))
                        await self._emit_event({"type": "audio_state", "speaking": True})
                        if self.on_audio_output:
                            res = self.on_audio_output(pcm_bytes)
                            if asyncio.iscoroutine(res):
                                await res

                    # Text part of the reply
                    text = part.get("text")
                    if text:
                        await self._emit_event({"type": "agent_transcript", "text": text})

                if server_content.get("turnComplete"):
                    await self._emit_event({"type": "audio_state", "speaking": False})
                    # Restore background music volume when Gemini finishes speaking
                    try:
                        from app.music.audio_controller import audio_controller
                        audio_controller.restore_music_volume()
                    except Exception:
                        pass

                # Extract user speech transcript if provided by Gemini
                user_turn = server_content.get("userTurn", {})
                for u_part in user_turn.get("parts", []):
                    if u_part.get("text"):
                        await self._emit_event({"type": "user_transcript", "text": u_part.get("text")})

                # 3. Handle Tool Calls
                tool_call = msg.get("toolCall")
                if tool_call:
                    await self._handle_gemini_tool_call(tool_call)

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error(f"[GeminiLive] WebSocket loop error: {exc}", exc_info=True)
        finally:
            await self.close()

    async def _handle_gemini_tool_call(self, tool_call: Dict[str, Any]) -> None:
        """Executes laptop function calls invoked by Gemini Live and responds."""
        for call in tool_call.get("functionCalls", []):
            call_id = call.get("id")
            func_name = call.get("name")
            args = call.get("args", {})
            logger.info(f"[GeminiLive] Dispatching tool call: '{func_name}' with args {args}")

            # Emit tool_start diagnostic event
            await self._emit_event({
                "type": "tool_start",
                "name": func_name,
                "args": args,
                "call_id": call_id,
            })

            res_data: Dict[str, Any] = {"status": "success"}

            try:
                if func_name == "launch_application":
                    app_name = args.get("app_name", "spotify")
                    res_data = await launch_application(app_name)
                elif func_name == "control_music_playback":
                    action = args.get("action", "play_pause")
                    res_data = await control_music_playback(action)
                elif func_name == "search_web":
                    query = args.get("query", "")
                    async with BrowserEngine(headless=False) as browser:
                        search_res = await browser.search_web(query=query, visual=True)
                        res_data = {"status": "success", "results_count": len(search_res)}
                elif func_name == "capture_desktop_screenshot":
                    fname = args.get("filename", "call_shot.png")
                    shot_path = await capture_desktop_screenshot(filename=fname)
                    res_data = {"status": "success", "path": shot_path}
                elif func_name == "play_music_request":
                    from app.music.music_controller import music_controller
                    q = args.get("query", "Top hits")
                    srv = args.get("service", "youtube_music")
                    res_data = await music_controller.play(service=srv, query=q)
                elif func_name == "generate_ai_playlist":
                    from app.music.recommendation_engine import recommendation_engine
                    from app.music.music_controller import music_controller
                    prompt = args.get("prompt", "Focus playlist")
                    dur = args.get("duration_minutes", 60)
                    pl_res = recommendation_engine.generate_ai_playlist(prompt=prompt, duration_minutes=dur)
                    if pl_res["tracks"]:
                        await music_controller.play(query=pl_res["tracks"][0]["query"])
                    res_data = pl_res
                elif func_name == "set_music_timer":
                    from app.music.sleep_timer import sleep_timer_manager
                    mins = args.get("minutes", 30)
                    res_data = sleep_timer_manager.set_sleep_timer(mins)
            except Exception as tool_err:
                logger.error(f"[GeminiLive] Tool execution failed: {tool_err}")
                res_data = {"status": "failed", "error": str(tool_err)}

            # Emit tool_complete diagnostic event
            await self._emit_event({
                "type": "tool_complete",
                "name": func_name,
                "status": res_data.get("status", "success"),
                "result": str(res_data),
                "call_id": call_id,
            })

            # Return tool response to Gemini

            # Return tool response to Gemini
            resp_payload = build_tool_response_payload(call_id, func_name, res_data)
            await self._ws.send(json.dumps(resp_payload))

            # Send visual proof screenshot to user's Telegram if chat_id is available
            if self.user_chat_id:
                try:
                    proof = await capture_desktop_screenshot(filename=f"live_{func_name}.png")
                    asyncio.create_task(
                        telegram_service.send_image(
                            chat_id=self.user_chat_id,
                            image_bytes_or_path=proof,
                            caption=f"⚡ Live Call Execution: `{func_name}` performed on laptop"
                        )
                    )
                except Exception as shot_err:
                    logger.debug(f"[GeminiLive] Telegram live proof note: {shot_err}")

    async def close(self) -> None:
        """Closes live WebSocket session cleanly."""
        self._is_active = False
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        logger.info("[GeminiLive] Live session terminated.")

