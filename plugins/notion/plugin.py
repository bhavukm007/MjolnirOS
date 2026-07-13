"""Notion productivity plugin lifecycle entry point."""


def activate() -> str:
    """Confirm that the isolated Notion plugin can be activated."""
    return "ready"
