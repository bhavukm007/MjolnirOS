"""Deterministic, extensible goal decomposition for the automation engine."""

from __future__ import annotations

from backend.app.automation.automation_service import AutomationService
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
