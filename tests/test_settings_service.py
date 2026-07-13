"""Coverage for persisted, non-secret settings."""

from backend.app.core.settings import AppSettings
from backend.app.domain.user_settings import UserSettingsUpdate
from backend.app.settings.settings_service import SettingsService


def test_user_settings_update_persists(tmp_path) -> None:
    settings = AppSettings(settings_storage_directory=tmp_path / "settings")
    service = SettingsService(settings)
    updated = service.update(
        UserSettingsUpdate(theme="light", start_with_windows=True, model="llama3.2")
    )
    assert updated.theme == "light"
    assert SettingsService(settings).get().model == "llama3.2"
