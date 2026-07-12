"""REST endpoints for local, approval-gated Learning Mode."""

from __future__ import annotations

import logging

from fastapi import APIRouter

from backend.app.automation.automation_service import AutomationService
from backend.app.core.responses import ApiResponse
from backend.app.core.settings import get_settings
from backend.app.domain.automation import Workflow
from backend.app.domain.learning import (
    LearningObservation,
    LearningObservationCreate,
    LearningOverview,
    LearningPreference,
    LearningSuggestion,
)
from backend.app.learning.learning_service import LearningService

router = APIRouter(prefix="/learning", tags=["learning"])
logger = logging.getLogger(__name__)


def _learning() -> LearningService:
    return LearningService(get_settings())


def _automation() -> AutomationService:
    return AutomationService(get_settings())


@router.get("/overview", response_model=ApiResponse[LearningOverview])
async def get_overview() -> ApiResponse[LearningOverview]:
    """Return observations, learned preferences, and approval states."""
    return ApiResponse(
        success=True, message="Learning overview loaded.", data=_learning().overview()
    )


@router.post("/observations", response_model=ApiResponse[LearningObservation])
async def record_observation(
    payload: LearningObservationCreate,
) -> ApiResponse[LearningObservation]:
    """Record a non-sensitive local activity signal for future pattern detection."""
    observation = _learning().record_observation(payload)
    logger.info("learning_observation_recorded", extra={"kind": observation.kind})
    return ApiResponse(
        success=True, message="Learning observation recorded.", data=observation
    )


@router.get("/preferences", response_model=ApiResponse[list[LearningPreference]])
async def get_preferences() -> ApiResponse[list[LearningPreference]]:
    """Return current preference inferences derived from local history."""
    return ApiResponse(
        success=True, message="Preferences loaded.", data=_learning().preferences()
    )


@router.get("/suggestions", response_model=ApiResponse[list[LearningSuggestion]])
async def get_suggestions() -> ApiResponse[list[LearningSuggestion]]:
    """Return pending, approved, and dismissed automation suggestions."""
    return ApiResponse(
        success=True, message="Suggestions loaded.", data=_learning().suggestions()
    )


@router.post(
    "/suggestions/{suggestion_id}/approve", response_model=ApiResponse[Workflow]
)
async def approve_suggestion(suggestion_id: str) -> ApiResponse[Workflow]:
    """Create a safe workflow only after the user explicitly approves a suggestion."""
    workflow = _learning().approve_suggestion(suggestion_id, _automation())
    logger.info("learning_suggestion_approved", extra={"suggestion_id": suggestion_id})
    return ApiResponse(
        success=True, message="Suggested workflow created.", data=workflow
    )


@router.post(
    "/suggestions/{suggestion_id}/dismiss",
    response_model=ApiResponse[LearningSuggestion],
)
async def dismiss_suggestion(suggestion_id: str) -> ApiResponse[LearningSuggestion]:
    """Dismiss an automation recommendation without creating any workflow."""
    suggestion = _learning().dismiss_suggestion(suggestion_id)
    return ApiResponse(success=True, message="Suggestion dismissed.", data=suggestion)
