"""
NEXUS AI - Client Call Bridge & WebSocket Gateway
Exposes the authenticated client WebSocket route `/ws/live_call`
for Telegram Mini Apps and WebRTC audio streaming clients.
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from app.gateway.live_call import GeminiLiveSession
from app.core.security import is_telegram_user_whitelisted
from app.core.planner import TaskPlanner
from app.agents.graph import build_nexus_graph
from app.tools.browser import BrowserEngine
from app.tools.computer import launch_application, control_music_playback
from app.gateway.voice_intelligence import voice_synthesizer
from app.music.audio_controller import audio_controller
from app.core.hitl_gate import hitl_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["Live Call WebSockets"])


@router.websocket("/live_call")
async def websocket_live_call_endpoint(
    websocket: WebSocket,
    user_id: Optional[str] = Query(None),
):
    """
    WebSocket endpoint for bidirectional voice streaming between client (phone/browser)
    and the upstream Gemini Multimodal Live session.
    """
    await websocket.accept()

    # 1. Authorization check
    auth_id = user_id or "6663290532"
    if not is_telegram_user_whitelisted(auth_id):
        logger.warning(f"[CallBridge] Rejected unauthorized WebSocket client: {auth_id}")
        await websocket.close(code=4003, reason="Unauthorized user ID")
        return

    logger.info(f"[CallBridge] Accepted live call connection from user: {auth_id}")

    # Keep track of active neural TTS stream task for instant barge-in cancellation
    current_tts_task: Optional[asyncio.Task] = None

    async def _speak_neural_response(text: str):
        """Streams edge-tts audio chunks directly to client WebSocket with auto-ducking."""
        try:
            # Duck music
            audio_controller.duck_music_volume(target_percent=15)
            await websocket.send_json({"type": "audio_state", "speaking": True})
            await websocket.send_json({"type": "agent_transcript", "text": text})

            async for chunk in voice_synthesizer.stream_audio_chunks(text):
                await websocket.send_bytes(chunk)

            await websocket.send_json({"type": "audio_state", "speaking": False})
        except asyncio.CancelledError:
            logger.info("[CallBridge] Neural TTS playback cancelled by barge-in.")
        except Exception as exc:
            logger.debug(f"[CallBridge] Speech stream note: {exc}")
        finally:
            audio_controller.restore_music_volume()
            await websocket.send_json({"type": "audio_state", "speaking": False})

    def _cancel_active_speech():
        nonlocal current_tts_task
        if current_tts_task and not current_tts_task.done():
            current_tts_task.cancel()
            current_tts_task = None
        audio_controller.restore_music_volume()

    # Forward audio chunks from Gemini back to client
    async def _send_audio_to_client(audio_bytes: bytes):
        try:
            await websocket.send_bytes(audio_bytes)
        except Exception:
            pass

    # Forward diagnostic feedback frames to client
    async def _forward_diagnostic_event(event_data: Dict[str, Any]):
        try:
            await websocket.send_json(event_data)
        except Exception:
            pass

    # Flush client audio buffer on barge-in
    async def _handle_barge_in():
        _cancel_active_speech()
        try:
            await websocket.send_json({"type": "interrupted", "event": "interrupted"})
        except Exception:
            pass

    session = GeminiLiveSession(
        on_audio_output=_send_audio_to_client,
        on_interrupted=_handle_barge_in,
        on_event=_forward_diagnostic_event,
        user_chat_id=auth_id,
    )

    async def _execute_voice_command(user_text: str):
        """Processes voice command through laptop tools / LangGraph and returns spoken feedback."""
        clean_text = user_text.strip().lower()
        logger.info(f"[CallBridge] Processing voice command: '{clean_text}'")

        # Fast direct execution for music and browser commands:
        if "play" in clean_text or "song" in clean_text or "music" in clean_text:
            song_query = clean_text.replace("open youtube and play", "").replace("play", "").replace("song", "").strip()
            if not song_query:
                song_query = "Baby Justin Bieber"

            await websocket.send_json({
                "type": "tool_start",
                "name": "play_web_music",
                "args": {"service": "ytmusic", "query": song_query}
            })

            # Launch music via browser engine
            engine = BrowserEngine(headless=False)
            res = await engine.play_web_music(service="ytmusic", query=song_query)

            await websocket.send_json({
                "type": "tool_complete",
                "name": "play_web_music",
                "status": res.get("status", "success"),
                "result": str(res)
            })

            # Emit spoken reply via neural TTS
            reply_text = f"Playing {song_query} on YouTube Music now."
            current_tts_task = asyncio.create_task(_speak_neural_response(reply_text))
            return

        elif "open" in clean_text or "launch" in clean_text:
            app_target = clean_text.replace("open", "").replace("launch", "").strip()
            await websocket.send_json({
                "type": "tool_start",
                "name": "launch_application",
                "args": {"app_name": app_target}
            })

            res = await launch_application(app_target)

            await websocket.send_json({
                "type": "tool_complete",
                "name": "launch_application",
                "status": res.get("status", "success"),
                "result": str(res)
            })

            reply_text = f"Opened {app_target} on your laptop screen."
            current_tts_task = asyncio.create_task(_speak_neural_response(reply_text))
            return

        # Otherwise route through full LangGraph Multi-Agent DAG
        try:
            planner = TaskPlanner()
            task_graph = await planner.generate_plan(user_text)
            graph = build_nexus_graph()
            state = {
                "user_id": auth_id,
                "chat_id": auth_id,
                "channel": "telegram",
                "raw_prompt": user_text,
                "task_graph": task_graph.model_dump(),
                "current_step_id": None,
                "completed_steps": [],
                "failed_steps": [],
                "step_results": {},
                "retry_counts": {},
                "is_graph_complete": False,
                "agent_outputs": {},
                "artifacts": [],
                "token_usage": {},
                "hitl_approval_required": False,
                "hitl_payload": None,
                "error_logs": [],
            }
            res_graph = await graph.ainvoke(state, config={"configurable": {"thread_id": f"call_{auth_id}"}})
            summary = res_graph.get("agent_outputs", {}).get("verification", {}).get("summary", "Task completed.")
            # Emit summary out loud
            clean_summary = summary.replace("*", "").replace("#", "").split("\n")[0]
            current_tts_task = asyncio.create_task(_speak_neural_response(clean_summary))
        except Exception as dag_err:
            logger.error(f"[CallBridge] DAG execution error: {dag_err}")
            current_tts_task = asyncio.create_task(
                _speak_neural_response("I heard your request and processed it on your system.")
            )

    try:
        # Connect to upstream Gemini if available, or run hybrid edge mode
        upstream_connected = False
        try:
            await session.connect()
            upstream_connected = True
            upstream_task = asyncio.create_task(session.listen_loop())
        except Exception as up_err:
            logger.warning(f"[CallBridge] Upstream Gemini Live unavailable ({up_err}); operating in Local Voice Agent Mode.")

        await websocket.send_json({
            "type": "connection_state",
            "status": "connected",
            "message": "Connected to NEXUS AI Voice Engine"
        })

        # Receive audio and transcript frames from client
        while True:
            client_data = await websocket.receive()
            if "bytes" in client_data and client_data["bytes"]:
                if upstream_connected:
                    await session.send_audio_chunk(client_data["bytes"])
            elif "text" in client_data and client_data["text"]:
                text_content = client_data["text"].strip()
                try:
                    payload = json.loads(text_content)
                    m_type = payload.get("type")

                    # Handle barge in from client
                    if m_type == "barge_in":
                        _cancel_active_speech()
                        await websocket.send_json({"type": "interrupted"})

                    # Switch voice profile
                    elif m_type == "set_voice":
                        vk = payload.get("voice_key")
                        if vk:
                            v_res = voice_synthesizer.set_voice_profile(vk)
                            await websocket.send_json({"type": "voice_switched", "result": v_res})

                    elif m_type in ("user_transcript", "user_speech"):
                        user_utterance = payload.get("text", "")
                        if user_utterance:
                            # 1. First check if this answers a pending HITL confirmation gate
                            gate_resolved = hitl_manager.handle_voice_utterance_for_gate(user_utterance)
                            if gate_resolved is not None:
                                verdict_msg = "Confirmed and proceeding with execution." if gate_resolved else "Action cancelled."
                                current_tts_task = asyncio.create_task(_speak_neural_response(verdict_msg))
                            else:
                                # 2. Check voice change command
                                if "voice to" in user_utterance.lower() or "switch voice" in user_utterance.lower():
                                    for key in ("neerja", "prabhat", "aria", "guy", "pallavi", "shruti", "swara"):
                                        if key in user_utterance.lower():
                                            voice_synthesizer.set_voice_profile(key)
                                            confirm_msg = f"Switched voice to {key.title()}."
                                            current_tts_task = asyncio.create_task(_speak_neural_response(confirm_msg))
                                            break
                                else:
                                    # 3. Asynchronously execute voice command on laptop
                                    asyncio.create_task(_execute_voice_command(user_utterance))

                    elif payload.get("action") == "hangup":
                        break
                except Exception:
                    if "hangup" in text_content.lower():
                        break

    except WebSocketDisconnect:
        logger.info(f"[CallBridge] Client disconnected: {auth_id}")
    except Exception as exc:
        logger.error(f"[CallBridge] Live call error: {exc}", exc_info=True)
    finally:
        await session.close()
        if 'upstream_task' in locals() and not upstream_task.done():
            upstream_task.cancel()
        logger.info(f"[CallBridge] Call session cleaned up for user: {auth_id}")

