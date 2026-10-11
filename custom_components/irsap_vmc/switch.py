"""Switches: unit power and boost."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import IrsapVmcConfigEntry, IrsapVmcCoordinator
from .entity import IrsapVmcEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IrsapVmcConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up switches."""
    coordinator = entry.runtime_data
    async_add_entities([IrsapVmcPower(coordinator), IrsapVmcBoost(coordinator)])


class IrsapVmcPower(IrsapVmcEntity, SwitchEntity):
    """Unit on/off (the on/off button of the speed widget)."""

    _attr_translation_key = "power"

    def __init__(self, coordinator: IrsapVmcCoordinator) -> None:
        super().__init__(coordinator, "power")

    @property
    def is_on(self) -> bool | None:
        """Unit on."""
        return self.coordinator.data.is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on (the device only has a toggle)."""
        if self.is_on is not True:
            await self._async_command(self.coordinator.client.async_toggle_power)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off."""
        if self.is_on is not False:
            await self._async_command(self.coordinator.client.async_toggle_power)


class IrsapVmcBoost(IrsapVmcEntity, SwitchEntity):
    """Boost: maximum ventilation, 10 minutes by default."""

    _attr_translation_key = "boost"

    def __init__(self, coordinator: IrsapVmcCoordinator) -> None:
        super().__init__(coordinator, "boost")

    @property
    def is_on(self) -> bool:
        """Boost running."""
        return self.coordinator.data.boost_active

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start the boost (10 minutes, adjustable with the duration entity)."""
        await self._async_command(self.coordinator.client.async_start_boost)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop the boost."""
        await self._async_command(self.coordinator.client.async_stop_boost)
