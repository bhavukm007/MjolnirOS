"""Microsoft Teams plugin lifecycle entry point; credentials remain in the core service."""
def activate() -> str:
    """Confirm isolated plugin activation."""
    return "ready"
