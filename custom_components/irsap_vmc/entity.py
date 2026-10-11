"""Base entity for the Irsap VMC integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import IrsapVmcError
from .const import DEFAULT_MODEL, DOMAIN, MANUFACTURER
from .coordinator import IrsapVmcCoordinator


class IrsapVmcEntity(CoordinatorEntity[IrsapVmcCoordinator]):
    """All entities of a unit belong to the same device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: IrsapVmcCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.unique_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            name=entry.title,
            manufacturer=MANUFACTURER,
            model=DEFAULT_MODEL,
            configuration_url=coordinator.client.base_url,
        )

    async def _async_command(
        self, func: Callable[..., Awaitable[Any]], *args: Any, menu: bool = False
    ) -> Any:
        """Run a command, translate errors and refresh the state."""
        try:
            result = await func(*args)
        except IrsapVmcError as err:
            raise HomeAssistantError(f"VMC command failed: {err}") from err
        if menu:
            self.coordinator.request_menu_refresh()
        # Immediate refresh (not debounced) so the UI reflects the change.
        await self.coordinator.async_refresh()
        return result
