"""Health domain model."""

from pydantic import BaseModel


class HealthStatus(BaseModel):
    """Backend health and foundational runtime state."""

    status: str
    app_name: str
    environment: str
    version: str
    default_model: str
    modules: list[str]
