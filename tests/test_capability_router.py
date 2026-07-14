from backend.app.ai.capability_router import (
    Capability,
    CapabilityRouter,
    CapabilityStatus,
    RoutingContext,
)
from backend.app.ai.intent_router import IntentRouter


def route(message: str):
    return CapabilityRouter().route(IntentRouter("Mjolnir").classify(message))


def test_browser_navigation_precedes_generic_application_launch() -> None:
    assert route("Open Gmail").capability is Capability.BROWSER
    assert route("Open Reddit").capability is Capability.BROWSER


def test_windows_application_launch() -> None:
    assert route("Open Chrome").capability is Capability.WINDOWS
    assert route("Open Calculator").capability is Capability.WINDOWS


def test_general_conversation_uses_llm_fallback() -> None:
    decision = route("Explain transformers")
    assert decision.capability is Capability.LLM
    assert decision.status is CapabilityStatus.FALLBACK


def test_live_information_never_falls_through_to_llm() -> None:
    messages = (
        "How is the weather today?",
        "What's the latest AI news?",
        "Who won yesterday's IPL match?",
        "What time is it in Tokyo?",
        "Convert 100 USD to INR.",
    )
    for message in messages:
        decision = route(message)
        assert decision.capability is Capability.LIVE_INFORMATION
        assert decision.status is CapabilityStatus.NOT_IMPLEMENTED


def test_unknown_request_has_explicit_fallback_decision() -> None:
    decision = route("flibbertigibbet")
    assert decision.capability is Capability.LLM
    assert decision.handler == "ollama_fallback"


def test_memory_and_planner_routes_are_preserved() -> None:
    assert route("Remember my birthday is 1 January").capability is Capability.MEMORY
    assert route("Automate my morning routine").capability is Capability.PLANNER


def test_browser_profile_context_is_forward_compatible() -> None:
    routed = IntentRouter("Mjolnir").classify("Open Gmail")
    decision = CapabilityRouter().route(routed, RoutingContext(preferred_browser_profile="primary"))
    assert decision.capability is Capability.BROWSER
    assert decision.context.preferred_browser_profile == "primary"
