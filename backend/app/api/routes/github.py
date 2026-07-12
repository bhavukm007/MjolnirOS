"""GitHub Agent API."""
from functools import lru_cache
from fastapi import APIRouter
from backend.app.core.responses import ApiResponse
from backend.app.core.settings import get_settings
from backend.app.domain.github import GitHubActionRequest, GitHubActionResult
from backend.app.github.controller import GitHubController
from backend.app.api.routes.memory import get_memory_store
from backend.app.domain.memory import MemoryCreate
router=APIRouter(prefix="/github",tags=["github"])
@lru_cache
def get_github_controller()->GitHubController: return GitHubController(get_settings())
@router.post("/actions",response_model=ApiResponse[GitHubActionResult])
async def execute_action(request:GitHubActionRequest)->ApiResponse[GitHubActionResult]:
    result=await get_github_controller().execute(request)
    if result.success and request.action in {"clone","repository_create"}:
        get_memory_store().save(MemoryCreate(memory_type="github_repository",content=request.repository or request.remote_url or request.repo_path or "repository",metadata={"action":request.action}))
    return ApiResponse(success=result.success,message=result.message,data=result)
