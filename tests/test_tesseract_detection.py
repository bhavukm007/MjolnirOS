import pytest
from PIL import Image

from backend.app.core.settings import AppSettings
from backend.app.vision.vision_service import VisionService


def test_explicit_tesseract_configuration_takes_precedence(monkeypatch) -> None:
    configured = r"C:\tools\tesseract.exe"
    monkeypatch.setattr(
        VisionService,
        "_existing_command",
        staticmethod(lambda command: configured if command == configured else None),
    )
    monkeypatch.setattr(
        "backend.app.vision.vision_service.shutil.which",
        lambda command: r"C:\path\tesseract.exe",
    )

    result = VisionService.detect_tesseract_command(
        AppSettings(tesseract_command=configured)
    )

    assert result == configured


def test_tesseract_detection_uses_path_when_not_configured(monkeypatch) -> None:
    path_command = r"C:\path\tesseract.exe"
    monkeypatch.setattr(
        "backend.app.vision.vision_service.shutil.which",
        lambda command: path_command,
    )

    assert VisionService.detect_tesseract_command(AppSettings()) == path_command


def test_tesseract_detection_uses_common_windows_install_root(
    tmp_path, monkeypatch
) -> None:
    executable = tmp_path / "Tesseract-OCR" / "tesseract.exe"
    executable.parent.mkdir()
    executable.touch()
    monkeypatch.setattr(
        "backend.app.vision.vision_service.shutil.which", lambda command: None
    )
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    monkeypatch.delenv("ProgramFiles(x86)", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    assert VisionService.detect_tesseract_command(AppSettings()) == str(executable)


def test_missing_tesseract_returns_installation_guidance(monkeypatch) -> None:
    monkeypatch.setattr(
        VisionService,
        "detect_tesseract_command",
        staticmethod(lambda settings: None),
    )
    service = VisionService(AppSettings())

    with pytest.raises(Exception, match="Tesseract OCR is not installed"):
        service.analyze_image(Image.new("RGB", (10, 10), "white"))
