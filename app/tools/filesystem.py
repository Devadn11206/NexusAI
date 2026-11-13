import asyncio
import logging
import os
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional

from app.core.security import resolve_safe_workspace_path
from app.config import settings

logger = logging.getLogger(__name__)

# Exhaustive categorization mapping for intelligent organization
EXTENSION_CATEGORY_MAP = {
    # Documents
    ".pdf": "documents",
    ".docx": "documents",
    ".doc": "documents",
    ".txt": "documents",
    ".md": "documents",
    ".pptx": "documents",
    ".ppt": "documents",
    ".rtf": "documents",
    ".odt": "documents",
    # Data & Spreadsheets
    ".xlsx": "data",
    ".xls": "data",
    ".csv": "data",
    ".json": "data",
    ".xml": "data",
    ".yaml": "data",
    ".yml": "data",
    ".parquet": "data",
    ".tsv": "data",
    # Images & Graphics
    ".png": "images",
    ".jpg": "images",
    ".jpeg": "images",
    ".gif": "images",
    ".svg": "images",
    ".webp": "images",
    ".ico": "images",
    ".bmp": "images",
    # Audio & Sound
    ".mp3": "audio",
    ".ogg": "audio",
    ".wav": "audio",
    ".m4a": "audio",
    ".flac": "audio",
    # Code & Development
    ".py": "code",
    ".js": "code",
    ".ts": "code",
    ".html": "code",
    ".css": "code",
    ".sh": "code",
    ".bat": "code",
    ".ps1": "code",
    ".sql": "code",
    ".cpp": "code",
    ".java": "code",
    ".rs": "code",
    # Archives
    ".zip": "archives",
    ".tar": "archives",
    ".gz": "archives",
    ".7z": "archives",
    ".rar": "archives",
}


async def create_file(path: str, content: str, mode: str = "w") -> str:
    """
    Creates or overwrites a file inside ./workspace/.
    Enforces path traversal isolation via resolve_safe_workspace_path.
    Returns the absolute path string.
    """
    safe_path = resolve_safe_workspace_path(path)
    safe_path.parent.mkdir(parents=True, exist_ok=True)

    def _sync_write():
        with open(safe_path, mode, encoding="utf-8") as f:
            f.write(content)

    await asyncio.to_thread(_sync_write)
    logger.info(f"[Filesystem] Created file: {safe_path} ({len(content)} chars)")
    return str(safe_path)


async def read_file(path: str, encoding: str = "utf-8") -> str:
    """
    Reads file content safely from within ./workspace/.
    Raises FileNotFoundError or PermissionError on boundary violations.
    """
    safe_path = resolve_safe_workspace_path(path)
    if not safe_path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if not safe_path.is_file():
        raise IsADirectoryError(f"Target path is a directory: {path}")

    def _sync_read():
        with open(safe_path, "r", encoding=encoding, errors="replace") as f:
            return f.read()

    return await asyncio.to_thread(_sync_read)


async def edit_file(path: str, find_str: str, replace_str: str) -> Dict[str, Any]:
    """
    Finds and replaces text patterns in an existing workspace document.
    """
    safe_path = resolve_safe_workspace_path(path)
    if not safe_path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    def _sync_edit():
        with open(safe_path, "r", encoding="utf-8", errors="replace") as f:
            original = f.read()
        occurrences = original.count(find_str)
        if occurrences == 0:
            return {"status": "unchanged", "occurrences": 0, "path": str(safe_path)}

        modified = original.replace(find_str, replace_str)
        with open(safe_path, "w", encoding="utf-8") as f:
            f.write(modified)
        return {"status": "success", "occurrences": occurrences, "path": str(safe_path)}

    return await asyncio.to_thread(_sync_edit)


async def delete_file_or_folder(path: str) -> Dict[str, Any]:
    """
    Safely deletes a file or directory within ./workspace/.
    Cannot delete the root workspace folder.
    """
    safe_path = resolve_safe_workspace_path(path)
    workspace_root = Path(settings.WORKSPACE_DIR).resolve()

    if safe_path == workspace_root:
        raise PermissionError("Deleting the root workspace folder is strictly prohibited.")

    if not safe_path.exists():
        return {"status": "not_found", "path": str(safe_path)}

    def _sync_delete():
        if safe_path.is_dir():
            shutil.rmtree(safe_path)
            return {"status": "success", "type": "directory", "path": str(safe_path)}
        else:
            safe_path.unlink()
            return {"status": "success", "type": "file", "path": str(safe_path)}

    return await asyncio.to_thread(_sync_delete)


async def list_directory(directory: str = "") -> List[Dict[str, Any]]:
    """
    Enumerates files and directories inside ./workspace/ or subfolder.
    """
    safe_dir = resolve_safe_workspace_path(directory)
    if not safe_dir.exists():
        return []

    def _sync_list():
        items = []
        for item in safe_dir.iterdir():
            items.append({
                "name": item.name,
                "is_dir": item.is_dir(),
                "size_bytes": item.stat().st_size if item.is_file() else 0,
                "path": str(item),
            })
        return items

    return await asyncio.to_thread(_sync_list)


async def search_workspace_files(pattern: str, search_content: bool = False) -> List[Dict[str, Any]]:
    """
    Searches workspace files by glob name pattern or by inspecting text contents.
    """
    workspace_root = Path(settings.WORKSPACE_DIR).resolve()

    def _sync_search():
        matched = []
        for path_obj in workspace_root.rglob("*"):
            if not path_obj.is_file():
                continue
            # Filter pattern in filename
            name_match = pattern.lower() in path_obj.name.lower()
            content_match = False

            if search_content and not name_match:
                try:
                    with open(path_obj, "r", encoding="utf-8", errors="ignore") as f:
                        if pattern.lower() in f.read().lower():
                            content_match = True
                except Exception:
                    pass

            if name_match or content_match:
                matched.append({
                    "filename": path_obj.name,
                    "relative_path": str(path_obj.relative_to(workspace_root)),
                    "path": str(path_obj),
                    "size_bytes": path_obj.stat().st_size,
                    "matched_by": "filename" if name_match else "content",
                })
        return matched

    return await asyncio.to_thread(_sync_search)


async def organize_directory(
    directory_path: str = "",
    strategy: str = "extension",
    directory: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Categorizes and moves workspace files into subdirectories based on extension:
    `documents/`, `images/`, `data/`, `code/`, `audio/`, `archives/`, or `others/`.
    Avoids moving subdirectories or hidden dotfiles.
    """
    target_dir = directory if directory is not None else directory_path
    safe_dir = resolve_safe_workspace_path(target_dir)
    if not safe_dir.exists():
        raise FileNotFoundError(f"Directory not found: {directory_path}")

    def _sync_organize():
        moved = []
        for item in list(safe_dir.iterdir()):
            if not item.is_file():
                continue
            if item.name.startswith("."):
                continue

            category = EXTENSION_CATEGORY_MAP.get(item.suffix.lower(), "others")
            target_folder = safe_dir / category
            target_folder.mkdir(parents=True, exist_ok=True)

            target_path = target_folder / item.name
            try:
                shutil.move(str(item), str(target_path))
                moved.append({
                    "file": item.name,
                    "category": category,
                    "destination": str(target_path),
                })
            except Exception as move_err:
                logger.debug(f"[FileSystem] Skip locked file {item.name}: {move_err}")
        return moved

    moved_files = await asyncio.to_thread(_sync_organize)
    logger.info(f"[Filesystem] Organized {len(moved_files)} files in {safe_dir}.")
    return {
        "status": "success",
        "directory": str(safe_dir),
        "total_organized": len(moved_files),
        "moved_files": moved_files,
    }


async def get_directory_tree(directory_path: str = "") -> str:
    """
    Generates a readable ASCII tree structure representation of workspace contents.
    """
    safe_dir = resolve_safe_workspace_path(directory_path)
    if not safe_dir.exists():
        return f"{directory_path} (Empty or Not Found)"

    def _sync_tree():
        lines = [safe_dir.name + "/"]

        def _walk(current_dir: Path, prefix: str = ""):
            items = sorted(list(current_dir.iterdir()), key=lambda x: (not x.is_dir(), x.name.lower()))
            for idx, item in enumerate(items):
                is_last = idx == len(items) - 1
                connector = "└── " if is_last else "├── "
                sub_prefix = "    " if is_last else "│   "
                if item.is_dir():
                    lines.append(f"{prefix}{connector}{item.name}/")
                    _walk(item, prefix + sub_prefix)
                else:
                    lines.append(f"{prefix}{connector}{item.name} ({item.stat().st_size} bytes)")

        _walk(safe_dir)
        return "\n".join(lines)

    return await asyncio.to_thread(_sync_tree)
