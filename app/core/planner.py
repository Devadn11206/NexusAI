import json
import logging
from typing import Optional, Dict, Any
import httpx

from app.config import settings
from app.schemas.planner import (
    TaskGraph,
    TaskStep,
    IntentCategory,
    TargetAgent,
)

logger = logging.getLogger(__name__)

PLANNER_SYSTEM_PROMPT = """You are the Lead Multi-Agent Task Planner and Intent Decomposition Engine for NEXUS AI.
Your job is to analyze the user's natural language request and output a STRICT JSON object representing an optimal Directed Acyclic Graph (DAG) task execution plan.

Target Agent Capabilities:
- ComputerAgent: Opening local applications on laptop (e.g. Notepad, Calculator, Spotify, Chrome, VS Code), closing applications, window management, desktop screenshots, mouse/keyboard hotkeys.
  * To launch an app: tool_name `launch_application` with `tool_params: {"app_name": "notepad"}`.
  * To close/quit an app: tool_name `close_application` with `tool_params: {"process_name": "notepad"}` (or "chrome", "spotify", "calculator", "vscode", etc.).
  * To play songs or playlists on Spotify: tool_name `play_music` with `tool_params: {"app_name": "spotify", "song": "Metro Proposal", "playlist": "Liked Songs"}`.
  * To control playback: tool_name `control_media` with `tool_params: {"action": "play" | "pause" | "stop" | "next" | "previous" | "forward" | "rewind" | "volume_up" | "volume_down" | "mute" | "shuffle" | "repeat"}`.
- BrowserAgent: Web searches, reading websites, scraping data, navigating portals, interacting with web apps. Tool name: `search_web` or `navigate_page`.
- FileAgent: File & folder operations in ./workspace/, reading/writing CSV, text, PDFs, Excel sheets (.xlsx), Word docs (.docx). Tool name: `create_file`, `read_file`, `organize_directory`.
- DeveloperAgent: Shell commands, Git operations, running Python scripts, debugging code, executing tests.
  * To execute shell commands: tool_name `run_command` with `tool_params: {"command": "dir"}`.
  * To run Python code: tool_name `run_python` with `tool_params: {"code": "print('Hello world')", "filename": "test.py"}`.
  * To run Git: tool_name `git` with `tool_params: {"subcommand": "status"}`.
- SupervisorAgent: Aggregation and multi-domain syntheses.

Intent Categories:
- BROWSER, FILESYSTEM, DOCUMENTS, DEVELOPER, COMPUTER, HYBRID

Ambiguity & Clarification Policy:
- If a request is completely vague or has zero context (e.g. only "do it", "fix it", "run", "help me"), set `requires_clarification` to true and provide a specific `clarification_prompt`.
- If the user provides a specific task (such as writing code, creating a script, searching a topic, or organizing files), DO NOT ask for clarification. Assume sensible defaults in `./workspace/`, set `requires_clarification` to false, and generate the actionable `steps` immediately.
- Every multi-step task must express dependencies: if step_2 needs the output of step_1, set `depends_on: ["step_1"]`.

You MUST output ONLY a valid JSON object matching the TaskGraph schema:
{
  "intent_category": "BROWSER" | "FILESYSTEM" | "DOCUMENTS" | "DEVELOPER" | "COMPUTER" | "HYBRID",
  "summary": "Short 1-2 sentence overview of the plan",
  "requires_clarification": false,
  "clarification_prompt": null,
  "steps": [
    {
      "step_id": "step_1",
      "description": "Specific action to perform",
      "target_agent": "BrowserAgent" | "FileAgent" | "DeveloperAgent" | "DocumentAgent" | "ComputerAgent" | "SupervisorAgent",
      "tool_name": "tool_to_call",
      "tool_params": {},
      "depends_on": [],
      "expected_output": "Description of artifact or outcome"
    }
  ]
}
"""


class TaskPlanner:
    """Autonomous Task Planner and Ambiguity Interceptor using Groq LLM."""

    def __init__(self, model: str = "qwen/qwen3.8-27b"):
        self.model = model
        self.api_key = settings.GROQ_API_KEY
        self.endpoint = "https://api.groq.com/openai/v1/chat/completions"

    async def generate_plan(
        self,
        prompt: str,
        user_context: Optional[Dict[str, Any]] = None,
    ) -> TaskGraph:
        """
        Decomposes raw user prompt into a structured TaskGraph DAG.
        Falls back to rule-based generation if LLM is unavailable or unconfigured.
        """
        clean_prompt = prompt.strip()
        if not clean_prompt:
            return TaskGraph(
                intent_category=IntentCategory.HYBRID,
                summary="Empty prompt received.",
                requires_clarification=True,
                clarification_prompt="I received an empty prompt. What would you like me to do?",
                steps=[],
            )

        # Fast heuristic ambiguity interceptor
        if len(clean_prompt.split()) <= 2 and clean_prompt.lower() in [
            "do it", "fix it", "run", "search", "create", "delete", "help me"
        ]:
            return TaskGraph(
                intent_category=IntentCategory.HYBRID,
                summary="Ambiguous short instruction.",
                requires_clarification=True,
                clarification_prompt=f"Could you please provide more details on what you would like to {clean_prompt}?",
                steps=[],
            )

        if not self.api_key:
            logger.warning("GROQ_API_KEY is not configured; using fallback rule-based planner.")
            return self._fallback_rule_based_plan(clean_prompt)

        messages = [
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"User Request: {clean_prompt}\nUser Context: {json.dumps(user_context or {})}",
            },
        ]

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(
                    self.endpoint,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                res.raise_for_status()
                data = res.json()
                content = data["choices"][0]["message"]["content"]
                parsed_json = json.loads(content)
                plan = TaskGraph.model_validate(parsed_json)
                logger.info(f"Task plan successfully synthesized with {len(plan.steps)} steps (Category: {plan.intent_category}).")
                return plan

        except Exception as exc:
            logger.error(f"LLM planner failed: {exc}. Falling back to rule-based decomposition.", exc_info=True)
            return self._fallback_rule_based_plan(clean_prompt)

    def _fallback_rule_based_plan(self, prompt: str) -> TaskGraph:
        """Deterministic rule-based fallback DAG generator."""
        p_lower = prompt.lower()

        # Multi-step search & document pattern
        if ("search" in p_lower or "research" in p_lower) and ("excel" in p_lower or "file" in p_lower or "doc" in p_lower):
            return TaskGraph(
                intent_category=IntentCategory.HYBRID,
                summary="Research topic online and create structured file in workspace.",
                requires_clarification=False,
                clarification_prompt=None,
                steps=[
                    TaskStep(
                        step_id="step_1",
                        description=f"Search online information for: {prompt}",
                        target_agent=TargetAgent.BrowserAgent,
                        tool_name="web_search",
                        tool_params={"query": prompt},
                        depends_on=[],
                        expected_output="Gathered research findings and summarized facts.",
                    ),
                    TaskStep(
                        step_id="step_2",
                        description="Format findings and save document into workspace sandbox.",
                        target_agent=TargetAgent.FileAgent,
                        tool_name="write_file",
                        tool_params={"filename": "research_report.xlsx" if "excel" in p_lower else "research_report.md"},
                        depends_on=["step_1"],
                        expected_output="Generated file artifact stored in ./workspace/.",
                    ),
                ],
            )

        # Computer / Close Application pattern
        if any(w in p_lower for w in ["close", "quit", "exit", "kill", "terminate", "shut down", "stop"]) and any(
            app_w in p_lower for app_w in ["app", "application", "chrome", "notepad", "spotify", "calculator", "calc", "vscode", "vs code", "terminal", "browser", "window"]
        ):
            # Extract target app
            target = "app"
            for candidate in ["chrome", "spotify", "notepad", "calculator", "calc", "vscode", "vs code", "terminal", "browser", "vlc", "explorer"]:
                if candidate in p_lower:
                    target = candidate
                    break

            return TaskGraph(
                intent_category=IntentCategory.COMPUTER,
                summary=f"Close desktop application '{target}' on laptop.",
                requires_clarification=False,
                clarification_prompt=None,
                steps=[
                    TaskStep(
                        step_id="step_1",
                        description=f"Close application: {target}",
                        target_agent=TargetAgent.ComputerAgent,
                        tool_name="close_application",
                        tool_params={"process_name": target},
                        depends_on=[],
                        expected_output=f"Closed application '{target}'.",
                    )
                ],
            )

        # Developer / Code pattern
        if any(w in p_lower for w in ["code", "script", "run", "python", "terminal", "bash", "git"]):
            return TaskGraph(
                intent_category=IntentCategory.DEVELOPER,
                summary="Develop code or execute system commands in workspace.",
                requires_clarification=False,
                clarification_prompt=None,
                steps=[
                    TaskStep(
                        step_id="step_1",
                        description=f"Execute developer task: {prompt}",
                        target_agent=TargetAgent.DeveloperAgent,
                        tool_name="run_command",
                        tool_params={"command": prompt},
                        depends_on=[],
                        expected_output="Terminal stdout/stderr and status code.",
                    )
                ],
            )

        # Browser pattern
        if any(w in p_lower for w in ["browse", "search", "google", "website", "url", "scrape", "look up"]):
            return TaskGraph(
                intent_category=IntentCategory.BROWSER,
                summary="Perform browser navigation and information retrieval.",
                requires_clarification=False,
                clarification_prompt=None,
                steps=[
                    TaskStep(
                        step_id="step_1",
                        description=f"Browse or search web for: {prompt}",
                        target_agent=TargetAgent.BrowserAgent,
                        tool_name="web_search",
                        tool_params={"query": prompt},
                        depends_on=[],
                        expected_output="Search results or website contents.",
                    )
                ],
            )

        # File operation pattern
        if any(w in p_lower for w in ["file", "excel", "csv", "write", "save", "document", "pdf"]):
            return TaskGraph(
                intent_category=IntentCategory.FILESYSTEM,
                summary="Execute file system manipulation inside workspace sandbox.",
                requires_clarification=False,
                clarification_prompt=None,
                steps=[
                    TaskStep(
                        step_id="step_1",
                        description=f"Perform file operation: {prompt}",
                        target_agent=TargetAgent.FileAgent,
                        tool_name="write_file",
                        tool_params={"instructions": prompt},
                        depends_on=[],
                        expected_output="File artifact in ./workspace/.",
                    )
                ],
            )

        # Default General / Hybrid Task
        return TaskGraph(
            intent_category=IntentCategory.HYBRID,
            summary="General task execution across agent swarm.",
            requires_clarification=False,
            clarification_prompt=None,
            steps=[
                TaskStep(
                    step_id="step_1",
                    description=prompt,
                    target_agent=TargetAgent.SupervisorAgent,
                    tool_name="orchestrate_task",
                    tool_params={"instruction": prompt},
                    depends_on=[],
                    expected_output="Task completion report.",
                )
            ],
        )


planner = TaskPlanner()
