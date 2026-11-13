"""
Integration & Unit Test Suite for Module 3: Advanced Browser Intelligence & Autonomous Web Research
Validates:
1. Login wall & password detector on mock HTML forms.
2. Website change monitoring & SHA-256 hash diff computation.
3. Academic paper metadata extraction via arXiv API parser.
4. Autonomous structured research & 2-sheet Excel report generation (.xlsx) for 10 AI/ML internships in India.
5. End-to-end cognitive brain planning for compound research queries.
"""

import os
import pytest
import openpyxl
from pathlib import Path

from app.tools.browser import BrowserEngine
from app.tools.research_engine import (
    compute_content_hash,
    monitor_website_changes,
    search_academic_papers,
    run_structured_research_to_excel,
    generate_styled_excel_report,
    CURATED_AIML_INTERNSHIPS_INDIA,
)
from app.core.brain import task_planner_node, step_executor_node
from app.core.security import resolve_safe_workspace_path


@pytest.mark.asyncio
async def test_detect_login_requirement():
    """Verifies detection of password fields and SSO login walls."""
    engine = BrowserEngine(headless=True)

    # HTML with password input
    login_html = """
    <html>
        <body>
            <form action="/login" method="post">
                <input type="text" name="username" placeholder="Username" />
                <input type="password" name="password" placeholder="Password" />
                <button type="submit">Sign In</button>
            </form>
        </body>
    </html>
    """
    res1 = await engine.detect_login_requirement(login_html)
    assert res1["is_login_wall"] is True
    assert res1["has_password_field"] is True
    assert res1["auth_type"] == "password"

    # Clean public page without login requirement
    public_html = """
    <html>
        <head><title>Public Research Blog</title></head>
        <body>
            <h1>Machine Learning in 2025</h1>
            <p>Welcome to our open access AI tutorials and benchmarks.</p>
        </body>
    </html>
    """
    res2 = await engine.detect_login_requirement(public_html)
    assert res2["is_login_wall"] is False
    assert res2["has_password_field"] is False


def test_website_content_hash_and_diff():
    """Verifies SHA-256 hash calculation and mutation detection."""
    text_v1 = "Internship openings: 5 positions available at Bengaluru AI Lab."
    text_v2 = "Internship openings: 5 positions available at Bengaluru AI Lab."
    text_v3 = "Internship openings: 8 positions available at Bengaluru AI Lab."

    hash1 = compute_content_hash(text_v1)
    hash2 = compute_content_hash(text_v2)
    hash3 = compute_content_hash(text_v3)

    assert hash1 == hash2, "Identical content must produce identical hash"
    assert hash1 != hash3, "Mutated content must produce a distinct hash"


@pytest.mark.asyncio
async def test_search_academic_papers():
    """Verifies academic research discovery returns structured metadata."""
    papers = await search_academic_papers(query="transformer architecture", max_results=5)
    assert isinstance(papers, list)
    assert len(papers) >= 1
    
    first = papers[0]
    assert "title" in first
    assert "authors" in first
    assert "year" in first
    assert "abstract" in first
    assert "pdf_url" in first
    assert isinstance(first["authors"], list)


@pytest.mark.asyncio
async def test_structured_research_excel_generation():
    """
    Verifies autonomous generation of presentation-grade 2-sheet Excel file (.xlsx)
    benchmarking 10 AI/ML internships in India.
    """
    test_filename = "Test_AIML_Internships_India.xlsx"
    result = await run_structured_research_to_excel(
        goal="Find 10 AI/ML internships in India, compare requirements and stipends",
        output_filename=test_filename,
    )

    assert result["status"] == "success"
    assert result["records_count"] == 10
    assert result["file_name"] == test_filename

    excel_path = Path(result["file_path"])
    assert excel_path.exists(), "Generated Excel file must exist on disk"
    assert excel_path.stat().st_size > 0, "Excel file must not be empty"

    # Inspect openpyxl workbook structure
    wb = openpyxl.load_workbook(str(excel_path))
    assert "Comparison_Data" in wb.sheetnames
    assert "Executive_Summary" in wb.sheetnames

    # Verify Sheet 1 (Comparison_Data)
    ws_data = wb["Comparison_Data"]
    headers = [cell.value for cell in ws_data[1]]
    assert "Company" in headers
    assert "Role" in headers
    assert "Stipend" in headers
    assert "Eligibility" in headers
    assert "Application_Link" in headers

    # Verify 10 rows of data + 1 header row = 11 rows
    row_count = ws_data.max_row
    assert row_count >= 11

    # Verify Sheet 2 (Executive_Summary)
    ws_sum = wb["Executive_Summary"]
    assert "Executive Research Report:" in str(ws_sum["A1"].value)
    assert ws_sum.freeze_panes is None or ws_data.freeze_panes == "A2"


@pytest.mark.asyncio
async def test_brain_planner_compound_research():
    """Verifies task_planner_node decomposes compound research requests to run_structured_research_to_excel."""
    state = {
        "user_intent": {
            "category": "RESEARCH",
            "resolved_query": "Find 10 AI/ML internships in India, compare requirements, salaries and eligibility, and create an Excel sheet",
        },
        "plan_steps": [],
        "current_step_index": 0,
        "replan_count": 0,
    }

    res = await task_planner_node(state)
    steps = res["plan_steps"]
    assert len(steps) >= 1
    assert steps[0]["tool_name"] == "run_structured_research_to_excel"
    assert "output_filename" in steps[0]["tool_args"]

    # Execute the planned step via step_executor_node
    exec_state = {
        "plan_steps": steps,
        "current_step_index": 0,
        "execution_logs": [],
        "artifacts": [],
    }
    exec_res = await step_executor_node(exec_state)
    assert exec_res["plan_steps"][0]["status"] == "completed"
    assert len(exec_res.get("artifacts", [])) >= 1
    assert exec_res["artifacts"][0].endswith(".xlsx")

