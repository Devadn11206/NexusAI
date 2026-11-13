"""NEXUS AI - Async Subprocess Runner, Log Monitor & Runtime Error Detector.
Spawns applications on available localhost ports (8010-8099), captures stdout/stderr in a rolling ring buffer,
runs automated pytest/health smoke tests, and extracts structured error diagnostics.
"""

from __future__ import annotations

import asyncio
import collections
import os
import re
import socket
import sys
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple


def find_free_port(start_port: int = 8010, max_port: int = 8099) -> int:
    """Find an available port in the designated developer range."""
    for port in range(start_port, max_port + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return 8010


class RuntimeMonitor:
    """Manages subprocess execution, rolling logs, and real-time failure parsing."""

    def __init__(self, max_log_lines: int = 500):
        self.logs: Deque[str] = collections.deque(maxlen=max_log_lines)
        self.process: Optional[asyncio.subprocess.Process] = None
        self.port: Optional[int] = None

    def append_log(self, line: str) -> None:
        """Add log line to rolling ring buffer."""
        self.logs.append(line)

    def get_logs(self, tail: int = 100) -> List[str]:
        """Return the most recent log lines."""
        return list(self.logs)[-tail:]

    def parse_diagnostics(self, log_text: Optional[str] = None) -> List[Dict[str, Any]]:
        """Parse log text or buffer for Python tracebacks, syntax errors, and 500 responses."""
        target_text = log_text if log_text is not None else "\n".join(self.logs)
        diagnostics = []

        # 1. Detect Python Tracebacks
        tb_pattern = re.compile(
            r'File "([^"]+)", line (\d+), in ([^\n]+)\n\s*(.*?)\n([A-Za-z0-9_]+Error:[^\n]+)',
            re.DOTALL
        )
        for match in tb_pattern.finditer(target_text):
            diagnostics.append({
                "error_type": "PythonTraceback",
                "file_path": match.group(1),
                "line_number": int(match.group(2)),
                "function": match.group(3),
                "code_snippet": match.group(4).strip(),
                "exception": match.group(5).strip(),
                "stack_trace": match.group(0),
            })

        # 2. Detect SyntaxError / IndentationError
        syntax_pattern = re.compile(
            r'File "([^"]+)", line (\d+)\n\s*(.*?)\n\s*\^\s*\n([A-Za-z0-9_]+Error:[^\n]+)'
        )
        for match in syntax_pattern.finditer(target_text):
            diagnostics.append({
                "error_type": "SyntaxError",
                "file_path": match.group(1),
                "line_number": int(match.group(2)),
                "code_snippet": match.group(3).strip(),
                "exception": match.group(4).strip(),
                "stack_trace": match.group(0),
            })

        # 3. Detect HTTP 500 Internal Server Errors
        http_500_pattern = re.compile(r'(?:POST|GET|PUT|DELETE)\s+([^\s]+)\s+HTTP/[0-9.]+"\s+500\b')
        for match in http_500_pattern.finditer(target_text):
            diagnostics.append({
                "error_type": "HTTP500InternalServerError",
                "endpoint": match.group(1),
                "message": "Endpoint returned 500 Internal Server Error",
                "stack_trace": match.group(0),
            })

        # 4. Detect Pytest FAILURES / ERRORS
        pytest_fail_pattern = re.compile(r'FAILED\s+([^\s:]+)::([^\s]+)\s+-\s+([^\n]+)')
        for match in pytest_fail_pattern.finditer(target_text):
            diagnostics.append({
                "error_type": "PytestFailure",
                "file_path": match.group(1),
                "test_name": match.group(2),
                "failure_reason": match.group(3),
                "stack_trace": match.group(0),
            })

        return diagnostics

    async def run_pytest_in_project(self, project_dir: str) -> Dict[str, Any]:
        """Execute pytest in project directory and return structured results and diagnostics."""
        proj_path = Path(project_dir)
        if not proj_path.exists():
            raise FileNotFoundError(f"Project directory not found: {project_dir}")

        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "pytest", "tests/", "-v",
            cwd=str(proj_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        raw_output = stdout.decode("utf-8", errors="replace") + "\n" + stderr.decode("utf-8", errors="replace")

        for line in raw_output.splitlines():
            self.append_log(line)

        diagnostics = self.parse_diagnostics(raw_output)
        passed = (proc.returncode == 0)

        return {
            "status": "passed" if passed else "failed",
            "returncode": proc.returncode,
            "diagnostics": diagnostics,
            "raw_output": raw_output,
        }

    async def start_server(self, project_dir: str, port: Optional[int] = None) -> int:
        """Start FastAPI/uvicorn server as async subprocess."""
        self.port = port or find_free_port()
        proj_path = Path(project_dir)

        cmd = [
            sys.executable, "-m", "uvicorn", "main:app",
            "--port", str(self.port),
            "--host", "127.0.0.1",
        ]

        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(proj_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        async def _read_stream(stream, prefix):
            while True:
                line = await stream.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").rstrip()
                self.append_log(f"[{prefix}] {decoded}")

        if self.process.stdout and self.process.stderr:
            asyncio.create_task(_read_stream(self.process.stdout, "OUT"))
            asyncio.create_task(_read_stream(self.process.stderr, "ERR"))

        # Wait briefly for startup
        await asyncio.sleep(1.0)
        return self.port

    async def stop_server(self) -> None:
        """Terminate the running subprocess."""
        if self.process:
            try:
                self.process.terminate()
                await asyncio.sleep(0.5)
                if self.process.returncode is None:
                    self.process.kill()
            except Exception:
                pass
            self.process = None

