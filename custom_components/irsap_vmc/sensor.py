"""Sensors for the Irsap VMC integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    EntityCategory,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import VmcData
from .coordinator import IrsapVmcConfigEntry
from .entity import IrsapVmcEntity


@dataclass(frozen=True, kw_only=True)
class IrsapVmcSensorDescription(SensorEntityDescription):
    """Sensor description with a value getter."""

    value_fn: Callable[[VmcData], Any]


def _status(key: str) -> Callable[[VmcData], Any]:
    return lambda d: d.status.get(key)


def _temp(key: str, attr: str) -> IrsapVmcSensorDescription:
    return IrsapVmcSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=lambda d: getattr(d, attr),
    )


SENSORS: tuple[IrsapVmcSensorDescription, ...] = (
    _temp("temp_outdoor", "temp_outdoor"),
    _temp("temp_extract", "temp_extract"),
    _temp("temp_exhaust", "temp_exhaust"),
    _temp("temp_supply", "temp_supply"),
    IrsapVmcSensorDescription(
        key="efficiency",
        translation_key="efficiency",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda d: d.efficiency,
    ),
    IrsapVmcSensorDescription(
        key="boost_remaining",
        translation_key="boost_remaining",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0,
        value_fn=lambda d: round(d.boost_remaining / 60, 1),
    ),
    IrsapVmcSensorDescription(
        key="supply_fan_rpm",
        translation_key="supply_fan_rpm",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_status("supply_fan_rpm"),
    ),
    IrsapVmcSensorDescription(
        key="exhaust_fan_rpm",
        translation_key="exhaust_fan_rpm",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_status("exhaust_fan_rpm"),
    ),
    IrsapVmcSensorDescription(
        key="fan_hours",
        translation_key="fan_hours",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_status("fan_hours"),
    ),
    IrsapVmcSensorDescription(
        key="alarms",
        translation_key="alarms",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.alarm_text or "OK",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IrsapVmcConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors."""
    coordinator = entry.runtime_data
    async_add_entities(IrsapVmcSensor(coordinator, desc) for desc in SENSORS)


class IrsapVmcSensor(IrsapVmcEntity, SensorEntity):
    """A VMC sensor."""

    entity_description: IrsapVmcSensorDescription

    def __init__(self, coordinator, description: IrsapVmcSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        """Return the value."""
        return self.entity_description.value_fn(self.coordinator.data)
