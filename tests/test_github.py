"""Deterministic GitHub Agent tests using a local native-Git runner substitute."""
from __future__ import annotations
import subprocess
import pytest
from fastapi.testclient import TestClient
from backend.app.api.routes import ai, github
from backend.app.core.settings import AppSettings
from backend.app.domain.github import GitHubActionRequest, GitHubActionResult
from backend.app.github.controller import GitHubController
from backend.app.github.client import GitHubRestClient
from backend.app.main import create_app

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

@pytest.mark.anyio
async def test_clone_push_pull_merge_and_public_branch_confirmation(tmp_path):
    """Successful native Git operations and every remaining confirmation gate are deterministic."""
    runner=Runner(status=""); controller=GitHubController(AppSettings(github_default_repository=tmp_path),runner=runner,client=Client())
    clone=await controller.execute(GitHubActionRequest(action="clone",repo_path=str(tmp_path/"clone"),remote_url="https://example.test/repo.git"))
    push=await controller.execute(GitHubActionRequest(action="push",repo_path=str(tmp_path)))
    pull=await controller.execute(GitHubActionRequest(action="pull",repo_path=str(tmp_path)))
    merge=await controller.execute(GitHubActionRequest(action="merge",repo_path=str(tmp_path),branch="feature/x",confirmed=True))
    public=await controller.execute(GitHubActionRequest(action="repository_create",repository="public",visibility="public"))
    deleted=await controller.execute(GitHubActionRequest(action="branch_delete",repo_path=str(tmp_path),branch="old"))
    assert clone.success and push.success and pull.success and merge.success
    assert ["git","clone","https://example.test/repo.git",str(tmp_path/"clone")] in runner.calls
    assert ["git","push"] in runner.calls and ["git","pull"] in runner.calls and ["git","merge","feature/x"] in runner.calls
    assert public.confirmation_required and deleted.confirmation_required

@pytest.mark.anyio
async def test_repository_creation_and_token_are_safe(tmp_path, monkeypatch, caplog):
    """REST creation uses a token only in request headers and never exposes it in results or logs."""
    client=Client(); controller=GitHubController(AppSettings(github_default_repository=tmp_path,github_token="token-secret"),runner=Runner(),client=client)
    result=await controller.execute(GitHubActionRequest(action="repository_create",repository="private"))
    assert result.success and client.calls == [("POST","/user/repos",{"name":"private","private":True})]
    assert "token-secret" not in str(result.model_dump()) and "token-secret" not in caplog.text
    rest=GitHubRestClient("token-secret","https://api.github.com")
    assert "token-secret" not in vars(rest).get("_base_url")

def test_github_route_persists_clone_and_repository_creation(monkeypatch):
    """API responses remain structured while successful repositories enter local memory."""
    class Controller:
        async def execute(self, request): return GitHubActionResult(success=True,message="ok",data={})
    class Store:
        def __init__(self): self.items=[]
        def save(self,item): self.items.append(item)
    store=Store(); monkeypatch.setattr(github,"get_github_controller",lambda:Controller()); monkeypatch.setattr(github,"get_memory_store",lambda:store)
    client=TestClient(create_app())
    clone=client.post("/api/v1/github/actions",json={"action":"clone","remote_url":"https://example.test/a.git"})
    created=client.post("/api/v1/github/actions",json={"action":"repository_create","repository":"a"})
    assert clone.json()["success"] and created.json()["data"]["success"]
    assert [item.memory_type for item in store.items] == ["github_repository","github_repository"]
    assert all("token" not in item.content for item in store.items)

def test_ai_and_voice_command_text_route_to_github_agent(monkeypatch):
    """The chat route used by typed and recognized voice commands dispatches GitHub phrases before Ollama."""
    class Controller:
        async def execute(self, request): return GitHubActionResult(success=True,message="GitHub dispatched.")
    monkeypatch.setattr(ai,"get_github_controller",lambda:Controller())
    response=TestClient(create_app()).post("/api/v1/chat",json={"message":"Mjolnir, summarize this repository."})
    assert response.status_code == 200 and "GitHub dispatched." in response.text
