"""Deterministic GitHub Agent tests using a local native-Git runner substitute."""
from __future__ import annotations
import subprocess
import pytest
from backend.app.core.settings import AppSettings
from backend.app.domain.github import GitHubActionRequest
from backend.app.github.controller import GitHubController

class Runner:
    """Capture native Git commands and return controlled output."""
    def __init__(self, status: str = " M app.py") -> None: self.calls=[]; self.status=status
    def __call__(self,args,**kwargs):
        self.calls.append(args)
        if args[1:]==["status","--short"]: return subprocess.CompletedProcess(args,0,self.status,"")
        if args[1:]==["log","-1","--pretty=%h %s"]: return subprocess.CompletedProcess(args,0,"abc123 feat: test","")
        return subprocess.CompletedProcess(args,0,"ok","")

class Client:
    """Official-API substitute without network access."""
    def __init__(self): self.calls=[]
    async def request(self,method,path,payload): self.calls.append((method,path,payload)); return {"html_url":"https://github.test/item","number":4,"name":"demo"}

@pytest.mark.anyio
async def test_local_git_actions_generate_conventional_commit_and_confirmation_gates(tmp_path):
    runner=Runner(); controller=GitHubController(AppSettings(github_default_repository=tmp_path),runner=runner,client=Client())
    init=await controller.execute(GitHubActionRequest(action="init",repo_path=str(tmp_path)))
    added=await controller.execute(GitHubActionRequest(action="add",repo_path=str(tmp_path),paths=["app.py"]))
    committed=await controller.execute(GitHubActionRequest(action="commit",repo_path=str(tmp_path)))
    force=await controller.execute(GitHubActionRequest(action="push",repo_path=str(tmp_path),force=True))
    merge=await controller.execute(GitHubActionRequest(action="merge",repo_path=str(tmp_path),branch="feature/x"))
    assert init.success and added.success and committed.success
    assert ["git","commit","-m","chore: update 1 file"] in runner.calls
    assert force.confirmation_required and merge.confirmation_required

@pytest.mark.anyio
async def test_status_branches_pull_summary_api_and_conflict_explanation(tmp_path):
    runner=Runner(); client=Client(); controller=GitHubController(AppSettings(github_default_repository=tmp_path),runner=runner,client=client)
    status=await controller.execute(GitHubActionRequest(action="status",repo_path=str(tmp_path)))
    created=await controller.execute(GitHubActionRequest(action="branch_create",repo_path=str(tmp_path),branch="feature/x"))
    switched=await controller.execute(GitHubActionRequest(action="branch_switch",repo_path=str(tmp_path),branch="feature/x"))
    pull=await controller.execute(GitHubActionRequest(action="pull",repo_path=str(tmp_path)))
    summary=await controller.execute(GitHubActionRequest(action="repository_summary",repo_path=str(tmp_path)))
    issue=await controller.execute(GitHubActionRequest(action="issue_create",owner="o",repository="r",title="Bug"))
    pr=await controller.execute(GitHubActionRequest(action="pull_request_create",owner="o",repository="r",title="PR",head="x",base="main"))
    assert status.success and created.success and switched.success and pull.confirmation_required
    assert summary.data["latest_commit"] == "abc123 feat: test" and issue.success and pr.success
    def conflict(args,**kwargs): raise subprocess.CalledProcessError(1,args,stderr="CONFLICT (content): merge conflict")
    failed=await GitHubController(AppSettings(github_default_repository=tmp_path),runner=conflict,client=client).execute(GitHubActionRequest(action="merge",repo_path=str(tmp_path),branch="x",confirmed=True))
    assert not failed.success and failed.data["merge_conflict"] and "Resolve" in failed.message
