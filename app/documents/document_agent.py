"""NEXUS AI - Document Intelligence Agent & LangGraph Supervisor Node.
Executes autonomous multi-step document pipelines:
- Research paper literature reviews, methodology matrices, and gap analysis
- Document parsing, semantic QA, and grounded citations
- Word report (.docx), Excel sheet (.xlsx), and PowerPoint (.pptx) creation
- Automatically updates state["artifacts"] for immediate delivery via Telegram.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.documents.parser_extractor import parse_document, extract_tables, extract_important_dates
from app.documents.vector_memory import (
    get_vector_memory,
    ingest_document,
    batch_ingest_directory,
    search_documents,
    answer_from_documents,
)
from app.documents.comparator_analyzer import (
    compare_two_documents,
    identify_missing_information,
    synthesize_literature_review,
)
from app.documents.generator_converter import (
    generate_word_report,
    generate_excel_workbook,
    generate_powerpoint_deck,
    create_meeting_notes,
    convert_document_format,
)
from app.documents.library_organizer import organize_library, deduplicate_library


async def run_document_task(task_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Execute dedicated document intelligence operations and generate artifact deliverables."""
    artifacts = []
    result_text = ""

    if task_type in ["literature_review", "synthesize_papers", "research_gaps"]:
        file_paths = params.get("file_paths", [])
        if not file_paths and "directory" in params:
            d = Path(params["directory"])
            file_paths = [str(f) for f in d.glob("*") if f.suffix.lower() in [".pdf", ".docx", ".txt", ".md"]]

        review = synthesize_literature_review(file_paths)
        result_text = review.get("synthesis_summary", "")

        # Export to Word Document
        word_sections = [
            {"heading": "Executive Summary", "body": "Comprehensive multi-paper analysis conducted across literature."},
            {"heading": "Paper Profiles & Identified Research Gaps", "body": "\n".join(review.get("cross_cutting_gaps", []))},
        ]
        doc_path = generate_word_report(
            title=params.get("title", "Literature Review & Research Gaps"),
            sections=word_sections,
        )
        artifacts.append(doc_path)

        # Export to Excel Matrix
        matrix_rows = []
        for p in review.get("profiles", []):
            matrix_rows.append({
                "Paper Title": p.get("title", ""),
                "Authors": p.get("authors", ""),
                "Core Methodology": p.get("methodology", ""),
                "Datasets/Baselines": p.get("datasets_baselines", ""),
                "Reported Results": p.get("results", ""),
                "Identified Research Gap": p.get("research_gap", ""),
            })
        excel_path = generate_excel_workbook(
            sheet_data={"Methodology Comparison": matrix_rows},
            workbook_title=params.get("title", "Literature_Review_Matrix"),
        )
        artifacts.append(excel_path)

        # Export to PowerPoint Deck
        pptx_slides = []
        for p in review.get("profiles", [])[:5]:
            pptx_slides.append({
                "title": p.get("title", "Paper Overview")[:40],
                "bullets": [
                    f"Methodology: {p.get('methodology', '')[:100]}",
                    f"Results: {p.get('results', '')[:100]}",
                    f"Key Gap: {p.get('research_gap', '')[:100]}",
                ]
            })
        ppt_path = generate_powerpoint_deck(
            deck_title=params.get("title", "Literature Review Executive Deck"),
            slides=pptx_slides,
        )
        artifacts.append(ppt_path)

        return {
            "status": "success",
            "summary": result_text,
            "artifacts": artifacts,
            "profiles": review.get("profiles", []),
        }

    elif task_type in ["compare", "diff"]:
        file1 = params.get("file1")
        file2 = params.get("file2")
        comparison = compare_two_documents(file1, file2)
        summary = (
            f"Comparison between {Path(file1).name} and {Path(file2).name}:\n"
            f"- Similarity Score: {comparison['similarity_ratio'] * 100:.1f}%\n"
            f"- Substantively Different: {comparison['is_substantively_different']}\n"
            f"- Words: {comparison['metrics']['doc1_words']} vs {comparison['metrics']['doc2_words']}"
        )
        return {
            "status": "success",
            "summary": summary,
            "details": comparison,
            "artifacts": [],
        }

    elif task_type in ["ask", "qa", "search"]:
        query = params.get("query", "")
        qa_res = answer_from_documents(query=query)
        return {
            "status": "success",
            "summary": qa_res["answer"],
            "citations": qa_res["citations"],
            "artifacts": [],
        }

    elif task_type in ["create_report", "generate_docx"]:
        title = params.get("title", "Report")
        sections = params.get("sections", [{"heading": "Overview", "body": params.get("content", "")}])
        out_doc = generate_word_report(title=title, sections=sections)
        artifacts.append(out_doc)
        return {
            "status": "success",
            "summary": f"Generated Word Report: {out_doc}",
            "artifacts": artifacts,
        }

    elif task_type in ["create_workbook", "generate_xlsx"]:
        title = params.get("title", "Workbook")
        sheet_data = params.get("sheet_data", {"Sheet1": params.get("rows", [])})
        out_xls = generate_excel_workbook(sheet_data=sheet_data, workbook_title=title)
        artifacts.append(out_xls)
        return {
            "status": "success",
            "summary": f"Generated Excel Workbook: {out_xls}",
            "artifacts": artifacts,
        }

    elif task_type in ["create_deck", "generate_pptx"]:
        title = params.get("title", "Presentation")
        slides = params.get("slides", [{"title": "Overview", "bullets": ["Generated by NEXUS AI"]}])
        out_ppt = generate_powerpoint_deck(deck_title=title, slides=slides)
        artifacts.append(out_ppt)
        return {
            "status": "success",
            "summary": f"Generated PowerPoint Deck: {out_ppt}",
            "artifacts": artifacts,
        }

    elif task_type in ["convert", "format_converter"]:
        src = params.get("source_file")
        target_fmt = params.get("target_format", ".docx")
        out_file = convert_document_format(src, target_fmt)
        artifacts.append(out_file)
        return {
            "status": "success",
            "summary": f"Converted {Path(src).name} to {target_fmt}: {out_file}",
            "artifacts": artifacts,
        }

    elif task_type in ["organize", "organize_library"]:
        src_dir = params.get("source_dir", "./workspace/downloads")
        res = organize_library(src_dir)
        return {
            "status": "success",
            "summary": f"Organized {res['files_organized']} files into structured categories.",
            "details": res,
            "artifacts": [],
        }

    else:
        # Default fallback to document parse
        src = params.get("file_path")
        parsed = parse_document(src)
        return {
            "status": "success",
            "summary": f"Parsed {parsed['metadata']['file_name']} ({parsed['word_count']} words, {len(parsed['tables'])} tables).",
            "parsed": parsed,
            "artifacts": [],
        }


async def document_agent_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph node routing for document and file intelligence."""
    from langchain_core.messages import AIMessage

    messages = state.get("messages", [])
    user_msg = messages[-1].content if messages else ""
    user_msg_lower = user_msg.lower()

    # Determine intent
    params: Dict[str, Any] = {}
    if any(k in user_msg_lower for k in ["literature review", "research gap", "compare methodologies", "papers"]):
        task_type = "literature_review"
        params = {"title": "Literature Review & Research Gaps"}
    elif any(k in user_msg_lower for k in ["compare", "diff", "difference between"]):
        task_type = "compare"
    elif any(k in user_msg_lower for k in ["presentation", "deck", "slide", "powerpoint", "pptx"]):
        task_type = "create_deck"
        params = {"title": "NEXUS AI Presentation"}
    elif any(k in user_msg_lower for k in ["excel", "spreadsheet", "workbook", "xlsx"]):
        task_type = "create_workbook"
        params = {"title": "NEXUS AI Data Sheet"}
    elif any(k in user_msg_lower for k in ["word", "report", "docx"]):
        task_type = "create_report"
        params = {"title": "NEXUS AI Executive Report", "content": user_msg}
    elif any(k in user_msg_lower for k in ["convert", "to docx", "to pdf", "to xlsx"]):
        task_type = "convert"
    else:
        task_type = "ask"
        params = {"query": user_msg}

    task_result = await run_document_task(task_type, params)

    existing_artifacts = list(state.get("artifacts") or [])
    new_artifacts = task_result.get("artifacts", [])
    updated_artifacts = existing_artifacts + [a for a in new_artifacts if a not in existing_artifacts]

    ai_reply = task_result.get("summary", "Document intelligence processing complete.")
    if new_artifacts:
        ai_reply += "\n\nGenerated Artifacts:\n" + "\n".join(f"- `{Path(a).name}`" for a in new_artifacts)

    return {
        "messages": [AIMessage(content=ai_reply)],
        "artifacts": updated_artifacts,
        "execution_logs": state.get("execution_logs", []) + [{
            "step_id": "document_agent",
            "output": task_result.get("summary", ""),
            "artifacts": new_artifacts,
        }],
    }

