import pytest

from backend.app.ai.capability_router import Capability, CapabilityRouter
from backend.app.ai.intent_router import IntentRouter
from backend.app.ai.text_normalizer import TextNormalizer


@pytest.mark.parametrize(
    ("text", "expected"),
    (
        ("opn gmail", "open gmail"),
        ("opne chrome", "open chrome"),
        ("opn calculatr", "open calculator"),
        ("remeber my bithday", "remember my birthday"),
        ("explin transformers", "explain transformers"),
        ("opn reddt", "open reddit"),
        ("whts the weather today", "whats the weather today"),
    ),
)
def test_corrects_high_confidence_routing_typos(text: str, expected: str) -> None:
    assert TextNormalizer().normalize(text) == expected


@pytest.mark.parametrize(
    "text",
    (
        "Write Python code that opens a file",
        "Tell me about Reddit communities",
        "calculate the transformer dimensions",
        "open UnknownApplicationXYZ",
        "remember that my project is called Calculatr",
    ),
)
def test_preserves_unrelated_and_unknown_text(text: str) -> None:
    assert TextNormalizer().normalize(text) == text


def test_normalized_examples_keep_deterministic_routing() -> None:
    installed = {"chrome", "calculator"}
    capability_router = CapabilityRouter(
        application_resolver=lambda name: name if name.lower() in installed else None
    )
    normalizer = TextNormalizer()
    intent_router = IntentRouter("Mjolnir")

    expected = {
        "opn gmail": Capability.BROWSER,
        "opne chrome": Capability.WINDOWS,
        "opn calculatr": Capability.WINDOWS,
        "remeber my birthday": Capability.MEMORY,
        "explin transformers": Capability.LLM,
        "whts the weather today": Capability.LIVE_INFORMATION,
    }
    for text, capability in expected.items():
        routed = intent_router.classify(normalizer.normalize(text))
        assert capability_router.route(routed).capability is capability
