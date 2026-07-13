"""Natural language mappings for GitHub Agent commands."""
from backend.app.domain.github import GitHubActionRequest

def parse_github_command(command: str) -> GitHubActionRequest | None:
    """Map supported text and voice phrases to GitHub operations."""
    text = command.strip().lower().removeprefix("mjolnir,").strip().rstrip(".!?")
    if text.startswith("push my "): return GitHubActionRequest(action="push", repo_path=command.strip()[len("Mjolnir, push my "):].strip())
    if text in {"summarize this repository", "summarize repository"}: return GitHubActionRequest(action="repository_summary")
    if text.startswith("create a new branch"): return GitHubActionRequest(action="branch_create")
    if text in {"commit today's work", "commit my work"}: return GitHubActionRequest(action="commit")
    if text == "create an issue": return GitHubActionRequest(action="issue_create")
    if text == "create a pull request": return GitHubActionRequest(action="pull_request_create")
    return None
