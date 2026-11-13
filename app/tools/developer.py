import asyncio
import logging
import os
import re
import shlex
import sys
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from app.core.security import resolve_safe_workspace_path
from app.config import settings

logger = logging.getLogger(__name__)

# Patterns that indicate potentially destructive, dangerous, or unauthorized operations
DESTRUCTIVE_COMMAND_PATTERNS = [
    # Shell & Filesystem destruction
    r"\brm\s+-[rfRF]{1,4}\b",
    r"\bdel\s+/[sfqSFQ]{1,4}\b",
    r"\berase\s+/[sfqSFQ]{1,4}\b",
    r"\brmdir\s+/[sqSQ]{1,4}\b",
    r"\bformat\b\s+[a-zA-Z]:",
    r"\bmkfs\b",
    r"\bdiskpart\b",
    r"\bdd\s+if=",
    # System modification / privilege escalation
    r"\bchmod\s+-[rR]\s+777\s+/",
    r"\bchown\s+-[rR]\b",
    r"\b(shutdown|reboot|init\s+0|init\s+6)\b",
    r"\bnet\s+user\b",
    r"\breg\s+delete\b",
    # Database destruction
    r"\bdrop\s+(database|schema|table)\b",
    r"\btruncate\s+table\b",
]

COMPILED_DESTRUCTIVE_REGEX = [re.compile(p, re.IGNORECASE) for p in DESTRUCTIVE_COMMAND_PATTERNS]


def is_command_destructive(command: str) -> Tuple[bool, Optional[str]]:
    """
    Scans a shell command for dangerous, system-altering, or destructive patterns.
    Returns (is_destructive: bool, reason: Optional[str]).
    """
    clean_cmd = command.strip()
    for pattern, regex in zip(DESTRUCTIVE_COMMAND_PATTERNS, COMPILED_DESTRUCTIVE_REGEX):
        if regex.search(clean_cmd):
            return True, f"Command matched dangerous pattern: '{pattern}'"
    return False, None


async def execute_shell_command(
    command: str,
    cwd: Optional[str] = None,
    timeout: int = 60,
    env: Optional[Dict[str, str]] = None,
    allow_destructive: bool = False,
) -> Dict[str, Any]:
    """
    Executes a shell command asynchronously inside the sandboxed workspace.
    Enforces path traversal safety and destructive command checks.
    """
    # 1. Destructive command check
    is_destructive, reason = is_command_destructive(command)
    if is_destructive and not allow_destructive:
        logger.warning(f"[DeveloperEngine] Blocked destructive command: '{command}'. Reason: {reason}")
        return {
            "status": "blocked",
            "command": command,
            "requires_hitl": True,
            "reason": reason,
            "stdout": "",
            "stderr": f"Security Alert: Command blocked by safety gate. {reason}",
            "exit_code": -1,
        }

    # 2. Resolve safe working directory
    workspace_dir = Path(settings.WORKSPACE_DIR).resolve()
    workspace_dir.mkdir(parents=True, exist_ok=True)

    target_cwd = workspace_dir
    if cwd:
        try:
            target_cwd = resolve_safe_workspace_path(cwd)
        except PermissionError as pe:
            logger.error(f"[DeveloperEngine] Sandboxed path escape attempt: {pe}")
            return {
                "status": "failed",
                "command": command,
                "error": str(pe),
                "exit_code": -1,
            }

    exec_env = os.environ.copy()
    if env:
        exec_env.update(env)

    # 3. Asynchronously execute process
    start_time = time.time()
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=str(target_cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=exec_env,
        )

        stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        duration = round(time.time() - start_time, 3)

        stdout = stdout_bytes.decode(errors="replace")
        stderr = stderr_bytes.decode(errors="replace")

        status_str = "success" if proc.returncode == 0 else "failed"

        # Truncate excessive outputs to prevent token bloat
        max_output_len = 10000
        truncated = False
        if len(stdout) > max_output_len:
            stdout = stdout[:max_output_len] + f"\n... [Output truncated after {max_output_len} chars]"
            truncated = True

        return {
            "status": status_str,
            "command": command,
            "exit_code": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "duration_seconds": duration,
            "cwd": str(target_cwd),
            "output_truncated": truncated,
        }

    except asyncio.TimeoutError:
        duration = round(time.time() - start_time, 3)
        try:
            proc.kill()
        except Exception:
            pass
        logger.error(f"[DeveloperEngine] Command timed out after {timeout}s: '{command}'")
        return {
            "status": "timeout",
            "command": command,
            "exit_code": -1,
            "error": f"Command timed out after {timeout} seconds",
            "duration_seconds": duration,
        }
    except Exception as exc:
        duration = round(time.time() - start_time, 3)
        logger.error(f"[DeveloperEngine] Command execution error: {exc}")
        return {
            "status": "failed",
            "command": command,
            "exit_code": -1,
            "error": str(exc),
            "duration_seconds": duration,
        }


async def execute_python_code(
    code: str,
    filename: Optional[str] = None,
    timeout: int = 60,
    args: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Executes arbitrary Python code inside the sandboxed workspace.
    Writes the script to `./workspace/scripts/` and runs it with the current Python runtime.
    Captures stdout, stderr, and detects any newly generated files.
    """
    workspace_dir = Path(settings.WORKSPACE_DIR).resolve()
    scripts_dir = workspace_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    script_name = filename or f"script_{int(time.time())}.py"
    if not script_name.endswith(".py"):
        script_name += ".py"

    script_path = scripts_dir / script_name

    # Snapshot existing files before execution
    existing_files = {p for p in workspace_dir.rglob("*") if p.is_file()}

    # Write code
    script_path.write_text(code, encoding="utf-8")

    # Build command
    cmd_args = [sys.executable, str(script_path)]
    if args:
        cmd_args.extend(args)

    cmd_str = " ".join(f'"{a}"' if " " in a else a for a in cmd_args)

    result = await execute_shell_command(
        command=cmd_str,
        cwd=".",
        timeout=timeout,
    )

    # Detect generated artifacts
    current_files = {p for p in workspace_dir.rglob("*") if p.is_file()}
    new_files = [
        str(f.relative_to(workspace_dir))
        for f in (current_files - existing_files)
        if f != script_path and not f.name.endswith(".pyc")
    ]

    result["script_path"] = str(script_path.relative_to(workspace_dir))
    result["generated_artifacts"] = new_files
    result["tool"] = "execute_python_code"

    return result


async def run_git_command(
    subcommand: str,
    args: Optional[List[str]] = None,
    cwd: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Runs safe git operations (e.g. status, diff, log, commit) within the workspace directory.
    """
    allowed_subcommands = {"status", "diff", "log", "branch", "checkout", "add", "commit", "clone"}
    sub_clean = subcommand.strip().lower()

    if sub_clean not in allowed_subcommands:
        return {
            "status": "failed",
            "error": f"Disallowed git subcommand '{subcommand}'. Allowed: {sorted(list(allowed_subcommands))}",
        }

    cmd_parts = ["git", sub_clean]
    if args:
        cmd_parts.extend(args)

    cmd_str = " ".join(f'"{a}"' if " " in a else a for a in cmd_parts)

    return await execute_shell_command(
        command=cmd_str,
        cwd=cwd or ".",
        timeout=30,
    )

