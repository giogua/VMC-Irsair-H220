"""Buttons: refresh of the menu data."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import IrsapVmcConfigEntry, IrsapVmcCoordinator
from .entity import IrsapVmcEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IrsapVmcConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up buttons."""
    async_add_entities([IrsapVmcRefresh(entry.runtime_data)])


class IrsapVmcRefresh(IrsapVmcEntity, ButtonEntity):
    """Read everything now, including the "Stato" menu and the season."""

    _attr_translation_key = "refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: IrsapVmcCoordinator) -> None:
        super().__init__(coordinator, "refresh")

    async def async_press(self) -> None:
        """Refresh."""
        self.coordinator.request_menu_refresh()
        await self.coordinator.async_request_refresh()
