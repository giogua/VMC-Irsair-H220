"""Season select ("Parametri > Stagione")."""

from __future__ import annotations

from dataclasses import replace

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import IrsapVmcError
from .const import SEASON_OPTIONS
from .coordinator import IrsapVmcConfigEntry, IrsapVmcCoordinator
from .entity import IrsapVmcEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IrsapVmcConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the season select."""
    async_add_entities([IrsapVmcSeason(entry.runtime_data)])


class IrsapVmcSeason(IrsapVmcEntity, SelectEntity):
    """Winter / summer mode."""

    _attr_translation_key = "season"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = list(SEASON_OPTIONS)

    def __init__(self, coordinator: IrsapVmcCoordinator) -> None:
        super().__init__(coordinator, "season")

    @property
    def current_option(self) -> str | None:
        """Current season."""
        value = self.coordinator.data.season
        return next((k for k, v in SEASON_OPTIONS.items() if v == value), None)

    async def async_select_option(self, option: str) -> None:
        """Change season (the client waits 5 s between consecutive changes)."""
        try:
            season = await self.coordinator.client.async_set_season(
                SEASON_OPTIONS[option]
            )
        except IrsapVmcError as err:
            raise HomeAssistantError(f"VMC command failed: {err}") from err
        self.coordinator.async_set_updated_data(
            replace(self.coordinator.data, season=season)
        )
