from pathlib import Path

from backend.app.ai.intent_router import Intent, IntentRouter
from backend.app.domain.ai import ChatMessage
from backend.app.domain.memory import MemoryCategory
from backend.app.memory.context_engine import ContextEngine
from backend.app.memory.service import MemoryService
from backend.app.memory.store import MemoryStore


def memory_service(tmp_path: Path) -> MemoryService:
    return MemoryService(MemoryStore(tmp_path / "memory.db", tmp_path / "chroma"))


def test_profile_and_preference_survive_store_restart(tmp_path: Path) -> None:
    service = memory_service(tmp_path)
    assert "Bhavuk Mahajan" in service.handle_command("My name is Bhavuk Mahajan.")
    assert "VS Code" in service.handle_command("Remember my favourite IDE is VS Code.")

    restarted = memory_service(tmp_path)
    assert restarted.handle_command("What's my name?") == (
        "Your name is Bhavuk Mahajan, but I'll continue calling you Boss."
    )
    assert "VS Code" in restarted.handle_command("What's my favourite IDE?")


def test_importance_policy_does_not_promote_transient_emotion(tmp_path: Path) -> None:
    service = memory_service(tmp_path)
    assert service.ingest("My dad is angry.") == []
    assert service.store.list(category=MemoryCategory.LONG_TERM) == []


def test_context_includes_profile_recent_turns_and_tasks(tmp_path: Path) -> None:
    service = memory_service(tmp_path)
    service.handle_command("My name is Bhavuk Mahajan")
    service.handle_command("Remember my favourite IDE is VS Code")
    service.handle_command("Remind me to submit the report")
    service.record_conversation("user", "My dad is angry.")
    service.record_conversation("assistant", "What happened, Boss?")
    engine = ContextEngine(service.store)

    prompt = engine.prompt("Which editor do I like?")
    history = engine.history([ChatMessage(role="user", content="Because I failed my exam.")])

    assert "Bhavuk Mahajan" in prompt
    assert "VS Code" in prompt
    assert "submit the report" in prompt
    assert [item.content for item in history][-3:] == [
        "My dad is angry.", "What happened, Boss?", "Because I failed my exam."
    ]


def test_forget_is_soft_delete(tmp_path: Path) -> None:
    service = memory_service(tmp_path)
    service.handle_command("Remember my favourite IDE is VS Code")
    assert "forgot 1" in service.handle_command("Forget favourite IDE").lower()
    assert "don't have" in service.handle_command("What's my favourite IDE?")


def test_intent_router_strips_inline_wake_phrase() -> None:
    router = IntentRouter("Mjolnir")
    routed = router.classify("Meonir open Chrome")
    assert routed.intent is Intent.APPLICATION_LAUNCH
    assert routed.message == "open Chrome"
    assert router.classify("What's my name?").intent is Intent.MEMORY_QUERY
    assert router.classify("What's up?").intent is Intent.GREETING
