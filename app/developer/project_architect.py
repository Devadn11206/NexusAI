"""NEXUS AI - Autonomous Project Architect & Scaffold Generator.
Analyzes natural-language software requirements, creates structured project file-trees,
and scaffolds production-ready full-stack applications in `./workspace/projects/<slug>/`.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECTS_ROOT = Path("./workspace/projects")


def slugify(text: str) -> str:
    """Generate a clean URL/directory slug from input text."""
    clean = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    slug = re.sub(r"[-\s]+", "_", clean)
    return slug[:50] or "generated_app"


def plan_project_architecture(requirements: str) -> Dict[str, Any]:
    """Analyze requirements and plan the multi-file architecture of the application."""
    req_lower = requirements.lower()

    # Determine primary domain & features
    domain = "general"
    if any(k in req_lower for k in ["attendance", "student", "class", "school"]):
        domain = "student_attendance"
    elif any(k in req_lower for k in ["task", "todo", "kanban", "project"]):
        domain = "task_tracker"
    elif any(k in req_lower for k in ["inventory", "store", "product", "stock"]):
        domain = "inventory_management"
    elif any(k in req_lower for k in ["chat", "message", "forum"]):
        domain = "messaging_app"
    elif any(k in req_lower for k in ["budget", "finance", "expense"]):
        domain = "expense_tracker"

    slug = slugify(requirements.split("\n")[0])
    if len(slug) < 4:
        slug = f"{domain}_app"

    file_tree = [
        "main.py",
        "models.py",
        "schemas.py",
        "database.py",
        "static/index.html",
        "static/style.css",
        "static/app.js",
        "tests/__init__.py",
        "tests/test_app.py",
        "requirements.txt",
        "README.md",
    ]

    return {
        "slug": slug,
        "domain": domain,
        "requirements": requirements,
        "file_tree": file_tree,
        "project_dir": str((PROJECTS_ROOT / slug).resolve()),
    }


def scaffold_project(architecture: Dict[str, Any]) -> str:
    """Create directory structure and empty placeholders for planned project files."""
    proj_dir = Path(architecture["project_dir"])
    proj_dir.mkdir(parents=True, exist_ok=True)

    for relative_path in architecture["file_tree"]:
        file_path = proj_dir / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if not file_path.exists():
            file_path.touch()

    return str(proj_dir.resolve())

