"""Shared API response models."""

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

DataT = TypeVar("DataT")


class ApiResponse(BaseModel, Generic[DataT]):
    """Standard JSON response envelope for internal APIs."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    success: bool
    message: str
    data: DataT
