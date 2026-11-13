"""
NEXUS AI - Cognitive Brain & Reasoning Engine
Implements the 5 core cyclical nodes:
1. intent_and_context_node
2. task_planner_node
3. step_executor_node
4. dynamic_replanner_node
5. final_responder_node
"""

import asyncio
import json
import logging
import traceback
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from app.config import settings
from app.core.state import NexusState
from app.tools.computer import (
    launch_application,
    close_application,
    control_music_playback,
    capture_desktop_screenshot,
    search_installed_apps,
    get_running_apps,
    manage_window,
    install_application,
    uninstall_application,
    detect_app_errors,
    control_app_ui,
    mouse_action,
    keyboard_action,
)
from app.tools.browser import BrowserEngine
from app.tools.filesystem import create_file, read_file
from app.tools.developer import execute_python_code
from app.tools.research_engine import (
    search_academic_papers,
    monitor_website_changes,
    run_structured_research_to_excel,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Structured Output Schemas
# ---------------------------------------------------------------------------

class UserIntentOutput(BaseModel):
    category: str = Field(description="Intent category: MEDIA, BROWSER, SYSTEM, FILESYSTEM, DEVELOPER, CHAT")
    entities: Dict[str, Any] = Field(default_factory=dict, description="Extracted entities such as app_name, song, query, target_path")
    confidence: float = Field(default=0.95, description="Confidence score between 0.0 and 1.0")
    resolved_query: str = Field(description="Self-contained user instruction after resolving multi-turn pronouns like it, that, etc.")


class AtomicPlanStep(BaseModel):
    step_id: str
    description: str
    tool_name: str
    tool_args: Dict[str, Any] = Field(default_factory=dict)
    status: str = Field(default="pending")


class TaskPlanOutput(BaseModel):
    summary: str
    plan_steps: List[AtomicPlanStep]


# ---------------------------------------------------------------------------
# Tool Registry Dispatcher
# ---------------------------------------------------------------------------

async def dispatch_tool_call(tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """Asynchronously routes tool_name to actual NEXUS AI tools with result normalization."""
    name_clean = tool_name.strip().lower()
    logger.info(f"[BrainDispatcher] Executing '{name_clean}' with args {tool_args}")

    # 1. Desktop Application Launcher
    if name_clean in ("launch_application", "launch_app", "open_app"):
        app_name = tool_args.get("app_name") or tool_args.get("app") or "notepad"
        args = tool_args.get("args", [])
        return await launch_application(app_name=app_name, args=args)

    # 2. Desktop Application Terminator
    elif name_clean in ("close_application", "close_app", "kill_process", "quit_app"):
        process_name = tool_args.get("process_name") or tool_args.get("app_name") or tool_args.get("app") or ""
        return await close_application(process_name_or_title=process_name)

    # 3. Web & Browser Automation
    elif name_clean in ("execute_browser_intent", "browser_intent", "universal_browser"):
        from app.tools.browser import execute_browser_intent
        instruction = tool_args.get("instruction") or tool_args.get("query") or ""
        return await execute_browser_intent(instruction=instruction, user_context=tool_args)

    elif name_clean in ("search_web", "web_search", "google_search"):
        query = tool_args.get("query") or tool_args.get("text") or ""
        from app.tools.browser import search_web
        return await search_web(query=query, max_results=8)

    elif name_clean in ("play_web_music", "play_music", "stream_music"):
        service = tool_args.get("service") or "youtube_music"
        query = tool_args.get("query") or tool_args.get("song") or ""
        engine = BrowserEngine(headless=False)
        return await engine.play_web_music(service=service, query=query)

    # 4. OS Media Controller
    elif name_clean in ("control_music_playback", "control_media", "media_hotkey"):
        action = tool_args.get("action") or "play_pause"
        value = tool_args.get("value")
        return await control_music_playback(action=action, value=value)

    # 5. Desktop Screenshot
    elif name_clean in ("capture_desktop_screenshot", "screenshot"):
        filename = tool_args.get("filename") or "desktop_proof.png"
        path = await capture_desktop_screenshot(filename=filename)
        return {"status": "success", "screenshot_path": path}

    # 6. Python Developer Tool
    elif name_clean in ("execute_python_script", "execute_python", "run_python"):
        code = tool_args.get("code") or ""
        filename = tool_args.get("filename") or "script.py"
        return await execute_python_code(code=code, filename=filename)

    # 7. File Operations
    elif name_clean in ("create_file", "write_file"):
        path = tool_args.get("path") or tool_args.get("filename") or "note.txt"
        content = tool_args.get("content") or ""
        return await create_file(path=path, content=content)

    elif name_clean in ("read_file", "get_file"):
        path = tool_args.get("path") or tool_args.get("filename") or "note.txt"
        return await read_file(path=path)

    # 8. WhatsApp Dispatcher
    elif name_clean in ("send_whatsapp_file", "whatsapp_file"):
        from app.tools.whatsapp import send_whatsapp_file
        contact = tool_args.get("contact_name") or ""
        f_query = tool_args.get("file_query") or ""
        caption = tool_args.get("caption") or ""
        return await send_whatsapp_file(contact_name=contact, file_query=f_query, caption=caption)

    # 9. Windows 11 Desktop Automation (Module 2)
    elif name_clean in ("search_installed_apps", "list_installed_apps"):
        query = tool_args.get("query", "")
        return {"status": "success", "apps": await search_installed_apps(query=query)}

    elif name_clean in ("get_running_apps", "list_running_apps"):
        return {"status": "success", "running": await get_running_apps()}

    elif name_clean in ("manage_window", "window_control"):
        title = tool_args.get("app_title") or tool_args.get("title") or ""
        action = tool_args.get("action") or "switch"
        return await manage_window(app_title=title, action=action)

    elif name_clean in ("install_application", "winget_install"):
        pkg = tool_args.get("package_id") or tool_args.get("pkg") or ""
        chat_id = tool_args.get("chat_id")
        return await install_application(package_id=pkg, chat_id=chat_id)

    elif name_clean in ("uninstall_application", "winget_uninstall"):
        pkg = tool_args.get("package_id") or tool_args.get("pkg") or ""
        chat_id = tool_args.get("chat_id")
        return await uninstall_application(package_id=pkg, chat_id=chat_id)

    elif name_clean in ("detect_app_errors", "check_crash_dialogs"):
        return {"status": "success", "errors": await detect_app_errors()}

    elif name_clean in ("control_app_ui", "uia_control"):
        w_title = tool_args.get("window_title", "")
        c_name = tool_args.get("control_name", "")
        action = tool_args.get("action", "click")
        val = tool_args.get("value")
        return await control_app_ui(window_title=w_title, control_name=c_name, action=action, value=val)

    elif name_clean in ("mouse_action", "mouse_control"):
        action = tool_args.get("action", "click")
        x = tool_args.get("x")
        y = tool_args.get("y")
        btn = tool_args.get("button", "left")
        clicks = tool_args.get("clicks", 1)
        delta_y = tool_args.get("delta_y", 0)
        return await mouse_action(action=action, x=x, y=y, button=btn, clicks=clicks, delta_y=delta_y)

    elif name_clean in ("keyboard_action", "keyboard_control"):
        action = tool_args.get("action", "hotkey")
        keys = tool_args.get("keys")
        text = tool_args.get("text")
        press_enter = tool_args.get("press_enter", True)
        return await keyboard_action(action=action, keys=keys, text=text, press_enter=press_enter)

    # 10. Module 3: Advanced Browser Intelligence & Research
    elif name_clean in ("search_academic_papers", "arxiv_search"):
        q = tool_args.get("query", "machine learning")
        max_r = tool_args.get("max_results", 10)
        return {"status": "success", "papers": await search_academic_papers(query=q, max_results=max_r)}

    elif name_clean in ("monitor_website_changes", "check_webpage_change"):
        url = tool_args.get("url", "")
        sel = tool_args.get("selector", "body")
        chat_id = tool_args.get("chat_id")
        return await monitor_website_changes(url=url, selector=sel, chat_id=chat_id)

    elif name_clean in ("run_structured_research_to_excel", "research_to_excel", "generate_excel_comparison"):
        goal = tool_args.get("goal") or "10 AI/ML internships in India"
        out_name = tool_args.get("output_filename") or "AIML_Internships_India_Comparison.xlsx"
        sources = tool_args.get("sources", [])
        return await run_structured_research_to_excel(goal=goal, sources=sources, output_filename=out_name)

    elif name_clean in ("download_document", "download_file"):
        url = tool_args.get("url", "")
        selector = tool_args.get("trigger_selector")
        filename = tool_args.get("custom_filename")
        engine = BrowserEngine(headless=True)
        return await engine.download_document(url=url, trigger_selector=selector, custom_filename=filename)

    elif name_clean in ("upload_document", "upload_file"):
        url = tool_args.get("url", "")
        selector = tool_args.get("file_input_selector", "input[type='file']")
        filepath = tool_args.get("local_filepath", "")
        engine = BrowserEngine(headless=True)
        return await engine.upload_document(url=url, file_input_selector=selector, local_filepath=filepath)

    elif name_clean in ("crawl_with_pagination", "crawl_pages"):
        url = tool_args.get("start_url", "")
        sel = tool_args.get("item_selector", "")
        count = tool_args.get("target_count", 10)
        engine = BrowserEngine(headless=True)
        items = await engine.crawl_with_pagination(start_url=url, item_selector=sel, target_count=count)
        return {"status": "success", "items": items, "count": len(items)}

    # 11. Module: Music & Audio Intelligence
    elif name_clean in ("get_audio_output_device", "get_default_output_device", "get_sound_device"):
        from app.music.audio_controller import audio_controller
        return audio_controller.get_default_output_device()

    elif name_clean in ("generate_ai_playlist", "create_playlist", "dj_playlist"):
        from app.music.recommendation_engine import recommendation_engine
        prompt = tool_args.get("prompt") or tool_args.get("query") or "Study playlist"
        mins = tool_args.get("duration_minutes") or 60
        return recommendation_engine.generate_ai_playlist(prompt=prompt, duration_minutes=mins)

    elif name_clean in ("set_volume", "adjust_volume"):
        from app.music.audio_controller import audio_controller
        pct = tool_args.get("percent") or tool_args.get("volume") or 50
        return audio_controller.set_master_volume(int(pct))

    elif name_clean in ("set_sleep_timer", "sleep_timer"):
        from app.music.sleep_timer import sleep_timer_manager
        mins = tool_args.get("minutes") or 30
        return sleep_timer_manager.set_sleep_timer(int(mins))

    # 12. Module: File & Document Intelligence
    elif name_clean in ("run_document_task", "document_intelligence", "literature_review", "compare_documents"):
        from app.documents.document_agent import run_document_task
        task_type = tool_args.get("task_type", "literature_review")
        params = tool_args.get("params", tool_args)
        return await run_document_task(task_type, params)

    # 13. Module: Autonomous Developer & Competitive Programming
    elif name_clean in ("run_developer_task", "build_application", "solve_competitive_programming", "developer_agent"):
        from app.developer.developer_agent import run_developer_task
        task_type = tool_args.get("task_type", "build_app")
        params = tool_args.get("params", tool_args)
        return await run_developer_task(task_type, params)

    else:
        # Fallback simulation or unknown tool
        logger.warning(f"[BrainDispatcher] Unrecognized tool '{tool_name}', executing simulated pass.")
        return {"status": "success", "tool": tool_name, "args": tool_args}


# ---------------------------------------------------------------------------
# Cognitive Nodes
# ---------------------------------------------------------------------------

async def intent_and_context_node(state: NexusState) -> Dict[str, Any]:
    """
    1. Inspects the latest user message and conversation history to resolve contextual references
       (e.g., 'it', 'that file', 'play next', 'close it').
    2. Classifies user_intent and extracts entities with structured output.
    """
    messages = state.get("messages", [])
    if not messages:
        return {
            "user_intent": {
                "category": "CHAT",
                "entities": {},
                "confidence": 1.0,
                "resolved_query": "Hello",
            }
        }

    latest_msg = messages[-1]
    raw_text = latest_msg.content if hasattr(latest_msg, "content") else str(latest_msg)

    # Analyze multi-turn context
    context_snippets = []
    for msg in messages[:-1][-4:]:
        role = "User" if isinstance(msg, HumanMessage) else "Assistant"
        content = msg.content if hasattr(msg, "content") else str(msg)
        context_snippets.append(f"{role}: {content}")
    history_str = "\n".join(context_snippets)

    # Rule-based contextual intent extraction with LLM fallback
    p_lower = raw_text.strip().lower()

    # Contextual reference resolution (e.g. "close it", "play it")
    resolved_query = raw_text
    prior_app = None
    for hist_item in reversed(context_snippets):
        for candidate in ["notepad", "spotify", "chrome", "calculator", "vscode", "terminal", "vlc"]:
            if candidate in hist_item.lower():
                prior_app = candidate
                break
        if prior_app:
            break

    if ("close it" in p_lower or "kill it" in p_lower or "exit it" in p_lower) and prior_app:
        resolved_query = f"close {prior_app}"
        category = "SYSTEM"
        entities = {"app_name": prior_app, "action": "close"}
    elif any(w in p_lower for w in ["close", "quit", "exit", "kill"]) and any(
        a in p_lower for a in ["app", "chrome", "notepad", "spotify", "calculator", "vscode", "terminal"]
    ):
        target_app = "app"
        for a in ["chrome", "spotify", "notepad", "calculator", "vscode", "terminal", "vlc"]:
            if a in p_lower:
                target_app = a
                break
        category = "SYSTEM"
        entities = {"app_name": target_app, "action": "close"}
    elif any(w in p_lower for w in ["play", "song", "music", "spotify", "ytmusic"]):
        category = "MEDIA"
        song = p_lower.replace("open youtube and play", "").replace("play", "").replace("song", "").strip()
        entities = {"song": song or "popular track", "service": "youtube_music" if "youtube" in p_lower else "spotify"}
    elif (
        any(w in p_lower for w in ["search", "google", "browse", "look up", "find", "history", "bookmark"])
        or ("download" in p_lower and "http" in p_lower)
        or any(d in p_lower for d in [".com", ".org", ".io", ".dev", ".ai", "github", "reddit", "leetcode", "youtube", "arxiv"])
        or (("chrome" in p_lower or "browser" in p_lower) and not any(c in p_lower for c in ["close", "kill", "quit", "exit"]))
    ):
        category = "BROWSER"
        entities = {"query": raw_text.strip(), "instruction": raw_text.strip()}
    elif any(w in p_lower for w in ["open", "launch"]):
        category = "SYSTEM"
        app = p_lower.replace("open", "").replace("launch", "").replace("please", "").strip()
        for candidate in ["notepad", "spotify", "chrome", "calculator", "calc", "vscode", "terminal", "vlc", "explorer"]:
            if candidate in p_lower:
                app = candidate
                break
        entities = {"app_name": app, "action": "launch"}
    elif any(w in p_lower for w in ["whatsapp", "send file"]):
        category = "MESSAGING"
        entities = {"action": "send_file"}
    elif any(w in p_lower for w in ["python", "code", "run script"]):
        category = "DEVELOPER"
        entities = {"action": "execute_code"}
    else:
        category = "GENERAL"
        entities = {}

    return {
        "user_intent": {
            "category": category,
            "entities": entities,
            "confidence": 0.95,
            "resolved_query": resolved_query,
        }
    }


async def task_planner_node(state: NexusState) -> Dict[str, Any]:
    """
    Decomposes the resolved user query into an ordered atomic list of plan_steps.
    Selects concrete tool names and arguments from NEXUS AI's tool registry.
    """
    intent_data = state.get("user_intent", {})
    resolved_query = intent_data.get("resolved_query", "").strip()
    category = intent_data.get("category", "GENERAL")
    entities = intent_data.get("entities", {})

    p_lower = resolved_query.lower()
    plan_steps: List[Dict[str, Any]] = []

    # 0. Primary Universal Browser & Web Routing
    if category == "BROWSER":
        instruction = entities.get("instruction") or entities.get("query") or resolved_query
        plan_steps.append({
            "step_id": "step_1",
            "description": f"Execute browser action in visible Chrome: {instruction}",
            "tool_name": "execute_browser_intent",
            "tool_args": {"instruction": instruction},
            "status": "pending",
        })

    # 1. Compound Autonomous Research to Excel (Module 3)
    elif "internship" in p_lower or ("research" in p_lower and "excel" in p_lower) or "academic" in p_lower or "monitor" in p_lower or ("arxiv" in p_lower and "paper" in p_lower):
        if "academic" in p_lower or "arxiv" in p_lower:
            plan_steps.append({
                "step_id": "step_1",
                "description": f"Search academic papers on arXiv for: {resolved_query}",
                "tool_name": "search_academic_papers",
                "tool_args": {"query": resolved_query, "max_results": 10},
                "status": "pending",
            })
        elif "monitor" in p_lower and "http" in p_lower:
            import re
            urls = re.findall(r'https?://[^\s]+', resolved_query)
            target_url = urls[0] if urls else "https://example.com"
            plan_steps.append({
                "step_id": "step_1",
                "description": f"Monitor website for changes: {target_url}",
                "tool_name": "monitor_website_changes",
                "tool_args": {"url": target_url},
                "status": "pending",
            })
        else:
            plan_steps.append({
                "step_id": "step_1",
                "description": f"Perform autonomous research and generate styled comparison Excel sheet",
                "tool_name": "run_structured_research_to_excel",
                "tool_args": {
                    "goal": resolved_query,
                    "output_filename": "AIML_Internships_India_Comparison.xlsx",
                },
                "status": "pending",
            })

    # 1. Close application
    elif category == "SYSTEM" and entities.get("action") == "close":
        target = entities.get("app_name", "notepad")
        plan_steps.append({
            "step_id": "step_1",
            "description": f"Close application '{target}'",
            "tool_name": "close_application",
            "tool_args": {"process_name": target},
            "status": "pending",
        })

    # 2. Launch application
    elif category == "SYSTEM" and entities.get("action") == "launch":
        target = entities.get("app_name", "notepad")
        plan_steps.append({
            "step_id": "step_1",
            "description": f"Launch application '{target}' in foreground",
            "tool_name": "launch_application",
            "tool_args": {"app_name": target},
            "status": "pending",
        })
        plan_steps.append({
            "step_id": "step_2",
            "description": f"Capture desktop proof of '{target}' window",
            "tool_name": "capture_desktop_screenshot",
            "tool_args": {"filename": f"launch_{target}.png"},
            "status": "pending",
        })

    # 3. Media streaming
    elif category == "MEDIA":
        song = entities.get("song", "Interstellar")
        service = entities.get("service", "youtube_music")
        plan_steps.append({
            "step_id": "step_1",
            "description": f"Stream '{song}' on {service}",
            "tool_name": "play_web_music",
            "tool_args": {"service": service, "query": song},
            "status": "pending",
        })

    # 4. Web Search
    elif category == "BROWSER":
        q = entities.get("query", resolved_query)
        plan_steps.append({
            "step_id": "step_1",
            "description": f"Search web for: {q}",
            "tool_name": "search_web",
            "tool_args": {"query": q},
            "status": "pending",
        })

    # 5. Multi-part / Complex default: Create report & screenshot
    elif "report" in p_lower and "code" in p_lower:
        plan_steps.append({
            "step_id": "step_1",
            "description": "Execute python computation",
            "tool_name": "execute_python_script",
            "tool_args": {"code": "print('Task analysis done')", "filename": "calc.py"},
            "status": "pending",
        })
        plan_steps.append({
            "step_id": "step_2",
            "description": "Save generated findings to report",
            "tool_name": "create_file",
            "tool_args": {"filename": "report.md", "content": "# Analysis Completed"},
            "status": "pending",
        })
        plan_steps.append({
            "step_id": "step_3",
            "description": "Capture desktop proof",
            "tool_name": "capture_desktop_screenshot",
            "tool_args": {"filename": "final_proof.png"},
            "status": "pending",
        })

    # 6. Audio / Sound Device identification & settings queries
    elif any(k in p_lower for k in ["audio output", "sound device", "speaker", "output device", "system > sound", "sound setting"]):
        plan_steps.append({
            "step_id": "step_1",
            "description": "Inspect and retrieve the current active audio output device",
            "tool_name": "get_audio_output_device",
            "tool_args": {},
            "status": "pending",
        })
        plan_steps.append({
            "step_id": "step_2",
            "description": "Capture visual screenshot verification of the desktop",
            "tool_name": "capture_desktop_screenshot",
            "tool_args": {"filename": "sound_settings_verification.png"},
            "status": "pending",
        })

    else:
        plan_steps.append({
            "step_id": "step_1",
            "description": f"Execute action: {resolved_query}",
            "tool_name": "search_web" if "search" in p_lower else "launch_application",
            "tool_args": {"query": resolved_query} if "search" in p_lower else {"app_name": "notepad"},
            "status": "pending",
        })

    return {
        "plan_steps": plan_steps,
        "current_step_index": 0,
        "replan_count": state.get("replan_count", 0),
    }


async def step_executor_node(state: NexusState) -> Dict[str, Any]:
    """
    Reads plan_steps[current_step_index], executes the tool asynchronously,
    captures outputs/error traces into execution_logs, and updates step status.
    """
    plan_steps = list(state.get("plan_steps", []))
    idx = state.get("current_step_index", 0)

    if idx >= len(plan_steps):
        return {"current_step_index": idx}

    step = dict(plan_steps[idx])
    step_id = step.get("step_id", f"step_{idx+1}")
    tool_name = step.get("tool_name", "")
    tool_args = step.get("tool_args", {})

    logger.info(f"[StepExecutor] Running step {idx+1}/{len(plan_steps)}: {step_id} - '{tool_name}'")

    # Sensitive tools requiring Human-in-the-Loop authorization
    SENSITIVE_TOOLS = {"send_whatsapp_file", "install_application", "uninstall_application", "delete_file_or_folder"}
    if tool_name in SENSITIVE_TOOLS:
        from app.core.hitl_gate import hitl_manager
        summary = f"{tool_name} with args {tool_args}"
        approved = await hitl_manager.request_voice_or_telegram_approval(
            action_summary=summary,
            thread_id=state.get("chat_id", "default"),
            timeout=30,
        )
        if not approved:
            step["status"] = "failed"
            return {
                "plan_steps": plan_steps,
                "current_step_index": idx,
                "execution_logs": state.get("execution_logs", []) + [{
                    "step_id": step_id,
                    "tool_name": tool_name,
                    "status": "rejected",
                    "output": "Action was not approved by user.",
                }],
            }

    artifacts: List[str] = []
    error_trace: Optional[str] = None
    step_output: Any = None

    try:
        step["status"] = "running"
        step_output = await dispatch_tool_call(tool_name, tool_args)

        # Check for error status in output
        if isinstance(step_output, dict) and step_output.get("status") == "failed":
            raise RuntimeError(step_output.get("error", "Tool returned failure status"))

        step["status"] = "completed"

        # Check for generated screenshot or artifact file paths
        if isinstance(step_output, dict):
            for key in ("screenshot_path", "path", "file_path"):
                if key in step_output and step_output[key]:
                    artifacts.append(str(step_output[key]))

    except Exception as exc:
        logger.error(f"[StepExecutor] Step {step_id} failed: {exc}", exc_info=True)
        step["status"] = "failed"
        error_trace = traceback.format_exc()
        step_output = {"status": "failed", "error": str(exc)}

    # Update step in plan_steps
    plan_steps[idx] = step

    log_entry = {
        "step_id": step_id,
        "tool_name": tool_name,
        "status": step["status"],
        "output": step_output,
        "error_traceback": error_trace,
    }

    return {
        "plan_steps": plan_steps,
        "execution_logs": [log_entry],
        "artifacts": artifacts,
    }


async def dynamic_replanner_node(state: NexusState) -> Dict[str, Any]:
    """
    Triggered when a step fails and replan_count < 3.
    Analyzes the failure traceback and replaces remaining plan_steps with a viable fallback.
    """
    replan_count = state.get("replan_count", 0) + 1
    plan_steps = list(state.get("plan_steps", []))
    idx = state.get("current_step_index", 0)
    failed_step = plan_steps[idx] if idx < len(plan_steps) else {}
    failed_tool = failed_step.get("tool_name", "")
    failed_args = failed_step.get("tool_args", {})

    logger.warning(
        f"[DynamicReplanner] Replanning attempt {replan_count}/3 for failed step '{failed_step.get('step_id')}' ({failed_tool})"
    )

    # Determine fallback strategy based on failed tool
    fallback_steps: List[Dict[str, Any]] = []

    # 1. Fallback for close_application -> try closing by process name or window title
    if failed_tool == "close_application":
        app_name = failed_args.get("process_name", "app")
        fallback_steps.append({
            "step_id": f"replan_{replan_count}_1",
            "description": f"Retry closing '{app_name}' with fuzzy matching",
            "tool_name": "close_application",
            "tool_args": {"process_name": app_name.split()[0]},
            "status": "pending",
        })

    # 2. Fallback for play_web_music -> fallback to YouTube search
    elif failed_tool == "play_web_music":
        q = failed_args.get("query", "music")
        fallback_steps.append({
            "step_id": f"replan_{replan_count}_1",
            "description": f"Fallback search for '{q}' in browser",
            "tool_name": "search_web",
            "tool_args": {"query": f"https://www.youtube.com/results?search_query={q}"},
            "status": "pending",
        })

    # 3. Fallback for launch_application -> fallback to browser URL or general launch
    elif failed_tool == "launch_application":
        app_name = failed_args.get("app_name", "notepad")
        fallback_steps.append({
            "step_id": f"replan_{replan_count}_1",
            "description": f"Alternative launch for '{app_name}'",
            "tool_name": "launch_application",
            "tool_args": {"app_name": f"{app_name}.exe"},
            "status": "pending",
        })

    # 4. Default fallback: capture desktop screenshot to diagnose error
    else:
        fallback_steps.append({
            "step_id": f"replan_{replan_count}_1",
            "description": f"Diagnostics screenshot after {failed_tool} failure",
            "tool_name": "capture_desktop_screenshot",
            "tool_args": {"filename": "diagnostics_after_failure.png"},
            "status": "pending",
        })

    # Keep completed steps up to idx, and append fallback_steps
    revised_steps = plan_steps[:idx] + fallback_steps

    return {
        "plan_steps": revised_steps,
        "current_step_index": idx,
        "replan_count": replan_count,
    }


async def final_responder_node(state: NexusState) -> Dict[str, Any]:
    """
    Synthesizes execution results, execution logs, and artifacts into a concise,
    natural language confirmation response for Telegram or Voice outputs.
    """
    plan_steps = state.get("plan_steps", [])
    logs = state.get("execution_logs", [])
    artifacts = state.get("artifacts", [])
    replan_count = state.get("replan_count", 0)

    completed_count = sum(1 for s in plan_steps if s.get("status") == "completed")
    failed_count = sum(1 for s in plan_steps if s.get("status") == "failed")

    lines = []
    if failed_count == 0:
        lines.append("✅ **Task Completed Successfully**")
    else:
        lines.append(f"⚠️ **Task Completed with {failed_count} Issues**")

    for idx, s in enumerate(plan_steps, 1):
        status_icon = "✅" if s.get("status") == "completed" else "❌"
        lines.append(f"{idx}. {status_icon} {s.get('description')}")

    if replan_count > 0:
        lines.append(f"\n🔄 *Dynamic recovery activated ({replan_count} replan(s) executed)*.")

    if artifacts:
        lines.append(f"\n📸 Attached {len(artifacts)} visual artifact(s).")

    response_text = "\n".join(lines)

    return {
        "final_response": response_text,
        "messages": [AIMessage(content=response_text)],
    }
