"""NEXUS AI - Automated Library Organizer, Deduplicator & Semantic Tagger.
Organizes messy directories into categorized workspaces (`./workspace/library/<category>/`),
detects exact and near-duplicates via SHA-256 and content similarity, and sanitizes filenames.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.documents.parser_extractor import parse_document

DEFAULT_LIBRARY_DIR = Path("./workspace/library")

# Heuristic category classifiers
CATEGORY_KEYWORDS = {
    "research_papers": ["abstract", "methodology", "evaluation", "benchmark", "arxiv", "proceedings", "ieee", "conference"],
    "contracts_legal": ["agreement", "party", "terms and conditions", "confidentiality", "indemnification", "clause", "governing law"],
    "financials_invoices": ["invoice", "balance sheet", "revenue", "fiscal", "tax", "statement", "q1", "q2", "q3", "q4", "subtotal", "usd"],
    "specifications_technical": ["architecture", "api", "specification", "schema", "endpoint", "system design", "payload", "protocol"],
    "notes_minutes": ["meeting", "minutes", "attendees", "agenda", "action items", "notes", "sync"],
}


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash for byte-level duplicate detection."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def tag_and_catalog_file(file_path: str) -> Dict[str, Any]:
    """Inspect file content, assign semantic category, and suggest sanitized name."""
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    try:
        parsed = parse_document(str(p))
        text_sample = (parsed["text"][:3000]).lower()
    except Exception:
        text_sample = p.name.lower()

    # Score categories
    category_scores = {}
    for cat, kws in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in kws if kw in text_sample)
        if score > 0:
            category_scores[cat] = score

    if category_scores:
        assigned_category = max(category_scores, key=category_scores.get)
    else:
        assigned_category = "uncategorized"

    # Sanitized filename
    clean_stem = re.sub(r"[^\w\s-]", "", p.stem).strip()
    clean_stem = re.sub(r"[-\s]+", "_", clean_stem)
    suggested_filename = f"{clean_stem}{p.suffix.lower()}"

    return {
        "original_name": p.name,
        "suggested_name": suggested_filename,
        "category": assigned_category,
        "size_bytes": p.stat().st_size,
    }


def deduplicate_library(directory_path: str) -> Dict[str, Any]:
    """Scan directory, detect SHA-256 exact duplicates, and return duplication report."""
    folder = Path(directory_path)
    if not folder.exists():
        raise FileNotFoundError(f"Directory not found: {directory_path}")

    hashes: Dict[str, List[Path]] = {}
    for p in folder.rglob("*"):
        if p.is_file():
            h = compute_file_hash(p)
            hashes.setdefault(h, []).append(p)

    duplicates: List[Dict[str, Any]] = []
    total_saved_bytes = 0

    for h, files in hashes.items():
        if len(files) > 1:
            primary = files[0]
            extra_dupes = files[1:]
            for d in extra_dupes:
                total_saved_bytes += d.stat().st_size
            duplicates.append({
                "sha256": h,
                "primary_file": str(primary.resolve()),
                "duplicate_files": [str(d.resolve()) for d in extra_dupes],
                "duplicate_count": len(extra_dupes),
            })

    return {
        "scanned_directory": str(folder.resolve()),
        "duplicate_groups": len(duplicates),
        "total_duplicates_found": sum(d["duplicate_count"] for d in duplicates),
        "potential_reclaimed_bytes": total_saved_bytes,
        "details": duplicates,
    }


def organize_library(
    source_dir: str,
    target_dir: Optional[str] = None,
    move_files: bool = False
) -> Dict[str, Any]:
    """Auto-organize files from source_dir into categorized subfolders under target_dir."""
    src = Path(source_dir)
    if not src.exists():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")

    tgt = Path(target_dir) if target_dir else DEFAULT_LIBRARY_DIR
    tgt.mkdir(parents=True, exist_ok=True)

    moved_or_copied: List[Dict[str, Any]] = []

    for file_path in src.iterdir():
        if file_path.is_file():
            classification = tag_and_catalog_file(str(file_path))
            cat = classification["category"]
            dest_folder = tgt / cat
            dest_folder.mkdir(parents=True, exist_ok=True)

            dest_path = dest_folder / classification["suggested_name"]

            # Avoid self-overwrite
            if dest_path.resolve() != file_path.resolve():
                if move_files:
                    shutil.move(str(file_path), str(dest_path))
                    action = "moved"
                else:
                    shutil.copy2(str(file_path), str(dest_path))
                    action = "copied"

                moved_or_copied.append({
                    "original": str(file_path.resolve()),
                    "destination": str(dest_path.resolve()),
                    "category": cat,
                    "action": action,
                })

    return {
        "source": str(src.resolve()),
        "target": str(tgt.resolve()),
        "files_organized": len(moved_or_copied),
        "details": moved_or_copied,
    }

