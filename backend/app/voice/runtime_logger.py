"""Dedicated structured logger for the continuous voice runtime."""

from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger("mjolniros.voice")


def state(name: str, **details: Any) -> None:
    """Log a stable, searchable voice state transition."""
    logger.info(
        "VOICE_STATE: %s",
        name,
        extra={"event": "voice_state", "voice_state": name, **details},
    )

