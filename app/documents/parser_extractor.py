"""NEXUS AI - Multi-Format Parser & Deep Content Extractor.
High-speed, 0-MB VRAM document parsing using PyMuPDF / pymupdf4llm, python-docx,
openpyxl, python-pptx, and structured date/deadline pattern extraction.
"""

from __future__ import annotations

import io
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import fitz  # PyMuPDF
try:
    import pymupdf4llm
except ImportError:
    pymupdf4llm = None

import docx
import openpyxl
import pptx


FIGURES_OUTPUT_DIR = Path("./workspace/artifacts/extracted_figures")


def extract_important_dates(text: str) -> List[Dict[str, str]]:
    """Extract dates, deadlines, milestones, and effective dates from document text."""
    date_patterns = [
        # YYYY-MM-DD or DD/MM/YYYY or MM/DD/YYYY
        r"\b(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b",
        # Month Day, Year (e.g., January 15, 2026 or 15 Jan 2026)
        r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}\b",
        r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?),?\s+\d{4}\b",
        # Relative deadlines (e.g. Due by: ..., Deadline: ...)
        r"(?:deadline|due\s+date|effective\s+date|milestone|target\s+date)[\s:]+([A-Za-z0-9\s,\-\./]+?)(?=[.;\n]|$)",
    ]

    found: List[Dict[str, str]] = []
    seen = set()

    for pat in date_patterns:
        for match in re.finditer(pat, text, re.IGNORECASE):
            raw = match.group(0).strip()
            # Capture contextual snippet around date
            start = max(0, match.start() - 35)
            end = min(len(text), match.end() + 35)
            snippet = " ".join(text[start:end].split())
            if raw.lower() not in seen:
                seen.add(raw.lower())
                found.append({
                    "date_str": raw,
                    "context": snippet,
                })
    return found


def extract_figures(file_path: str, output_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    """Extract figures/images from PDF documents into workspace artifacts."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    target_dir = Path(output_dir) if output_dir else FIGURES_OUTPUT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    extracted_figures: List[Dict[str, Any]] = []

    if path.suffix.lower() == ".pdf":
        doc = fitz.open(str(path))
        base_name = path.stem
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            image_list = page.get_images(full=True)
            for img_idx, img in enumerate(image_list):
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                image_filename = f"{base_name}_p{page_idx + 1}_img{img_idx + 1}.{image_ext}"
                out_path = target_dir / image_filename
                with open(out_path, "wb") as f:
                    f.write(image_bytes)

                extracted_figures.append({
                    "page": page_idx + 1,
                    "image_index": img_idx + 1,
                    "format": image_ext,
                    "width": base_image.get("width"),
                    "height": base_image.get("height"),
                    "file_path": str(out_path.resolve()),
                })
        doc.close()

    return extracted_figures


def extract_tables(file_path: str) -> List[Dict[str, Any]]:
    """Extract structured tables from PDF, Excel, Word, or Markdown files."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = path.suffix.lower()
    tables: List[Dict[str, Any]] = []

    if ext == ".pdf":
        doc = fitz.open(str(path))
        for page_idx, page in enumerate(doc):
            try:
                tabs = page.find_tables()
                if tabs and tabs.tables:
                    for t_idx, t in enumerate(tabs.tables):
                        extracted_rows = t.extract()
                        if extracted_rows:
                            tables.append({
                                "source": path.name,
                                "page": page_idx + 1,
                                "table_id": t_idx + 1,
                                "headers": extracted_rows[0] if extracted_rows else [],
                                "rows": extracted_rows[1:] if len(extracted_rows) > 1 else [],
                                "row_count": len(extracted_rows),
                            })
            except Exception:
                pass
        doc.close()

    elif ext in [".xlsx", ".xls"]:
        wb = openpyxl.load_workbook(str(path), data_only=True)
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            rows = list(ws.iter_rows(values_only=True))
            if rows:
                headers = [str(c or "") for c in rows[0]]
                data_rows = [[str(c or "") for c in r] for r in rows[1:]]
                tables.append({
                    "source": path.name,
                    "sheet_name": sheet_name,
                    "headers": headers,
                    "rows": data_rows,
                    "row_count": len(rows),
                })
        wb.close()

    elif ext == ".docx":
        doc = docx.Document(str(path))
        for t_idx, table in enumerate(doc.tables):
            grid = []
            for row in table.rows:
                grid.append([cell.text.strip() for cell in row.cells])
            if grid:
                tables.append({
                    "source": path.name,
                    "table_id": t_idx + 1,
                    "headers": grid[0] if grid else [],
                    "rows": grid[1:] if len(grid) > 1 else [],
                    "row_count": len(grid),
                })

    return tables


def parse_document(file_path: str, extract_imgs: bool = False) -> Dict[str, Any]:
    """Parse a document into structured text, metadata, tables, dates, and optional figures.
    
    Supports: .pdf, .docx, .xlsx, .pptx, .md, .txt, .csv.
    Operates at 0 MB GPU VRAM.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = path.suffix.lower()
    full_text = ""
    pages_text: List[Dict[str, Any]] = []
    metadata: Dict[str, Any] = {
        "file_name": path.name,
        "file_path": str(path.resolve()),
        "file_size": path.stat().st_size,
        "extension": ext,
    }

    if ext == ".pdf":
        doc = fitz.open(str(path))
        metadata["page_count"] = len(doc)
        metadata["title"] = doc.metadata.get("title") or path.stem
        metadata["author"] = doc.metadata.get("author") or "Unknown"

        # Try pymupdf4llm for markdown conversion if available
        markdown_content = ""
        if pymupdf4llm is not None:
            try:
                markdown_content = pymupdf4llm.to_markdown(str(path))
            except Exception:
                markdown_content = ""

        for page_idx in range(len(doc)):
            p = doc[page_idx]
            p_text = p.get_text()
            pages_text.append({
                "page_number": page_idx + 1,
                "text": p_text,
            })
            full_text += f"\n--- Page {page_idx + 1} ---\n" + p_text

        doc.close()
        if markdown_content:
            metadata["markdown"] = markdown_content

    elif ext == ".docx":
        doc = docx.Document(str(path))
        paras = [p.text for p in doc.paragraphs if p.text.strip()]
        full_text = "\n\n".join(paras)
        pages_text.append({"page_number": 1, "text": full_text})
        metadata["paragraph_count"] = len(paras)

    elif ext in [".xlsx", ".xls"]:
        wb = openpyxl.load_workbook(str(path), data_only=True)
        sheets_data = []
        for name in wb.sheetnames:
            ws = wb[name]
            lines = []
            for row in ws.iter_rows(values_only=True):
                if any(row):
                    lines.append("\t".join(str(c or "") for c in row))
            sheet_text = "\n".join(lines)
            sheets_data.append(f"### Sheet: {name}\n{sheet_text}")
        full_text = "\n\n".join(sheets_data)
        pages_text.append({"page_number": 1, "text": full_text})
        metadata["sheet_names"] = wb.sheetnames
        wb.close()

    elif ext == ".pptx":
        prs = pptx.Presentation(str(path))
        slides_text = []
        for s_idx, slide in enumerate(prs.slides):
            slide_lines = []
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        if para.text.strip():
                            slide_lines.append(para.text.strip())
            s_content = "\n".join(slide_lines)
            slides_text.append(f"--- Slide {s_idx + 1} ---\n{s_content}")
            pages_text.append({"page_number": s_idx + 1, "text": s_content})
        full_text = "\n\n".join(slides_text)
        metadata["slide_count"] = len(prs.slides)

    elif ext in [".md", ".txt", ".csv", ".json", ".log"]:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            full_text = f.read()
        pages_text.append({"page_number": 1, "text": full_text})

    else:
        # Fallback reading
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                full_text = f.read()
            pages_text.append({"page_number": 1, "text": full_text})
        except Exception as e:
            full_text = f"Unsupported or binary file format: {ext}"

    tables = extract_tables(str(path))
    dates = extract_important_dates(full_text)
    figures = extract_figures(str(path)) if (extract_imgs and ext == ".pdf") else []

    return {
        "text": full_text,
        "pages": pages_text,
        "metadata": metadata,
        "tables": tables,
        "dates": dates,
        "figures": figures,
        "word_count": len(full_text.split()),
    }

