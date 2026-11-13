import asyncio
import pytest
from app.core.planner import TaskPlanner
from app.schemas.planner import IntentCategory, TargetAgent


@pytest.mark.asyncio
async def test_ambiguous_short_prompt_triggers_clarification():
    """Verify that ambiguous short commands prompt for user clarification."""
    planner = TaskPlanner()
    plan = await planner.generate_plan("do it")

    assert plan.requires_clarification is True
    assert plan.clarification_prompt is not None
    assert len(plan.steps) == 0


@pytest.mark.asyncio
async def test_empty_prompt_triggers_clarification():
    """Verify empty input prompts for user clarification."""
    planner = TaskPlanner()
    plan = await planner.generate_plan("   ")

    assert plan.requires_clarification is True
    assert plan.clarification_prompt is not None


@pytest.mark.asyncio
async def test_single_step_developer_task():
    """Verify developer / coding requests yield a DeveloperAgent DAG step."""
    planner = TaskPlanner()
    prompt = "Write a python script to parse CSV files and run unit tests"
    plan = await planner.generate_plan(prompt)

    assert plan.requires_clarification is False
    assert len(plan.steps) >= 1
    # Check that DeveloperAgent is involved
    assert any(step.target_agent in (TargetAgent.DeveloperAgent, TargetAgent.FileAgent) for step in plan.steps)


@pytest.mark.asyncio
async def test_multi_step_hybrid_dag_dependencies():
    """Verify research and excel document generation produces dependent DAG steps."""
    planner = TaskPlanner()
    prompt = "Search online for top 10 AI startups in 2026 and compile them into an Excel spreadsheet in workspace"
    plan = await planner.generate_plan(prompt)

    assert plan.requires_clarification is False
    assert len(plan.steps) >= 2

    # Step 1 should be Browser / research, Step 2 should depend on Step 1
    step_ids = [s.step_id for s in plan.steps]
    assert "step_1" in step_ids

    # Verify at least one step depends on an earlier step
    has_dependency = any(len(s.depends_on) > 0 for s in plan.steps)
    assert has_dependency is True


if __name__ == "__main__":
    async def run_manual_checks():
        planner = TaskPlanner()
        print("--- Testing Ambiguous Request ---")
        p1 = await planner.generate_plan("search")
        print("Requires clarification:", p1.requires_clarification)
        print("Prompt:", p1.clarification_prompt)

        print("\n--- Testing Multi-step Plan ---")
        p2 = await planner.generate_plan("Search top 5 renewable energy stocks and create an excel sheet in workspace")
        print("Intent Category:", p2.intent_category)
        print("Summary:", p2.summary)
        print("Steps count:", len(p2.steps))
        for s in p2.steps:
            print(f"  [{s.step_id}] {s.target_agent.value} ➔ {s.description} (depends: {s.depends_on})")

    asyncio.run(run_manual_checks())

