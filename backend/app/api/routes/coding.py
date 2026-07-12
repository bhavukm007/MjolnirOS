"""Coding Agent API."""
from fastapi import APIRouter
from backend.app.core.responses import ApiResponse
from backend.app.domain.coding import CodingRequest,CodingResult
from backend.app.coding.controller import CodingController
router=APIRouter(prefix="/coding",tags=["coding"])
@router.post("/actions",response_model=ApiResponse[CodingResult])
async def action(request:CodingRequest)->ApiResponse[CodingResult]:
 result=CodingController().execute(request); return ApiResponse(success=result.success,message=result.message,data=result)
