"""NEXUS AI - Autonomous Developer & Competitive Programming Agent.
Orchestrates bounded cyclical workflows:
1. Full-Stack Application Engineering (plan -> generate -> run_and_monitor -> self_heal -> docs)
2. Competitive Programming Solving (parse -> solve -> sandbox test -> inject & submit -> repair loop)
Registered as a first-class node in LangGraph Supervisor.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.developer.project_architect import plan_project_architecture, scaffold_project
from app.developer.code_generator import generate_full_stack_project
from app.developer.runtime_monitor import RuntimeMonitor
from app.developer.self_healer import SelfHealer
from app.developer.cp_solver import CompetitiveProgrammingSolver


async def run_developer_task(task_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Execute end-to-end autonomous developer or competitive programming tasks."""
    if task_type in ["build_app", "full_stack_engineering", "scaffold_project"]:
        prompt = params.get("prompt") or params.get("requirements") or "Student attendance management application"
        arch = plan_project_architecture(prompt)
        proj_dir = scaffold_project(arch)
        generated_files = generate_full_stack_project(arch)

        # Monitor and verify with pytest
        monitor = RuntimeMonitor()
        pytest_res = await monitor.run_pytest_in_project(proj_dir)

        # Self-healing loop (up to max_fix_cycles = 5)
        healer = SelfHealer(proj_dir)
        cycles = 0
        max_fix_cycles = 5

        while pytest_res["status"] != "passed" and cycles < max_fix_cycles:
            cycles += 1
            for diag in pytest_res["diagnostics"]:
                healer.heal_traceback(diag)
            pytest_res = await monitor.run_pytest_in_project(proj_dir)

        return {
            "status": "success" if pytest_res["status"] == "passed" else "partial",
            "project_name": arch["slug"],
            "project_dir": proj_dir,
            "generated_files_count": len(generated_files),
            "pytest_status": pytest_res["status"],
            "healing_cycles_applied": cycles,
            "summary": f"Full-stack project '{arch['slug']}' generated autonomously under {proj_dir} with {len(generated_files)} files. Tests: {pytest_res['status']}.",
        }

    elif task_type in ["solve_cp", "leetcode", "codechef", "competitive_programming"]:
        problem = params.get("problem") or params.get("description") or "Two Sum Problem"
        solver = CompetitiveProgrammingSolver()
        res = await solver.solve_with_repair_loop(problem_description=problem)
        return {
            "status": "success",
            "title": res["title"],
            "verdict": res["final_verdict"],
            "total_attempts": res["total_attempts"],
            "solution_code": res["solution_code"],
            "summary": f"Competitive programming solver resolved '{res['title']}' with verdict: {res['final_verdict']} (Attempts: {res['total_attempts']}).",
        }

    else:
        return {
            "status": "unknown_task",
            "summary": f"Unrecognized developer task type: {task_type}",
        }


async def developer_agent_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph node interface for DeveloperAgent."""
    from langchain_core.messages import AIMessage

    messages = state.get("messages", [])
    user_msg = messages[-1].content if messages else ""
    user_msg_lower = user_msg.lower()

    if any(k in user_msg_lower for k in ["leetcode", "codechef", "two sum", "competitive programming", "algorithm"]):
        task_type = "solve_cp"
        params = {"problem": user_msg}
    else:
        task_type = "build_app"
        params = {"prompt": user_msg}

    result = await run_developer_task(task_type, params)

    existing_artifacts = list(state.get("artifacts") or [])
    if result.get("project_dir") and result["project_dir"] not in existing_artifacts:
        existing_artifacts.append(result["project_dir"])

    reply_content = result.get("summary", "Developer agent task execution completed.")

    return {
        "messages": [AIMessage(content=reply_content)],
        "artifacts": existing_artifacts,
        "execution_logs": state.get("execution_logs", []) + [{
            "step_id": "developer_agent",
            "output": reply_content,
        }],
    }

