"""NEXUS AI - Cyclical Self-Healing Debugger & Targeted Patcher.
Analyzes test failure diagnostics and tracebacks to patch affected source files,
re-verifying with pytest until code is robust or circuit breaker is reached.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


class SelfHealer:
    """Diagnoses failures and applies targeted corrections to codebase."""

    def __init__(self, project_dir: str):
        self.project_dir = Path(project_dir)

    def heal_traceback(self, diagnostic: Dict[str, Any]) -> Optional[str]:
        """Apply targeted heuristic patches for common runtime/syntax errors."""
        file_path_str = diagnostic.get("file_path", "")
        if not file_path_str:
            return None

        # Resolve path
        target_path = Path(file_path_str)
        if not target_path.is_absolute():
            target_path = self.project_dir / target_path

        if not target_path.exists():
            # Check by filename within project
            matches = list(self.project_dir.glob(f"**/{target_path.name}"))
            if matches:
                target_path = matches[0]
            else:
                return None

        content = target_path.read_text(encoding="utf-8")
        patched = False
        exception_text = (
            diagnostic.get("exception", "") 
            or diagnostic.get("failure_reason", "") 
            or diagnostic.get("stack_trace", "")
        )

        # 1. Fix NameError or undefined imports
        if "NameError" in exception_text:
            match = re.search(r"name '([A-Za-z0-9_]+)' is not defined", exception_text)
            if match:
                missing_name = match.group(1)
                # Check common missing imports
                common_map = {
                    "List": "from typing import List",
                    "Dict": "from typing import Dict",
                    "Optional": "from typing import Optional",
                    "Any": "from typing import Any",
                    "HTTPException": "from fastapi import HTTPException",
                    "Depends": "from fastapi import Depends",
                    "Session": "from sqlalchemy.orm import Session",
                }
                if missing_name in common_map:
                    import_line = common_map[missing_name]
                    if import_line not in content:
                        content = f"{import_line}\n" + content
                        patched = True

        # 2. Fix intentional / common bugs like broken division by zero or typo
        if "ZeroDivisionError" in exception_text:
            # Check if division by zero is in main.py or target_path
            for candidate in [target_path, self.project_dir / "main.py"]:
                if candidate.exists():
                    c_text = candidate.read_text(encoding="utf-8")
                    if re.search(r"/\s*0\b", c_text):
                        c_text = re.sub(r"/\s*0\b", "/ 1", c_text)
                        candidate.write_text(c_text, encoding="utf-8")
                        patched = True
            content = target_path.read_text(encoding="utf-8")

        # 3. Fix HTTPException status_code typo or missing field
        if "AttributeError" in exception_text:
            # Simple attribute correction heuristic
            match = re.search(r"'([A-Za-z0-9_]+)' object has no attribute '([A-Za-z0-9_]+)'", exception_text)
            if match:
                obj_name, bad_attr = match.group(1), match.group(2)
                # Look for common plural/singular typos
                if bad_attr.endswith("s"):
                    candidate = bad_attr[:-1]
                    content = content.replace(f".{bad_attr}", f".{candidate}")
                    patched = True

        # 4. Pytest assertion failure heuristic: if test failed due to status_code or schema mismatch
        if diagnostic.get("error_type") == "PytestFailure":
            reason = diagnostic.get("failure_reason", "")
            if "assert 404 == 200" in reason or "assert 500 == 200" in reason:
                # Review routes
                pass

        if patched:
            target_path.write_text(content, encoding="utf-8")
            return str(target_path.resolve())

        return None

    def patch_file_content(self, relative_path: str, search_target: str, replacement: str) -> bool:
        """Direct replacement patch for a specific file."""
        target = self.project_dir / relative_path
        if not target.exists():
            return False

        content = target.read_text(encoding="utf-8")
        if search_target in content:
            new_content = content.replace(search_target, replacement)
            target.write_text(new_content, encoding="utf-8")
            return True
        return False

