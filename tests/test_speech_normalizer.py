import pytest

from backend.app.voice.speech_normalizer import SpeechNormalizer


@pytest.mark.parametrize(
    ("transcript", "expected"),
    (
        ("open calculater", "open calculator"),
        ("open calclator", "open calculator"),
        ("open calculate her", "open calculator"),
        ("open git hub", "open github"),
        ("open chat gpt", "open chat gpt"),
        ("open browserr", "open browser"),
        ("open VS code", "open VS code"),
        ("open Visual Studio Code", "open Visual Studio Code"),
        ("opened chrome", "open chrome"),
    ),
)
def test_normalizes_high_confidence_command_entities(
    transcript: str, expected: str
) -> None:
    assert SpeechNormalizer().normalize(transcript) == expected


@pytest.mark.parametrize(
    "transcript",
    (
        "remember my birthday is July 14",
        "explain transformers",
        "calculate her annual expenses",
        "open UnknownApplicationXYZ",
        "tell me about the Git Hub project",
    ),
)
def test_preserves_free_form_and_unknown_speech(transcript: str) -> None:
    assert SpeechNormalizer().normalize(transcript) == transcript


def test_ambiguous_match_is_not_rewritten() -> None:
    normalizer = SpeechNormalizer({"cart": "cart", "card": "card"})

    assert normalizer.normalize("open car") == "open car"
