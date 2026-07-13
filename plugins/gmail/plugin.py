"""Gmail productivity plugin lifecycle entry point."""


def activate() -> str:
    """Confirm that the isolated Gmail plugin can be activated."""
    return "ready"
