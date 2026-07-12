"""Windows Control Agent API."""
from functools import lru_cache
from fastapi import APIRouter
from backend.app.core.responses import ApiResponse
from backend.app.core.settings import get_settings
from backend.app.domain.windows import WindowsActionRequest, WindowsActionResult
from backend.app.windows.controller import WindowsController
router=APIRouter(prefix="/windows",tags=["windows"])
@lru_cache
def get_windows_controller() -> WindowsController:
    """Return the local Windows Control Agent."""
    return WindowsController(get_settings())
@router.post("/actions",response_model=ApiResponse[WindowsActionResult])
async def execute_action(request: WindowsActionRequest) -> ApiResponse[WindowsActionResult]:
    """Execute a local Windows action with confirmation safeguards."""
    result=get_windows_controller().execute(request.action,request.arguments,request.confirmed)
    return ApiResponse(success=result.success,message=result.message,data=result)
