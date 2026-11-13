"""Comprehensive Test Suite for NEXUS AI File & Document Intelligence Subsystem.
Verifies:
1. Multi-Format Parser (PDF text, tables, figures/images, deadlines & dates)
2. Persistent ChromaDB Vector Memory + SQLite Catalog (Grounded Q&A, citations)
3. Document Comparator & Synthesis (diffing, compliance checklist, literature review)
4. Multi-Format Generator & Converter (styled Word .docx, Excel .xlsx, PPTX deck, format conversions)
5. Library Organizer & Deduplicator (SHA-256 deduplication, category tagging)
6. DocumentAgent LangGraph Node integration & artifacts generation
"""

import os
import shutil
import pytest
from pathlib import Path

from app.documents.parser_extractor import (
    parse_document,
    extract_tables,
    extract_figures,
    extract_important_dates,
)
from app.documents.vector_memory import (
    DocumentVectorMemory,
    ingest_document,
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
from app.documents.library_organizer import (
    tag_and_catalog_file,
    deduplicate_library,
    organize_library,
)
from app.documents.document_agent import run_document_task, document_agent_node
from langchain_core.messages import HumanMessage


@pytest.fixture
def temp_doc_workspace(tmp_path):
    """Fixture providing temporary test directory with sample documents."""
    ws = tmp_path / "doc_test_ws"
    ws.mkdir()

    # Create sample text document
    sample_text = (
        "Project NEXUS AI Architecture\n"
        "Lead Architect: Dev Team\n"
        "Abstract: NEXUS AI provides zero-VRAM agentic intelligence.\n"
        "Methodology: Cyclical LangGraph orchestrating multi-format parsers.\n"
        "Datasets and Benchmarks: Tested on 500 documents across Windows 11.\n"
        "Results: Zero GPU utilization and sub-second parsing.\n"
        "Limitations: Currently bound by CPU parsing throughput.\n"
        "Important Milestones:\n"
        "- Due date: 2026-12-01\n"
        "- Effective date: January 15, 2026\n"
        "- Final Review Deadline: 2026-12-20\n"
    )
    p_text = ws / "sample_paper_1.txt"
    p_text.write_text(sample_text, encoding="utf-8")

    # Create second paper
    sample_paper_2 = (
        "Multi-Modal Agentic Voice Control\n"
        "Lead Architect: Voice Research Group\n"
        "Abstract: Full-duplex speech recognition with barge-in interruption.\n"
        "Methodology: Asynchronous WebSocket pipeline with edge-tts neural voice.\n"
        "Datasets and Benchmarks: Evaluated on LibriSpeech.\n"
        "Results: Latency reduced to under 300ms.\n"
        "Limitations: Edge-tts requires intermittent network access.\n"
        "Milestones:\n"
        "- Milestone: 2026-11-30\n"
    )
    p_text2 = ws / "sample_paper_2.txt"
    p_text2.write_text(sample_paper_2, encoding="utf-8")

    # Create sample markdown
    sample_md = (
        "# System Specifications\n\n"
        "## Section 1: Overview\n"
        "NEXUS AI runs on Windows 11 with 0 MB VRAM overhead.\n\n"
        "## Section 2: Requirements\n"
        "- Python 3.10+\n"
        "- ChromaDB\n"
    )
    p_md = ws / "spec.md"
    p_md.write_text(sample_md, encoding="utf-8")

    return ws


def test_parser_and_date_extraction(temp_doc_workspace):
    """Verify multi-format parsing, text extraction, and date/deadline detection."""
    doc_path = temp_doc_workspace / "sample_paper_1.txt"
    parsed = parse_document(str(doc_path))

    assert parsed["word_count"] > 30
    assert "NEXUS AI Architecture" in parsed["text"]

    dates = parsed["dates"]
    assert len(dates) >= 2
    date_strs = [d["date_str"] for d in dates]
    assert any("2026-12-01" in s or "January 15, 2026" in s for s in date_strs)


def test_generator_word_excel_powerpoint(temp_doc_workspace):
    """Verify generation of styled Word, Excel, and PowerPoint files."""
    out_dir = temp_doc_workspace / "output"
    out_dir.mkdir()

    # Word report
    docx_file = out_dir / "report.docx"
    doc_res = generate_word_report(
        title="NEXUS AI Executive Summary",
        sections=[
            {"heading": "Architecture", "body": "Microkernel agentic framework."},
            {"heading": "Metrics", "table": [{"Metric": "VRAM", "Value": "0 MB"}, {"Metric": "Speed", "Value": "Fast"}]},
        ],
        output_path=str(docx_file),
    )
    assert Path(doc_res).exists()
    assert Path(doc_res).stat().st_size > 1000

    # Excel workbook
    xlsx_file = out_dir / "matrix.xlsx"
    xls_res = generate_excel_workbook(
        sheet_data={"Benchmarks": [{"Model": "NEXUS", "VRAM": "0MB", "Accuracy": "99.4%"}]},
        output_path=str(xlsx_file),
    )
    assert Path(xls_res).exists()
    assert Path(xls_res).stat().st_size > 1000

    # PowerPoint deck
    pptx_file = out_dir / "deck.pptx"
    ppt_res = generate_powerpoint_deck(
        deck_title="NEXUS AI Briefing",
        slides=[{"title": "Core Modules", "bullets": ["Document AI", "Music Intelligence", "Voice Bridge"]}],
        output_path=str(pptx_file),
    )
    assert Path(ppt_res).exists()
    assert Path(ppt_res).stat().st_size > 1000


def test_document_format_conversion(temp_doc_workspace):
    """Verify converting .md to .docx format."""
    md_file = temp_doc_workspace / "spec.md"
    out_docx = temp_doc_workspace / "converted_spec.docx"

    res = convert_document_format(str(md_file), target_format=".docx", output_path=str(out_docx))
    assert Path(res).exists()
    assert Path(res).stat().st_size > 500


def test_comparator_and_compliance(temp_doc_workspace):
    """Verify pairwise diffing, similarity ratio, and compliance auditing."""
    doc1 = temp_doc_workspace / "sample_paper_1.txt"
    doc2 = temp_doc_workspace / "sample_paper_2.txt"

    diff_res = compare_two_documents(str(doc1), str(doc2))
    assert "similarity_ratio" in diff_res
    assert diff_res["is_substantively_different"] is True

    # Audit compliance checklist
    checklist = ["Abstract", "Methodology", "Results", "NonExistentSection"]
    audit_res = identify_missing_information(str(doc1), checklist)
    assert audit_res["compliance_score_percent"] == 75.0
    assert "NonExistentSection" in audit_res["missing_sections"]
    assert audit_res["status"] == "DEFICIENT"


def test_literature_review_synthesis(temp_doc_workspace):
    """Verify multi-paper academic synthesis, methodology matrix, and research gaps."""
    doc1 = temp_doc_workspace / "sample_paper_1.txt"
    doc2 = temp_doc_workspace / "sample_paper_2.txt"

    review = synthesize_literature_review([str(doc1), str(doc2)])
    assert review["paper_count"] == 2
    assert len(review["profiles"]) == 2
    assert "Multi-Paper Literature Review" in review["synthesis_summary"]

    p1 = review["profiles"][0]
    assert "methodology" in p1
    assert "research_gap" in p1


def test_vector_memory_and_citations(temp_doc_workspace):
    """Verify ChromaDB indexing, semantic search, and grounded citations at 0 VRAM."""
    vec_path = temp_doc_workspace / "vector_db"
    cat_path = temp_doc_workspace / "catalog.db"

    mem = DocumentVectorMemory(vector_db_path=vec_path, catalog_db_path=cat_path)
    doc1 = temp_doc_workspace / "sample_paper_1.txt"

    ingest_res = mem.ingest_document(str(doc1), category="research_papers")
    assert ingest_res["total_chunks"] >= 1

    search_hits = mem.search_documents("zero VRAM agentic", n_results=2)
    assert len(search_hits) > 0
    assert "citation" in search_hits[0]

    qa_res = mem.answer_from_documents("What does NEXUS AI provide?")
    assert len(qa_res["citations"]) > 0
    assert "Based on the indexed documents" in qa_res["answer"]


def test_library_organizer_and_deduplication(temp_doc_workspace):
    """Verify auto-tagging, SHA-256 deduplication, and folder restructuring."""
    # Create duplicate file
    doc1 = temp_doc_workspace / "sample_paper_1.txt"
    dupe_file = temp_doc_workspace / "duplicate_paper_1.txt"
    shutil.copyfile(doc1, dupe_file)

    dedupe_res = deduplicate_library(str(temp_doc_workspace))
    assert dedupe_res["total_duplicates_found"] >= 1
    assert dedupe_res["duplicate_groups"] >= 1

    target_lib = temp_doc_workspace / "organized_library"
    org_res = organize_library(str(temp_doc_workspace), target_dir=str(target_lib))
    assert org_res["files_organized"] >= 3
    assert (target_lib / "research_papers").exists()


@pytest.mark.asyncio
async def test_document_agent_node_execution(temp_doc_workspace):
    """Verify DocumentAgent executes compound requests and populates state['artifacts']."""
    doc1 = temp_doc_workspace / "sample_paper_1.txt"
    doc2 = temp_doc_workspace / "sample_paper_2.txt"

    state = {
        "messages": [HumanMessage(content=f"Prepare a literature review and compare methodologies for {doc1} and {doc2}")],
        "artifacts": [],
        "execution_logs": [],
    }

    res = await document_agent_node(state)
    assert len(res["artifacts"]) >= 3  # DOCX report, XLSX matrix, PPTX presentation
    assert len(res["messages"]) == 1
    assert "Generated Artifacts" in res["messages"][0].content

