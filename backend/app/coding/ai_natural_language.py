"""Natural-language recognition for local AI coding tasks."""

from __future__ import annotations

from backend.app.domain.ai_coding import CodingAiRequest


def parse_ai_coding_command(command: str) -> CodingAiRequest | None:
    """Map explicit coding-assistance phrases to local AI actions."""
    original = command.strip()
    text = original.lower().removeprefix("mjolnir,").strip().rstrip(".!?")
    mappings = (
        ("explain this compiler error", "compile_analysis"),
        ("explain this error", "error_explanation"),
        ("debug this error", "debug"),
        ("explain this code", "explain"),
        ("explain this sql query", "explain"),
        ("generate a flask application", "generate"),
        ("generate a rest api", "generate"),
        ("suggest fixes", "fix_suggestions"),
    )
    for phrase, action in mappings:
        if text.startswith(phrase):
            language = "python" if "flask" in text else "sql" if "sql" in text else None
            remainder = original[original.lower().find(phrase) + len(phrase):].strip(" .!?:")
            return CodingAiRequest(action=action, content=remainder or original, language=language)
    return None
