"""Persistent, approval-gated local learning and automation suggestions."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
import json
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException

from backend.app.automation.automation_service import AutomationService
from backend.app.core.settings import AppSettings
from backend.app.domain.automation import (
    StepAction,
    Workflow,
    WorkflowCreate,
    WorkflowStep,
)
from backend.app.domain.learning import (
    LearningObservation,
    LearningObservationCreate,
    LearningOverview,
    LearningPreference,
    LearningSuggestion,
    ObservationKind,
    SuggestionStatus,
)


class LearningService:
    """Learn repeatable local habits without automatically executing them."""

    _IDE_NAMES = {
        "vs code",
        "visual studio",
        "pycharm",
        "intellij idea",
        "sublime text",
        "vim",
        "neovim",
    }

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._directory = settings.learning_storage_directory
        self._observations_path = self._directory / "observations.json"
        self._preferences_path = self._directory / "preferences.json"
        self._suggestions_path = self._directory / "suggestions.json"

    def record_observation(
        self, payload: LearningObservationCreate
    ) -> LearningObservation:
        """Persist an activity signal and refresh learned preferences and suggestions."""
        observation = LearningObservation(id=uuid4().hex, **payload.model_dump())
        observations = self._observations()
        observations.append(observation)
        self._write(self._observations_path, observations)
        self._write(self._preferences_path, self._derive_preferences(observations))
        self._generate_suggestions(observations)
        return observation

    def overview(self) -> LearningOverview:
        """Return current preference inferences and all suggestion states."""
        return LearningOverview(
            observation_count=len(self._observations()),
            preferences=self.preferences(),
            suggestions=self.suggestions(),
        )

    def preferences(self) -> list[LearningPreference]:
        """Return stable preference inferences ordered by category."""
        return sorted(
            self._load(self._preferences_path, LearningPreference),
            key=lambda item: item.key,
        )

    def suggestions(self) -> list[LearningSuggestion]:
        """Return suggestions with pending recommendations first."""
        return sorted(
            self._load(self._suggestions_path, LearningSuggestion),
            key=lambda item: (item.status is not SuggestionStatus.PENDING, item.title),
        )

    def approve_suggestion(
        self, suggestion_id: str, automation: AutomationService
    ) -> Workflow:
        """Create a safe workflow only after an explicit user approval."""
        suggestion = self._suggestion(suggestion_id)
        if suggestion.status is not SuggestionStatus.PENDING:
            raise HTTPException(
                status_code=409, detail="Suggestion has already been decided."
            )
        steps = [
            WorkflowStep(
                id="announce",
                title="Confirm routine start",
                action=StepAction.NOTIFY,
                priority=5,
                message=f"Starting {suggestion.title}.",
            )
        ]
        for index, item in enumerate(suggestion.items, start=1):
            steps.append(
                WorkflowStep(
                    id=f"habit-{index}",
                    title=f"Prepare {item}",
                    action=StepAction.NOTIFY,
                    priority=4,
                    depends_on=["announce"],
                    message=f"Preferred habit: {item}.",
                )
            )
        workflow = automation.create_workflow(
            WorkflowCreate(
                name=suggestion.title,
                description=suggestion.description,
                steps=steps,
            )
        )
        suggestion.status = SuggestionStatus.APPROVED
        suggestion.workflow_id = workflow.id
        suggestion.updated_at = datetime.now(UTC)
        self._save_suggestion(suggestion)
        return workflow

    def dismiss_suggestion(self, suggestion_id: str) -> LearningSuggestion:
        """Dismiss a suggestion so learning never repeatedly asks for the same routine."""
        suggestion = self._suggestion(suggestion_id)
        if suggestion.status is SuggestionStatus.PENDING:
            suggestion.status = SuggestionStatus.DISMISSED
            suggestion.updated_at = datetime.now(UTC)
            self._save_suggestion(suggestion)
        return suggestion

    def _observations(self) -> list[LearningObservation]:
        return self._load(self._observations_path, LearningObservation)

    def _derive_preferences(
        self, observations: list[LearningObservation]
    ) -> list[LearningPreference]:
        preferences: list[LearningPreference] = []
        for kind, key in (
            (ObservationKind.BROWSER, "preferred_browser"),
            (ObservationKind.CODING_STYLE, "coding_style"),
            (ObservationKind.FOLDER, "preferred_folder"),
            (ObservationKind.COMMAND, "frequent_command"),
            (ObservationKind.REPOSITORY, "favorite_repository"),
        ):
            values = [item.value for item in observations if item.kind is kind]
            if values:
                value, occurrences = Counter(values).most_common(1)[0]
                preferences.append(
                    LearningPreference(key=key, value=value, occurrences=occurrences)
                )
        apps = [
            item.value
            for item in observations
            if item.kind is ObservationKind.APPLICATION
        ]
        if apps:
            value, occurrences = Counter(apps).most_common(1)[0]
            preferences.append(
                LearningPreference(
                    key="preferred_application", value=value, occurrences=occurrences
                )
            )
            ide_values = [item for item in apps if item.lower() in self._IDE_NAMES]
            if ide_values:
                ide, ide_occurrences = Counter(ide_values).most_common(1)[0]
                preferences.append(
                    LearningPreference(
                        key="preferred_ide", value=ide, occurrences=ide_occurrences
                    )
                )
        return preferences

    def _generate_suggestions(self, observations: list[LearningObservation]) -> None:
        candidates = [
            item.value
            for item in observations
            if item.kind
            in {
                ObservationKind.APPLICATION,
                ObservationKind.BROWSER,
                ObservationKind.STARTUP,
            }
        ]
        repeated = sorted(
            value
            for value, count in Counter(candidates).items()
            if count >= self._settings.learning_suggestion_threshold
        )
        if not repeated:
            return
        signature = "daily-routine:" + "|".join(repeated)
        suggestions = self.suggestions()
        existing = next(
            (item for item in suggestions if item.signature == signature), None
        )
        if existing:
            return
        occurrences = min(Counter(candidates)[item] for item in repeated)
        suggestions.append(
            LearningSuggestion(
                id=uuid4().hex,
                signature=signature,
                title="Suggested daily routine",
                description=f"You repeatedly use {', '.join(repeated)}. Create a safe routine?",
                items=repeated,
                occurrences=occurrences,
            )
        )
        self._write(self._suggestions_path, suggestions)

    def _suggestion(self, suggestion_id: str) -> LearningSuggestion:
        try:
            return next(item for item in self.suggestions() if item.id == suggestion_id)
        except StopIteration as error:
            raise HTTPException(
                status_code=404, detail="Learning suggestion was not found."
            ) from error

    def _save_suggestion(self, suggestion: LearningSuggestion) -> None:
        suggestions = self.suggestions()
        for index, item in enumerate(suggestions):
            if item.id == suggestion.id:
                suggestions[index] = suggestion
                break
        self._write(self._suggestions_path, suggestions)

    def _load(
        self,
        path: Path,
        model: (
            type[LearningObservation]
            | type[LearningPreference]
            | type[LearningSuggestion]
        ),
    ) -> list:
        if not path.exists():
            return []
        return [
            model.model_validate(item)
            for item in json.loads(path.read_text(encoding="utf-8"))
        ]

    def _write(self, path: Path, records: list[object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps([item.model_dump(mode="json") for item in records], indent=2),
            encoding="utf-8",
        )  # type: ignore[union-attr]
