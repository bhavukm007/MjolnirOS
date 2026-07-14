"""Deterministic, extensible goal decomposition for the automation engine."""

from __future__ import annotations

import logging

from backend.app.automation.automation_service import AutomationService
from backend.app.core.settings import get_settings
from backend.app.domain.automation import PlanRequest, PlannedTask, TaskPlan


class PlannerService:
    """Turn natural-language goals into transparent dependency-aware task plans."""

    _WORKFLOW_KEYWORDS = {
        "coding_mode": ("coding", "code", "developer", "programming"),
        "study_mode": ("study", "learn", "revision"),
        "interview_mode": ("interview",),
        "presentation_mode": ("presentation", "present"),
        "gaming_mode": ("gaming", "game"),
        "morning_routine": ("morning", "start my day"),
        "placement_preparation": ("placement",),
        "shutdown_routine": ("shutdown", "shut down", "end my day"),
    }

    def __init__(self, automation: AutomationService) -> None:
        self._automation = automation
        self._logger = logging.getLogger(__name__)

    def create_plan(self, request: PlanRequest) -> TaskPlan:
        """Return a predictable plan, preferring a matching built-in workflow."""
        normalized_goal = request.goal.lower()
        workflow_id = next(
            (
                candidate
                for candidate, keywords in self._WORKFLOW_KEYWORDS.items()
                if any(keyword in normalized_goal for keyword in keywords)
            ),
            None,
        )
        if workflow_id:
            workflow = self._automation.get_workflow(workflow_id)
            return TaskPlan(
                goal=request.goal,
                workflow_id=workflow.id,
                tasks=[
                    PlannedTask(
                        id=step.id,
                        title=step.title,
                        priority=step.priority,
                        depends_on=step.depends_on,
                    )
                    for step in sorted(
                        workflow.steps, key=lambda item: item.priority, reverse=True
                    )
                ],
            )
        return TaskPlan(
            goal=request.goal,
            tasks=[
                PlannedTask(
                    id="clarify", title="Clarify the desired outcome", priority=5
                ),
                PlannedTask(
                    id="prepare",
                    title="Prepare the required local resources",
                    priority=4,
                    depends_on=["clarify"],
                ),
                PlannedTask(
                    id="complete",
                    title="Confirm the goal is complete",
                    priority=3,
                    depends_on=["prepare"],
                ),
            ],
        )

    async def execute_goal(self, goal: str) -> str | None:
        """Run a recognized plan step through its existing owning agent."""
        self._logger.info("planner_input", extra={"goal": goal})
        from backend.app.api.routes.memory import get_memory_store
        from backend.app.api.routes.browser import get_browser_controller
        from backend.app.api.routes.coding import get_coding_controller
        from backend.app.api.routes.github import get_github_controller
        from backend.app.api.routes.windows import get_windows_controller
        from backend.app.browser.natural_language import parse_browser_command
        from backend.app.coding.natural_language import parse_coding_command
        from backend.app.github.natural_language import parse_github_command
        from backend.app.windows.natural_language import execute_natural_command
        from backend.app.domain.memory import MemoryCreate
        from backend.app.vision.document_service import DocumentService
        from backend.app.domain.vision import DocumentType

        normalized = goal.strip().lower().rstrip(".?!")
        if normalized.startswith("remember "):
            content = goal.strip()[len("remember "):].strip().rstrip(".?!")
            get_memory_store().save(MemoryCreate(memory_type="note", content=content, metadata={"source": "assistant"}))
            return f"I'll remember that: {content}."
        if normalized in {"what did i tell you", "what did i ask you to remember"}:
            notes = get_memory_store().list("note")
            return f"You told me: {notes[0].content}." if notes else "You have not asked me to remember anything yet."
        if normalized in {"summarize a pdf", "summarize the pdf", "summarize my pdf"}:
            service = DocumentService(get_settings())
            pdfs = [record for record in service.list() if record.document_type is DocumentType.PDF]
            if not pdfs:
                return "Upload a PDF in Documents first, then ask me to summarize it."
            return service.summarize(pdfs[0]).summary

        browser = parse_browser_command(goal)
        if browser is not None:
            return (await get_browser_controller().execute(browser)).message
        github = parse_github_command(goal)
        if github is not None:
            return (await get_github_controller().execute(github)).message
        coding = parse_coding_command(goal)
        if coding is not None:
            return get_coding_controller().execute(coding).message
        windows = execute_natural_command(goal, get_windows_controller())
        if windows is not None:
            self._logger.info(
                "planner_output",
                extra={
                    "goal": goal,
                    "agent": "windows",
                    "success": windows.success,
                    "result_message": windows.message,
                    "data": windows.data,
                },
            )
        return windows.message if windows is not None else None
