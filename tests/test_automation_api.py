import asyncio

from fastapi.testclient import TestClient

from backend.app.automation.automation_service import AutomationService
from backend.app.core.settings import AppSettings
from backend.app.domain.automation import StepAction, WorkflowCreate, WorkflowStep
from backend.app.main import create_app


def _settings(tmp_path) -> AppSettings:
    return AppSettings(automation_storage_directory=tmp_path / "automation")


def _payload() -> dict[str, object]:
    return {
        "name": "Focus sprint",
        "description": "Prepare a focused sprint.",
        "steps": [
            {
                "id": "announce",
                "title": "Announce start",
                "action": "notify",
                "priority": 5,
                "message": "Sprint started.",
            },
            {
                "id": "finish",
                "title": "Confirm readiness",
                "action": "notify",
                "priority": 3,
                "depends_on": ["announce"],
                "message": "Sprint ready.",
            },
        ],
    }


def test_workflow_crud_planning_and_execution_api(tmp_path, monkeypatch) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setattr(
        "backend.app.api.routes.automation.get_settings", lambda: settings
    )
    client = TestClient(create_app(settings))

    built_ins = client.get("/api/v1/automation/workflows")
    assert built_ins.status_code == 200
    assert any(item["id"] == "coding_mode" for item in built_ins.json()["data"])

    created = client.post("/api/v1/automation/workflows", json=_payload())
    assert created.status_code == 201
    workflow_id = created.json()["data"]["id"]

    plan = client.post(
        "/api/v1/automation/plans", json={"goal": "prepare my coding setup"}
    )
    assert plan.status_code == 200
    assert plan.json()["data"]["workflow_id"] == "coding_mode"

    started = client.post(f"/api/v1/automation/workflows/{workflow_id}/executions")
    assert started.status_code == 200
    execution_id = started.json()["data"]["id"]
    execution = client.get(f"/api/v1/automation/executions/{execution_id}")
    assert execution.status_code == 200
    assert execution.json()["data"]["progress_percent"] in range(0, 101)

    deleted = client.delete(f"/api/v1/automation/workflows/{workflow_id}")
    assert deleted.status_code == 204


def test_service_orders_dependencies_and_supports_cancellation(tmp_path) -> None:
    service = AutomationService(_settings(tmp_path))
    workflow = service.create_workflow(
        WorkflowCreate(
            name="Dependency test",
            description="Verify ordering.",
            steps=[
                WorkflowStep(
                    id="first",
                    title="First",
                    action=StepAction.NOTIFY,
                    message="First complete.",
                    priority=1,
                ),
                WorkflowStep(
                    id="second",
                    title="Second",
                    action=StepAction.NOTIFY,
                    message="Second complete.",
                    depends_on=["first"],
                    priority=5,
                ),
            ],
        )
    )
    execution = service.begin_execution(workflow.id)
    completed = asyncio.run(service.run_execution(execution.id))
    assert completed.status == "completed"
    assert [step.status for step in completed.steps] == ["completed", "completed"]

    waiting = service.create_workflow(
        WorkflowCreate(
            name="Cancellation test",
            description="Verify cancellation.",
            steps=[
                WorkflowStep(
                    id="wait", title="Wait", action=StepAction.WAIT, duration_seconds=1
                ),
            ],
        )
    )
    active = service.begin_execution(waiting.id)
    assert service.cancel_execution(active.id).status == "cancelled"


def test_workflow_validation_rejects_dependency_cycles(tmp_path) -> None:
    service = AutomationService(_settings(tmp_path))
    payload = WorkflowCreate(
        name="Cycle",
        description="Invalid cycle.",
        steps=[
            WorkflowStep(
                id="one",
                title="One",
                action=StepAction.WAIT,
                duration_seconds=0,
                depends_on=["two"],
            ),
            WorkflowStep(
                id="two",
                title="Two",
                action=StepAction.WAIT,
                duration_seconds=0,
                depends_on=["one"],
            ),
        ],
    )

    import pytest

    with pytest.raises(Exception, match="dependency cycle"):
        service.create_workflow(payload)
