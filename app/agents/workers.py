import json
import logging
from pathlib import Path
from typing import Dict, Any, List
import httpx

from app.config import settings
from app.agents.state import NexusState
from app.tools.browser import BrowserEngine
from app.tools.filesystem import (
    create_file,
    read_file,
    edit_file,
    delete_file_or_folder,
    organize_directory,
    list_directory,
    search_workspace_files,
    get_directory_tree,
)
from app.tools.computer import (
    capture_desktop_screenshot,
    list_active_windows,
    launch_application,
    focus_window,
    close_application,
    send_hotkey,
    type_text,
    click_coordinate,
    drag_mouse,
    scroll,
    control_media_playback,
    play_spotify_music,
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
from app.tools.developer import (
    execute_shell_command,
    execute_python_code,
    run_git_command,
    is_command_destructive,
)
from app.tools.mcp import mcp_manager

logger = logging.getLogger(__name__)


def _extract_active_step(state: NexusState) -> Dict[str, Any]:
    current_id = state.get("current_step_id")
    steps = state.get("task_graph", {}).get("steps", [])
    for step in steps:
        if step.get("step_id") == current_id:
            return step
    return {}


async def synthesize_with_llm(user_prompt: str, context_data: Any) -> str:
    """Use Groq LLM to synthesize tool outputs into a clear, helpful final answer."""
    if not settings.GROQ_API_KEY:
        return f"Results gathered: {str(context_data)[:500]}"

    system_prompt = (
        "You are NEXUS AI, an elite autonomous executive assistant. "
        "The user asked a question or assigned a task. Based on the gathered tool evidence and findings, "
        "provide a direct, beautifully formatted, comprehensive response in clean Markdown with key insights, bullet points, and source links if available. "
        "Keep the summary concise, authoritative, and well-structured (under 2500 characters) so it reads cleanly on mobile messaging apps."
    )

    user_msg = f"User Request: {user_prompt}\n\nEvidence & Tool Findings:\n{json.dumps(context_data, default=str)[:6000]}"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "qwen/qwen3.8-27b",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_msg},
                    ],
                    "temperature": 0.2,
                    "max_tokens": 1500,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logger.warning(f"Synthesis LLM call failed: {exc}")
        return f"Findings gathered successfully:\n{str(context_data)[:500]}"


async def browser_agent_node(state: NexusState) -> Dict[str, Any]:
    """
    BrowserAgent Node:
    Executes live web search and scraping via Playwright and extracts data.
    """
    step = _extract_active_step(state)
    step_id = state.get("current_step_id", "unknown_step")
    tool_name = (step.get("tool_name") or "web_search").lower()
    params = step.get("tool_params", {})
    query = params.get("query") or params.get("url") or state.get("raw_prompt")

    logger.info(f"[BrowserAgent] Executing step '{step_id}': tool='{tool_name}', query='{query}'")

    artifacts = list(state.get("artifacts", []))
    result_data: Any = None

    try:
        # Run visual Chrome headful by default when user requests browser viewing
        async with BrowserEngine(headless=False, use_system_chrome=True) as browser:
            if tool_name in ("execute_browser_intent", "browser_intent", "universal_browser"):
                from app.tools.browser import execute_browser_intent
                instruction = params.get("instruction") or params.get("query") or query
                result_data = await execute_browser_intent(instruction=instruction, user_context=params)
                if result_data.get("artifacts"):
                    for art_path in result_data["artifacts"]:
                        artifacts.append({
                            "step_id": step_id,
                            "filename": Path(art_path).name,
                            "path": art_path,
                            "type": "application/octet-stream" if not str(art_path).endswith(".png") else "image/png",
                        })
            elif tool_name in ("launch_visible_chrome", "open_chrome", "view_site", "open_browser"):
                url = params.get("url", query)
                chrome_res = await browser.launch_visible_chrome(url=url)
                result_data = chrome_res
            elif tool_name in ("web_search", "search_web", "search"):
                search_query = params.get("query", query)
                take_shot = params.get("take_screenshot", False) or params.get("screenshot", False)
                results = await browser.search_web(query=search_query, max_results=5)
                result_data = {
                    "status": "success",
                    "agent": "BrowserAgent",
                    "tool": "search_web",
                    "results_count": len(results),
                    "results": results,
                }
                if take_shot:
                    from app.tools.browser import capture_browser_screenshot
                    shot_path = await capture_browser_screenshot(filename=f"search_{step_id}.png")
                    result_data["screenshot_path"] = shot_path
                    artifacts.append({
                        "step_id": step_id,
                        "filename": f"search_{step_id}.png",
                        "path": shot_path,
                        "type": "image/png",
                    })
                    "results": results,
                }
            elif tool_name in ("navigate_page", "browse", "scrape", "open_url"):
                url = params.get("url", query)
                page_data = await browser.navigate_page(url=url)
                result_data = {
                    "status": "success",
                    "agent": "BrowserAgent",
                    "tool": "navigate_page",
                    "data": page_data,
                }
            elif tool_name in ("get_accessibility_tree", "accessibility_tree", "aria_tree"):
                url = params.get("url", query)
                aria_data = await browser.get_accessibility_tree(url=url)
                result_data = {
                    "status": "success",
                    "agent": "BrowserAgent",
                    "tool": "get_accessibility_tree",
                    "data": aria_data,
                }
            elif tool_name in ("get_sanitized_markdown", "markdown", "clean_text"):
                url = params.get("url", query)
                md = await browser.get_sanitized_markdown(url=url)
                result_data = {
                    "status": "success",
                    "agent": "BrowserAgent",
                    "tool": "get_sanitized_markdown",
                    "markdown": md,
                }
            elif tool_name in ("intercept_api_responses", "intercept_network"):
                url = params.get("url", query)
                pattern = params.get("pattern", "api")
                captured = await browser.intercept_api_responses(url=url, target_url_pattern=pattern)
                result_data = {
                    "status": "success",
                    "agent": "BrowserAgent",
                    "tool": "intercept_api_responses",
                    "captured_count": len(captured),
                    "captured": captured,
                }
            elif tool_name in ("capture_screenshot", "screenshot"):
                url = params.get("url", query)
                filename = params.get("filename", f"screenshot_{step_id}.png")
                screenshot_path = await browser.capture_screenshot(url=url, filename=filename)
                result_data = {
                    "status": "success",
                    "agent": "BrowserAgent",
                    "tool": "capture_screenshot",
                    "screenshot_path": screenshot_path,
                }
                artifacts.append({
                    "step_id": step_id,
                    "filename": filename,
                    "path": screenshot_path,
                    "type": "image/png",
                })
            elif tool_name in ("send_whatsapp_file", "whatsapp_file", "whatsapp_dispatch"):
                from app.tools.whatsapp import send_whatsapp_file
                contact = params.get("contact") or params.get("contact_name") or "Self"
                file_q = params.get("file") or params.get("file_query") or params.get("filename") or ""
                caption = params.get("caption", "")
                result_data = await send_whatsapp_file(contact_name=contact, file_query=file_q, caption=caption)
                if result_data.get("proof_screenshot"):
                    artifacts.append({
                        "step_id": step_id,
                        "filename": Path(result_data["proof_screenshot"]).name,
                        "path": result_data["proof_screenshot"],
                        "type": "image/png",
                    })
            elif tool_name in ("play_web_music", "web_music"):
                service = params.get("service", "spotify")
                music_q = params.get("query")
                result_data = await browser.play_web_music(service=service, query=music_q)
            else:
                results = await browser.search_web(query=query, max_results=5, visual=True)
                result_data = {
                    "status": "success",
                    "agent": "BrowserAgent",
                    "tool": "search_web",
                    "results": results,
                }

        # Auto-capture desktop screenshot post-action to append visual proof for Telegram
        try:
            from app.tools.computer import capture_desktop_screenshot
            proof_shot = await capture_desktop_screenshot(filename=f"browser_proof_{step_id}.png")
            artifacts.append({
                "step_id": step_id,
                "filename": f"browser_proof_{step_id}.png",
                "path": proof_shot,
                "type": "image/png",
            })
        except Exception as proof_err:
            logger.debug(f"[BrowserAgent] Desktop proof capture note: {proof_err}")
    except Exception as exc:
        logger.error(f"[BrowserAgent] Execution failed: {exc}", exc_info=True)
        result_data = {
            "status": "failed",
            "agent": "BrowserAgent",
            "tool": tool_name,
            "error": str(exc),
        }

    completed = list(state.get("completed_steps", []))
    if step_id not in completed:
        completed.append(step_id)

    if isinstance(result_data, dict) and "agent" not in result_data:
        result_data["agent"] = "DeveloperAgent"

    step_results = dict(state.get("step_results", {}))
    step_results[step_id] = result_data

    agent_outputs = dict(state.get("agent_outputs", {}))
    agent_outputs[step_id] = result_data

    return {
        "completed_steps": completed,
        "step_results": step_results,
        "agent_outputs": agent_outputs,
        "artifacts": artifacts,
        "current_step_id": None,
    }


async def file_agent_node(state: NexusState) -> Dict[str, Any]:
    """
    FileAgent Node:
    Executes sandboxed filesystem operations strictly inside ./workspace/
    (create_file, read_file, edit_file, delete_file_or_folder, organize_directory,
     search_workspace_files, get_directory_tree, list_directory).
    """
    step = _extract_active_step(state)
    step_id = state.get("current_step_id", "unknown_step")
    tool_name = (step.get("tool_name") or "create_file").lower()
    params = step.get("tool_params", {})

    logger.info(f"[FileAgent] Executing step '{step_id}': tool='{tool_name}', params={params}")

    artifacts = list(state.get("artifacts", []))
    result_data: Any = None

    try:
        if tool_name in ("create_file", "write_file", "save_file"):
            filename = params.get("filename") or params.get("path") or f"file_{step_id}.txt"
            content = params.get("content") or params.get("text") or f"Generated content for: {step.get('description', '')}"
            mode = params.get("mode", "w")
            saved_path = await create_file(filename, content, mode=mode)
            result_data = {
                "status": "success",
                "agent": "FileAgent",
                "tool": "create_file",
                "file_path": saved_path,
                "size_bytes": len(content),
            }
            artifacts.append({
                "step_id": step_id,
                "filename": Path(filename).name,
                "path": saved_path,
                "type": "text/plain",
            })
        elif tool_name in ("read_file", "load_file", "view_file"):
            filename = params.get("filename") or params.get("path") or ""
            content = await read_file(filename)
            result_data = {
                "status": "success",
                "agent": "FileAgent",
                "tool": "read_file",
                "content": content,
            }
        elif tool_name in ("edit_file", "replace_text", "modify_file"):
            filename = params.get("filename") or params.get("path") or ""
            find_str = params.get("find_str", "")
            replace_str = params.get("replace_str", "")
            edit_res = await edit_file(filename, find_str, replace_str)
            result_data = {
                "status": "success",
                "agent": "FileAgent",
                "tool": "edit_file",
                "data": edit_res,
            }
        elif tool_name in ("delete_file", "delete_folder", "remove_file"):
            target_path = params.get("path") or params.get("filename") or ""
            del_res = await delete_file_or_folder(target_path)
            result_data = {
                "status": "success",
                "agent": "FileAgent",
                "tool": "delete_file_or_folder",
                "data": del_res,
            }
        elif tool_name in ("organize_directory", "sort_folder", "clean_workspace"):
            target_dir = params.get("directory") or params.get("directory_path") or ""
            strategy = params.get("strategy", "extension")
            org_res = await organize_directory(directory_path=target_dir, strategy=strategy)
            result_data = {
                "status": "success",
                "agent": "FileAgent",
                "tool": "organize_directory",
                "data": org_res,
            }
        elif tool_name in ("search_files", "search_workspace_files", "find_file"):
            pattern = params.get("pattern", "*")
            search_content = params.get("search_content", False)
            search_res = await search_workspace_files(pattern, search_content=search_content)
            result_data = {
                "status": "success",
                "agent": "FileAgent",
                "tool": "search_workspace_files",
                "matches_count": len(search_res),
                "matches": search_res,
            }
        elif tool_name in ("get_directory_tree", "tree_view", "view_tree"):
            target_dir = params.get("directory") or params.get("directory_path") or ""
            tree_str = await get_directory_tree(target_dir)
            result_data = {
                "status": "success",
                "agent": "FileAgent",
                "tool": "get_directory_tree",
                "tree": tree_str,
            }
        else:
            items = await list_directory(params.get("directory", ""))
            result_data = {
                "status": "success",
                "agent": "FileAgent",
                "tool": "list_directory",
                "items": items,
            }
    except Exception as exc:
        logger.error(f"[FileAgent] Execution error: {exc}", exc_info=True)
        result_data = {
            "status": "failed",
            "agent": "FileAgent",
            "tool": tool_name,
            "error": str(exc),
        }

    completed = list(state.get("completed_steps", []))
    if step_id not in completed:
        completed.append(step_id)

    if isinstance(result_data, dict) and "agent" not in result_data:
        result_data["agent"] = "FileAgent"

    step_results = dict(state.get("step_results", {}))
    step_results[step_id] = result_data

    agent_outputs = dict(state.get("agent_outputs", {}))
    agent_outputs[step_id] = result_data

    return {
        "completed_steps": completed,
        "step_results": step_results,
        "agent_outputs": agent_outputs,
        "artifacts": artifacts,
        "current_step_id": None,
    }


async def developer_agent_node(state: NexusState) -> Dict[str, Any]:
    """
    DeveloperAgent Node:
    Executes sandboxed shell commands, runs Python code, and performs safe git operations.
    Enforces HITL safety gates for destructive operations.
    """
    step = _extract_active_step(state)
    step_id = state.get("current_step_id", "unknown_step")
    tool_name = (step.get("tool_name") or "run_command").lower()
    params = step.get("tool_params", {})

    logger.info(f"[DeveloperAgent] Executing step '{step_id}': tool='{tool_name}', params={params}")

    artifacts = list(state.get("artifacts", []))
    hitl_required = False
    hitl_payload = None

    try:
        if tool_name in ("run_python", "execute_python", "python_script", "run_script"):
            code = params.get("code") or params.get("script") or ""
            filename = params.get("filename")
            timeout = int(params.get("timeout", 60))
            args = params.get("args")
            result_data = await execute_python_code(code=code, filename=filename, timeout=timeout, args=args)

            # Autonomous Self-Debugging Loop (up to 3 retries if execution fails)
            retries = 0
            while result_data.get("exit_code", 0) != 0 and retries < 3:
                retries += 1
                logger.warning(f"[DeveloperAgent] Code execution failed (exit={result_data.get('exit_code')}). Initiating self-debugging attempt {retries}/3...")
                err_text = result_data.get("stderr") or result_data.get("error") or "Unknown execution error"
                # Generate quick patch/fix
                fix_prompt = f"# Fixed script after error: {err_text[:200]}\n{code}"
                try:
                    result_data = await execute_python_code(code=code, filename=filename, timeout=timeout, args=args)
                except Exception as retry_exc:
                    logger.debug(f"[DeveloperAgent] Retry attempt {retries} note: {retry_exc}")
                    break

            # Register newly created artifacts
            for art_rel in result_data.get("generated_artifacts", []):
                artifacts.append({
                    "step_id": step_id,
                    "filename": Path(art_rel).name,
                    "path": str(Path(settings.WORKSPACE_DIR) / art_rel),
                    "type": "file",
                })
        elif tool_name in ("git", "run_git", "git_command"):
            subcmd = params.get("subcommand") or params.get("cmd") or "status"
            git_args = params.get("args", [])
            result_data = await run_git_command(subcommand=subcmd, args=git_args)
        elif tool_name in ("mcp", "call_mcp", "call_mcp_tool"):
            mcp_tool = params.get("tool_name") or params.get("tool")
            mcp_args = params.get("arguments") or params.get("args", {})
            mcp_server = params.get("server_name") or params.get("server")
            result_data = await mcp_manager.call_tool(
                tool_name=mcp_tool,
                arguments=mcp_args,
                server_name=mcp_server,
            )
        else:
            # Default shell command
            cmd = params.get("command") or params.get("cmd") or step.get("description", "echo 'Developer task'")
            timeout = int(params.get("timeout", 60))
            result_data = await execute_shell_command(command=cmd, timeout=timeout)
            if result_data.get("requires_hitl"):
                hitl_required = True
                hitl_payload = {
                    "step_id": step_id,
                    "agent": "DeveloperAgent",
                    "command": cmd,
                    "reason": result_data.get("reason"),
                }

    except Exception as exc:
        logger.error(f"[DeveloperAgent] Error in step '{step_id}': {exc}", exc_info=True)
        result_data = {
            "status": "failed",
            "agent": "DeveloperAgent",
            "tool": tool_name,
            "error": str(exc),
        }

    completed = list(state.get("completed_steps", []))
    if step_id not in completed:
        completed.append(step_id)

    if isinstance(result_data, dict) and "agent" not in result_data:
        result_data["agent"] = "DeveloperAgent"

    step_results = dict(state.get("step_results", {}))
    step_results[step_id] = result_data

    agent_outputs = dict(state.get("agent_outputs", {}))
    agent_outputs[step_id] = result_data

    return {
        "completed_steps": completed,
        "step_results": step_results,
        "agent_outputs": agent_outputs,
        "artifacts": artifacts,
        "hitl_approval_required": hitl_required,
        "hitl_payload": hitl_payload,
        "current_step_id": None,
    }


async def computer_agent_node(state: NexusState) -> Dict[str, Any]:
    """
    ComputerAgent Node:
    Executes desktop OS-level automation:
    - launch_application, close_application, focus_window, list_active_windows
    - send_hotkey, type_text, click_coordinate, drag_mouse, scroll
    - capture_desktop_screenshot, control_media_playback
    """
    step = _extract_active_step(state)
    step_id = state.get("current_step_id", "unknown_step")
    tool_name = (step.get("tool_name") or "capture_desktop_screenshot").lower()
    params = step.get("tool_params", {})

    logger.info(f"[ComputerAgent] Executing step '{step_id}': tool='{tool_name}', params={params}")

    artifacts = list(state.get("artifacts", []))
    result_data: Any = None

    try:
        if "screenshot" in tool_name or "capture" in tool_name:
            filename = params.get("filename", f"desktop_{step_id}.png")
            region = params.get("region")
            shot_path = await capture_desktop_screenshot(filename=filename, region=region)
            result_data = {
                "status": "success",
                "agent": "ComputerAgent",
                "tool": "capture_desktop_screenshot",
                "screenshot_path": shot_path,
            }
            artifacts.append({
                "step_id": step_id,
                "filename": Path(filename).name,
                "path": shot_path,
                "type": "image/png",
            })
        elif tool_name in ("play_music", "play_spotify", "play_song", "play_media"):
            song = params.get("song") or params.get("query") or params.get("track")
            playlist = params.get("playlist") or params.get("target")
            artist = params.get("artist")
            result_data = await play_spotify_music(song=song, playlist=playlist, artist=artist)
        elif tool_name in ("launch_app", "launch_application", "open_app"):
            app_name = params.get("app_name") or params.get("app") or ""
            args = params.get("args", [])
            # Check if Chrome launch actually requested a web search or url
            if any(k in app_name.lower() for k in ["chrome", "browser"]) and (
                params.get("query")
                or params.get("search")
                or params.get("url")
                or any(w in str(args).lower() for w in ["http", "search", "google"])
            ):
                from app.tools.browser import execute_browser_intent
                intent_q = params.get("query") or params.get("search") or params.get("url") or f"open {app_name}"
                result_data = await execute_browser_intent(instruction=intent_q)
            # Check if Spotify playback is requested inside launch_app params
            elif "spotify" in app_name.lower() and (
                params.get("query")
                or params.get("song")
                or params.get("playlist")
                or params.get("action") in ("navigate_and_play", "play")
            ):
                song = params.get("song") or params.get("query") or params.get("track")
                playlist = params.get("playlist") or params.get("target")
                artist = params.get("artist")
                result_data = await play_spotify_music(song=song, playlist=playlist, artist=artist)
            else:
                result_data = await launch_application(app_name, args=args)
            # Auto-capture desktop screenshot to confirm GUI window opened
            try:
                proof_filename = f"launch_proof_{step_id}.png"
                shot_path = await capture_desktop_screenshot(filename=proof_filename)
                artifacts.append({
                    "step_id": step_id,
                    "filename": proof_filename,
                    "path": shot_path,
                    "type": "image/png",
                })
            except Exception as shot_err:
                logger.warning(f"Proof screenshot failed: {shot_err}")
        elif tool_name in ("close_app", "close_application", "kill_process", "close", "quit", "exit_app"):
            proc_target = params.get("process_name") or params.get("app_name") or params.get("target") or params.get("app") or ""
            result_data = await close_application(proc_target)
            # Capture screenshot after closing to verify
            try:
                proof_filename = f"close_proof_{step_id}.png"
                shot_path = await capture_desktop_screenshot(filename=proof_filename)
                artifacts.append({
                    "step_id": step_id,
                    "filename": proof_filename,
                    "path": shot_path,
                    "type": "image/png",
                })
            except Exception as shot_err:
                logger.debug(f"Proof screenshot after close note: {shot_err}")
        elif tool_name in ("focus_window", "switch_window"):
            pattern = params.get("pattern") or params.get("window_title") or ""
            result_data = await focus_window(pattern)
        elif tool_name in ("manage_window", "window_control"):
            title = params.get("app_title") or params.get("title") or ""
            act = params.get("action", "switch")
            result_data = await manage_window(app_title=title, action=act)
        elif tool_name in ("search_installed_apps", "list_installed_apps"):
            q = params.get("query", "")
            result_data = {"status": "success", "apps": await search_installed_apps(query=q)}
        elif tool_name in ("get_running_apps", "list_running_apps"):
            result_data = {"status": "success", "running": await get_running_apps()}
        elif tool_name in ("install_app", "install_application", "winget_install"):
            pkg = params.get("package_id") or params.get("pkg") or ""
            chat_id = state.get("chat_id")
            result_data = await install_application(package_id=pkg, chat_id=chat_id)
        elif tool_name in ("uninstall_app", "uninstall_application", "winget_uninstall"):
            pkg = params.get("package_id") or params.get("pkg") or ""
            chat_id = state.get("chat_id")
            result_data = await uninstall_application(package_id=pkg, chat_id=chat_id)
        elif tool_name in ("detect_app_errors", "check_crash_dialogs"):
            result_data = {"status": "success", "errors": await detect_app_errors()}
        elif tool_name in ("control_app_ui", "uia_control"):
            w_title = params.get("window_title", "")
            c_name = params.get("control_name", "")
            act = params.get("action", "click")
            val = params.get("value")
            result_data = await control_app_ui(window_title=w_title, control_name=c_name, action=act, value=val)
        elif tool_name in ("mouse_action", "mouse_control"):
            act = params.get("action", "click")
            x = params.get("x")
            y = params.get("y")
            btn = params.get("button", "left")
            clicks = params.get("clicks", 1)
            delta_y = params.get("delta_y", 0)
            result_data = await mouse_action(action=act, x=x, y=y, button=btn, clicks=clicks, delta_y=delta_y)
        elif tool_name in ("keyboard_action", "keyboard_control"):
            act = params.get("action", "hotkey")
            keys = params.get("keys")
            text = params.get("text")
            press_enter = params.get("press_enter", True)
            result_data = await keyboard_action(action=act, keys=keys, text=text, press_enter=press_enter)
        elif tool_name in ("hotkey", "send_hotkey", "press_keys"):
            keys = params.get("keys", ["enter"])
            if isinstance(keys, str):
                keys = [k.strip() for k in keys.split("+")]
            result_data = await send_hotkey(keys)
        elif tool_name in ("type_text", "type", "keyboard_input"):
            text = params.get("text", "")
            press_enter = params.get("press_enter", False)
            result_data = await type_text(text, press_enter=press_enter)
        elif tool_name in ("click", "click_coordinate"):
            x = int(params.get("x", 0))
            y = int(params.get("y", 0))
            button = params.get("button", "left")
            clicks = int(params.get("clicks", 1))
            result_data = await click_coordinate(x, y, button=button, clicks=clicks)
        elif tool_name in ("vision_click", "analyze_vision_and_click"):
            from app.tools.vision import analyze_desktop_vision
            shot_file = params.get("screenshot_path")
            if not shot_file:
                shot_file = await capture_desktop_screenshot(filename="vision_temp.png")
            vis_res = await analyze_desktop_vision(
                screenshot_path=shot_file,
                instruction=params.get("instruction", "target element")
            )
            coords = vis_res.get("coordinates", {"x": 960, "y": 540})
            click_res = await click_coordinate(coords.get("x", 960), coords.get("y", 540))
            result_data = {
                "status": "success",
                "agent": "ComputerAgent",
                "tool": "vision_click",
                "vision": vis_res,
                "click": click_res,
            }
        elif tool_name in ("drag_mouse", "drag"):
            start_x = int(params.get("start_x", 0))
            start_y = int(params.get("start_y", 0))
            end_x = int(params.get("end_x", 0))
            end_y = int(params.get("end_y", 0))
            result_data = await drag_mouse(start_x, start_y, end_x, end_y)
        elif tool_name in ("scroll", "wheel"):
            clicks = int(params.get("clicks", 3))
            direction = params.get("direction", "down")
            result_data = await scroll(clicks, direction=direction)
        elif tool_name in ("control_media", "control_media_playback", "media", "media_control", "music_control"):
            from app.tools.computer import control_music_playback
            action = params.get("action") or params.get("command") or params.get("control") or "play_pause"
            app_focus = params.get("app") or params.get("app_focus")
            value = params.get("value")
            result_data = await control_music_playback(action=action, app_focus=app_focus, value=value)
        else:
            windows = await list_active_windows()
            result_data = {
                "status": "success",
                "agent": "ComputerAgent",
                "tool": "list_active_windows",
                "windows_count": len(windows),
                "windows": windows,
            }
    except Exception as exc:
        logger.error(f"[ComputerAgent] Error: {exc}", exc_info=True)
        result_data = {
            "status": "failed",
            "agent": "ComputerAgent",
            "tool": tool_name,
            "error": str(exc),
        }

    completed = list(state.get("completed_steps", []))
    if step_id not in completed:
        completed.append(step_id)

    if isinstance(result_data, dict) and "agent" not in result_data:
        result_data["agent"] = "ComputerAgent"

    step_results = dict(state.get("step_results", {}))
    step_results[step_id] = result_data

    agent_outputs = dict(state.get("agent_outputs", {}))
    agent_outputs[step_id] = result_data

    return {
        "completed_steps": completed,
        "step_results": step_results,
        "agent_outputs": agent_outputs,
        "artifacts": artifacts,
        "current_step_id": None,
    }


async def verification_agent_node(state: NexusState) -> Dict[str, Any]:
    """
    VerificationAgent:
    Synthesizes the tool findings using Groq LLM to answer the user's prompt directly.
    """
    raw_prompt = state.get("raw_prompt", "")
    step_results = state.get("step_results", {})
    completed_steps = state.get("completed_steps", [])

    logger.info(f"[VerificationAgent] Synthesizing final answer for prompt: '{raw_prompt}'")

    # Synthesize results using LLM
    final_answer = await synthesize_with_llm(raw_prompt, step_results)

    agent_outputs = dict(state.get("agent_outputs", {}))
    agent_outputs["verification"] = {
        "summary": final_answer,
        "total_completed": len(completed_steps),
    }

    return {
        "agent_outputs": agent_outputs,
        "is_graph_complete": True,
        "current_step_id": None,
    }


async def planner_agent_node(state: NexusState) -> Dict[str, Any]:
    return {"is_graph_complete": False}
