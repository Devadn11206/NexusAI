"""NEXUS AI - File & Document Intelligence Subsystem.
Zero-GPU VRAM footprint, CPU-native multi-format parsing, persistent ChromaDB + SQLite catalog,
comparative analysis, literature reviews, and multi-format document generation.
"""

from app.documents.parser_extractor import (
    parse_document,
    extract_tables,
    extract_figures,
    extract_important_dates,
)
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
from app.documents.library_organizer import (
    organize_library,
    deduplicate_library,
    tag_and_catalog_file,
)
from app.documents.document_agent import document_agent_node, run_document_task

__all__ = [
    "parse_document",
    "extract_tables",
    "extract_figures",
    "extract_important_dates",
    "get_vector_memory",
    "ingest_document",
    "batch_ingest_directory",
    "search_documents",
    "answer_from_documents",
    "compare_two_documents",
    "identify_missing_information",
    "synthesize_literature_review",
    "generate_word_report",
    "generate_excel_workbook",
    "generate_powerpoint_deck",
    "create_meeting_notes",
    "convert_document_format",
    "organize_library",
    "deduplicate_library",
    "tag_and_catalog_file",
    "document_agent_node",
    "run_document_task",
]

