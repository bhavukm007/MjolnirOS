"""Coding Agent tests."""
from backend.app.coding.controller import CodingController
from backend.app.domain.coding import CodingRequest
def test_coding_actions(tmp_path):
 c=CodingController(); blocked=c.execute(CodingRequest(action="terminal",command="echo ok")); assert blocked.confirmation_required
 explained=c.execute(CodingRequest(action="explain",code="print('x')",language="python")); assert explained.success
 project=c.execute(CodingRequest(action="generate_project",project_path=str(tmp_path),prompt="demo app")); assert project.success
