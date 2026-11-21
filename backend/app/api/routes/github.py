"""GitHub Agent API."""
from functools import lru_cache
from fastapi import APIRouter, HTTPException
from backend.app.core.responses import ApiResponse
from backend.app.core.settings import get_settings
from backend.app.domain.github import GitHubActionRequest, GitHubActionResult
from backend.app.github.controller import GitHubController
router=APIRouter(prefix="/github",tags=["github"])
@lru_cache
def get_github_controller()->GitHubController: return GitHubController(get_settings())
@router.post("/actions",response_model=ApiResponse[GitHubActionResult])
async def execute_action(request:GitHubActionRequest)->ApiResponse[GitHubActionResult]:
    if request.action not in {"status", "repository_summary"}:
        raise HTTPException(
            status_code=501,
            detail="Git and GitHub mutations are unavailable until they use the approved agent runtime.",
        )
    result=await get_github_controller().execute(request)
    return ApiResponse(success=result.success,message=result.message,data=result)
