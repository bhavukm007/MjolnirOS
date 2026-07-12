"""Natural-language mappings for local Coding Agent actions."""
from backend.app.domain.coding import CodingRequest
def parse_coding_command(command: str) -> CodingRequest | None:
    """Map supported text and voice phrases to coding requests."""
    text=command.strip().lower().removeprefix("mjolnir,").strip().rstrip(".!?")
    if text.startswith("explain this code"): return CodingRequest(action="explain",code=command)
    if text.startswith("debug this error"): return CodingRequest(action="debug",prompt=command)
    if text.startswith("run my "): return CodingRequest(action="terminal",command=command.split("run my ",1)[1])
    if text.startswith("generate "): return CodingRequest(action="generate_project",prompt=command.split("generate ",1)[1])
    if text.startswith("install dependencies"): return CodingRequest(action="dependencies")
    return None
