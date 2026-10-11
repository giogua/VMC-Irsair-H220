"""Data update coordinator for the Irsap VMC integration."""

from __future__ import annotations

import logging
import time
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import IrsapVmcClient, IrsapVmcConnectionError, IrsapVmcError, VmcData
from .const import (
    CONF_MENU_INTERVAL,
    CONF_SCAN_INTERVAL,
    DEFAULT_MENU_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

type IrsapVmcConfigEntry = ConfigEntry[IrsapVmcCoordinator]


class IrsapVmcCoordinator(DataUpdateCoordinator[VmcData]):
    """Polls one unit.

    Home page widgets are read at every update (no side effects); the menu
    pages (status list "Stato" and season "Parametri > Stagione") move the unit's menu cursor,
    so they are read less often.
    """

    config_entry: IrsapVmcConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: IrsapVmcConfigEntry, client: IrsapVmcClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self.client = client
        self._menu_interval = entry.options.get(
            CONF_MENU_INTERVAL, DEFAULT_MENU_INTERVAL
        )
        self._last_menu_read = 0.0
        self._force_menu = True

    def request_menu_refresh(self) -> None:
        """Read the menu pages at the next update."""
        self._force_menu = True

    async def _async_update_data(self) -> VmcData:
        try:
            data = await self.client.async_get_data(self.data)
        except IrsapVmcConnectionError as err:
            raise UpdateFailed(f"Cannot reach the VMC: {err}") from err
        except IrsapVmcError as err:
            raise UpdateFailed(str(err)) from err

        if (
            self._force_menu
            or time.monotonic() - self._last_menu_read >= self._menu_interval
        ):
            try:
                season, status = await self.client.async_get_menu_data()
            except IrsapVmcError as err:
                _LOGGER.warning("Unable to read the VMC menu pages: %s", err)
            else:
                data.season = season
                data.status = status
                data.status_updated = time.time()
                self._last_menu_read = time.monotonic()
                self._force_menu = False
        return data
