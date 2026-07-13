"""Local Git controller and isolated GitHub REST operation layer."""
from __future__ import annotations
import logging
from pathlib import Path
import subprocess
from typing import Callable
from backend.app.core.settings import AppSettings
from backend.app.domain.github import GitHubActionRequest, GitHubActionResult
from backend.app.github.client import GitHubRestClient

class GitHubController:
    """Execute local Git work safely and delegate network calls to GitHubRestClient."""
    def __init__(self, settings: AppSettings, runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run, client: GitHubRestClient | None = None) -> None:
        self._settings, self._runner = settings, runner
        self._client = client or GitHubRestClient(settings.github_token, settings.github_api_base_url)
        self._logger=logging.getLogger(__name__)
    async def execute(self, request: GitHubActionRequest) -> GitHubActionResult:
        """Return a structured result without logging secrets."""
        if self._needs_confirmation(request): return GitHubActionResult(success=False,message="Confirmation is required before this Git operation.",confirmation_required=True)
        try: return await self._execute(request)
        except (OSError, ValueError, subprocess.CalledProcessError) as error:
            detail=getattr(error,"stderr","") or str(error)
            conflict="CONFLICT" in detail.upper()
            self._logger.warning("github_action_failed",extra={"action":request.action,"conflict":conflict})
            message="Merge conflict detected. Resolve the listed conflicts locally, stage the resolutions, then commit." if conflict else "GitHub operation failed. Check the repository and credentials."
            return GitHubActionResult(success=False,message=message,data={"merge_conflict":conflict})
    async def _execute(self, r: GitHubActionRequest) -> GitHubActionResult:
        if r.action=="repository_create": return await self._api("POST","/user/repos",{"name":self._required(r.repository,"repository"),"private":r.visibility=="private"},"Repository created.")
        if r.action=="issue_create": return await self._api("POST",f"/repos/{self._owner_repo(r)}/issues",{"title":self._required(r.title,"title"),"body":r.body or ""},"Issue created.")
        if r.action=="pull_request_create": return await self._api("POST",f"/repos/{self._owner_repo(r)}/pulls",{"title":self._required(r.title,"title"),"body":r.body or "","head":self._required(r.head,"head"),"base":self._required(r.base,"base")},"Pull request created.")
        path=self._path(r)
        if r.action=="repository_summary": return GitHubActionResult(success=True,message="Repository summary loaded.",data={"status":self._git(["status","--short"],path),"latest_commit":self._git(["log","-1","--pretty=%h %s"],path)})
        if r.action=="pull" and self._git(["status","--short"],path) and not r.confirmed:
            return GitHubActionResult(success=False,message="Confirmation is required before pulling over local changes.",confirmation_required=True)
        command=self._command(r,path); output=self._git(command,path if r.action!="clone" else None)
        if r.action=="status": return GitHubActionResult(success=True,message="Repository status loaded.",data={"status":output})
        return GitHubActionResult(success=True,message=f"Git {r.action.replace('_',' ')} completed.",data={"output":output,"message":r.message if r.action=="commit" else None})
    def _command(self,r: GitHubActionRequest,path:Path)->list[str]:
        if r.action=="init": return ["init"]
        if r.action=="clone": return ["clone",self._required(r.remote_url,"remote_url"),str(path)]
        if r.action=="status": return ["status","--short"]
        if r.action=="add": return ["add",*(r.paths or ["."])]
        if r.action=="commit": return ["commit","-m",r.message or self._commit_message(path)]
        if r.action=="push": return ["push",*( ["--force"] if r.force else [])]
        if r.action=="pull": return ["pull"]
        if r.action=="branch_create": return ["branch",self._required(r.branch,"branch")]
        if r.action=="branch_switch": return ["switch",self._required(r.branch,"branch")]
        if r.action=="merge": return ["merge",self._required(r.branch,"branch")]
        if r.action=="branch_delete": return ["branch","-d",self._required(r.branch,"branch")]
        raise ValueError("Unsupported Git action.")
    def _git(self,args:list[str],path:Path|None)->str:
        result=self._runner(["git",*args],cwd=str(path) if path else None,text=True,capture_output=True,check=True)
        return result.stdout.strip()
    async def _api(self,method:str,path:str,payload:dict[str,object],message:str)->GitHubActionResult:
        data=await self._client.request(method,path,payload); return GitHubActionResult(success=True,message=message,data={"url":data.get("html_url"),"number":data.get("number"),"name":data.get("name")})
    def _path(self,r:GitHubActionRequest)->Path: return Path(r.repo_path or self._settings.github_default_repository).expanduser().resolve()
    def _owner_repo(self,r:GitHubActionRequest)->str: return f"{self._required(r.owner,'owner')}/{self._required(r.repository,'repository')}"
    @staticmethod
    def _required(value:str|None,name:str)->str:
        if not value: raise ValueError(f"{name} is required.")
        return value
    def _commit_message(self,path:Path)->str:
        changed=self._git(["status","--short"],path).splitlines(); return f"chore: update {len(changed)} file{'s' if len(changed)!=1 else ''}"
    @staticmethod
    def _needs_confirmation(r:GitHubActionRequest)->bool:
        sensitive = r.action=="merge" or r.action=="branch_delete" or (r.action=="push" and r.force) or (r.action=="repository_create" and r.visibility=="public")
        return sensitive and not r.confirmed
