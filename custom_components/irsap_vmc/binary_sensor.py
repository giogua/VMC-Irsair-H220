"""Binary sensors for the Irsap VMC integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import VmcData
from .coordinator import IrsapVmcConfigEntry
from .entity import IrsapVmcEntity


@dataclass(frozen=True, kw_only=True)
class IrsapVmcBinaryDescription(BinarySensorEntityDescription):
    """Binary sensor description with a value getter."""

    value_fn: Callable[[VmcData], bool | None]


def _status(key: str) -> Callable[[VmcData], bool | None]:
    def _get(d: VmcData) -> bool | None:
        value = d.status.get(key)
        return value if isinstance(value, bool) else None

    return _get


BINARY_SENSORS: tuple[IrsapVmcBinaryDescription, ...] = (
    IrsapVmcBinaryDescription(
        key="bypass",
        translation_key="bypass",
        value_fn=lambda d: d.bypass,
    ),
    IrsapVmcBinaryDescription(
        key="alarm",
        translation_key="alarm",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda d: d.alarm,
    ),
    IrsapVmcBinaryDescription(
        key="antifreeze",
        translation_key="antifreeze",
        value_fn=_status("antifreeze"),
    ),
    IrsapVmcBinaryDescription(
        key="supply_fan_remote",
        translation_key="supply_fan_remote",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_status("supply_fan_remote"),
    ),
    IrsapVmcBinaryDescription(
        key="exhaust_fan_remote",
        translation_key="exhaust_fan_remote",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_status("exhaust_fan_remote"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IrsapVmcConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(IrsapVmcBinarySensor(coordinator, d) for d in BINARY_SENSORS)


class IrsapVmcBinarySensor(IrsapVmcEntity, BinarySensorEntity):
    """A VMC binary sensor."""

    entity_description: IrsapVmcBinaryDescription

    def __init__(self, coordinator, description: IrsapVmcBinaryDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return the state."""
        return self.entity_description.value_fn(self.coordinator.data)
