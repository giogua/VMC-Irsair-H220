"""Constants for the Irsap VMC integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "irsap_vmc"

MANUFACTURER: Final = "Irsap"
DEFAULT_MODEL: Final = "Irsair H 220"
DEFAULT_NAME: Final = "VMC"

CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_MENU_INTERVAL: Final = "menu_interval"

DEFAULT_SCAN_INTERVAL: Final = 30  # seconds, home page widgets
DEFAULT_MENU_INTERVAL: Final = 300  # seconds, "Stato" list and season
MIN_SCAN_INTERVAL: Final = 10
MIN_MENU_INTERVAL: Final = 60

SEASON_OPTIONS: Final = {"winter": "Inverno", "summer": "Estate"}
