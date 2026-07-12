"""REST integration for safe workflows, progress tracking, and task planning."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Response, status

from backend.app.automation.automation_service import AutomationService
from backend.app.automation.planner_service import PlannerService
from backend.app.core.responses import ApiResponse
from backend.app.core.settings import get_settings
from backend.app.domain.automation import (
    PlanRequest,
    TaskPlan,
    Workflow,
    WorkflowCreate,
    WorkflowExecution,
)

router = APIRouter(prefix="/automation", tags=["automation", "planner"])
logger = logging.getLogger(__name__)


def _automation() -> AutomationService:
    return AutomationService(get_settings())


@router.get("/workflows", response_model=ApiResponse[list[Workflow]])
async def list_workflows() -> ApiResponse[list[Workflow]]:
    """List built-in and persisted custom workflows."""
    return ApiResponse(
        success=True, message="Workflows loaded.", data=_automation().list_workflows()
    )


@router.post(
    "/workflows",
    response_model=ApiResponse[Workflow],
    status_code=status.HTTP_201_CREATED,
)
async def create_workflow(payload: WorkflowCreate) -> ApiResponse[Workflow]:
    """Record and save a user-defined workflow."""
    workflow = _automation().create_workflow(payload)
    logger.info("workflow_created", extra={"workflow_id": workflow.id})
    return ApiResponse(success=True, message="Custom workflow saved.", data=workflow)


@router.put("/workflows/{workflow_id}", response_model=ApiResponse[Workflow])
async def update_workflow(
    workflow_id: str, payload: WorkflowCreate
) -> ApiResponse[Workflow]:
    """Edit an existing user-defined workflow."""
    workflow = _automation().update_workflow(workflow_id, payload)
    return ApiResponse(success=True, message="Custom workflow updated.", data=workflow)


@router.delete("/workflows/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(workflow_id: str) -> Response:
    """Delete a user-defined workflow."""
    _automation().delete_workflow(workflow_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/workflows/{workflow_id}/executions", response_model=ApiResponse[WorkflowExecution]
)
async def start_workflow(workflow_id: str) -> ApiResponse[WorkflowExecution]:
    """Start a workflow asynchronously so its progress can be viewed or cancelled."""
    service = _automation()
    execution = service.begin_execution(workflow_id)
    asyncio.create_task(service.run_execution(execution.id))
    return ApiResponse(
        success=True,
        message="Workflow execution started.",
        data=service.view_execution(execution.id),
    )


@router.get("/executions", response_model=ApiResponse[list[WorkflowExecution]])
async def list_executions() -> ApiResponse[list[WorkflowExecution]]:
    """List workflow runs and their persisted progress."""
    return ApiResponse(
        success=True, message="Executions loaded.", data=_automation().list_executions()
    )


@router.get("/executions/{execution_id}", response_model=ApiResponse[WorkflowExecution])
async def get_execution(execution_id: str) -> ApiResponse[WorkflowExecution]:
    """Get current workflow progress."""
    return ApiResponse(
        success=True,
        message="Execution loaded.",
        data=_automation().view_execution(execution_id),
    )


@router.post(
    "/executions/{execution_id}/cancel", response_model=ApiResponse[WorkflowExecution]
)
async def cancel_execution(execution_id: str) -> ApiResponse[WorkflowExecution]:
    """Cancel an active workflow without executing remaining steps."""
    execution = _automation().cancel_execution(execution_id)
    logger.info("workflow_cancelled", extra={"execution_id": execution_id})
    return ApiResponse(success=True, message="Execution cancelled.", data=execution)


@router.post("/plans", response_model=ApiResponse[TaskPlan])
async def create_plan(request: PlanRequest) -> ApiResponse[TaskPlan]:
    """Create a transparent local plan for a natural-language goal."""
    plan = PlannerService(_automation()).create_plan(request)
    return ApiResponse(success=True, message="Task plan created.", data=plan)
