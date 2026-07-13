"""Natural-language recognition for Build and Project Agent commands."""
from backend.app.domain.build import BuildActionRequest

def parse_build_command(command: str) -> BuildActionRequest | None:
    """Map explicit typed or voice build phrases to local actions."""
    text = command.strip().lower().removeprefix("mjolnir,").strip().rstrip(".!?")
    if text == "create a flask project": return BuildActionRequest(action="generate_project", language="flask", project_name="flask_project", path=".")
    if text == "create a fastapi project": return BuildActionRequest(action="generate_project", language="fastapi", project_name="fastapi_project", path=".")
    if text == "install dependencies": return BuildActionRequest(action="install_dependencies", package_manager="pip", path=".")
    if text == "build docker image": return BuildActionRequest(action="docker_build", image="mjolnir-project", path=".")
    if text == "run this project": return BuildActionRequest(action="run_project", language="python", path=".")
    if text == "show docker logs": return BuildActionRequest(action="docker_logs", container="mjolnir-project", path=".")
    return None
