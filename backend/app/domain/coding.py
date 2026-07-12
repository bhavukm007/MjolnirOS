"""Schemas for safe local coding actions."""
from typing import Any, Literal
from pydantic import BaseModel, Field
CodingAction=Literal["terminal","explain","debug","generate_project","dependencies"]
class CodingRequest(BaseModel):
    action:CodingAction
    project_path:str|None=None
    command:str|None=Field(default=None,max_length=4000)
    code:str|None=Field(default=None,max_length=30000)
    language:Literal["python","cpp","java","javascript","sql"]="python"
    prompt:str|None=Field(default=None,max_length=12000)
    confirmed:bool=False
class CodingResult(BaseModel):
    success:bool
    message:str
    data:dict[str,Any]=Field(default_factory=dict)
    confirmation_required:bool=False
