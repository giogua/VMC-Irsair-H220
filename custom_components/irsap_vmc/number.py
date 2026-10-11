"""Number entities: fan speed, temperature set point, boost duration."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import IrsapVmcConfigEntry, IrsapVmcCoordinator
from .entity import IrsapVmcEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IrsapVmcConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up number entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            IrsapVmcSpeed(coordinator),
            IrsapVmcSetpoint(coordinator),
            IrsapVmcBoostDuration(coordinator),
        ]
    )


class IrsapVmcSpeed(IrsapVmcEntity, NumberEntity):
    """Fan speed (%)."""

    _attr_translation_key = "fan_speed"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: IrsapVmcCoordinator) -> None:
        super().__init__(coordinator, "fan_speed")

    @property
    def native_value(self) -> float | None:
        """Current speed (None while the unit is off)."""
        return self.coordinator.data.speed

    async def async_set_native_value(self, value: float) -> None:
        """Set the speed."""
        await self._async_command(self.coordinator.client.async_set_speed, value)


class IrsapVmcSetpoint(IrsapVmcEntity, NumberEntity):
    """Temperature set point."""

    _attr_translation_key = "temperature_setpoint"
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_min_value = 10
    _attr_native_max_value = 30
    _attr_native_step = 0.2
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: IrsapVmcCoordinator) -> None:
        super().__init__(coordinator, "temperature_setpoint")

    @property
    def native_value(self) -> float | None:
        """Current set point."""
        return self.coordinator.data.setpoint

    async def async_set_native_value(self, value: float) -> None:
        """Set the set point."""
        await self._async_command(self.coordinator.client.async_set_setpoint, value)


class IrsapVmcBoostDuration(IrsapVmcEntity, NumberEntity):
    """Boost: maximum ventilation for N minutes (0 = stop).

    Setting a value starts the boost (if needed) and adjusts the remaining
    time; the state is the remaining time, rounded to the minute.
    """

    _attr_translation_key = "boost_duration"
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_min_value = 0
    _attr_native_max_value = 240
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: IrsapVmcCoordinator) -> None:
        super().__init__(coordinator, "boost_duration")

    @property
    def native_value(self) -> float | None:
        """Remaining boost time in minutes."""
        return round(self.coordinator.data.boost_remaining / 60)

    async def async_set_native_value(self, value: float) -> None:
        """Start/adjust/stop the boost."""
        client = self.coordinator.client
        if value <= 0:
            await self._async_command(client.async_stop_boost)
        else:
            await self._async_command(client.async_start_boost, int(value))
