"""End-to-end tests inside Home Assistant (pytest-homeassistant-custom-component)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from aiohttp.test_utils import TestServer
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

sys.path.insert(0, str(Path(__file__).parents[1]))
from fake_vmc import FakeVmc  # noqa: E402

DOMAIN = "irsap_vmc"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations."""
    return


@pytest.fixture
async def fake(socket_enabled):
    vmc = FakeVmc()
    server = TestServer(vmc.app(), host="127.0.0.1")
    await server.start_server()
    vmc.host = f"127.0.0.1:{server.port}"
    yield vmc
    await server.close()


async def _setup(hass: HomeAssistant, fake: FakeVmc, name: str = "VMC") -> str:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: f"http://{fake.host}/", CONF_NAME: name}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY, result
    assert result["data"] == {CONF_HOST: fake.host}
    await hass.async_block_till_done()
    return result["result"].entry_id


async def test_full_flow(hass: HomeAssistant, fake: FakeVmc) -> None:
    entry_id = await _setup(hass, fake)

    # single device holding all entities
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    devices = dr.async_entries_for_config_entry(dev_reg, entry_id)
    assert len(devices) == 1
    entities = er.async_entries_for_config_entry(ent_reg, entry_id)
    assert all(e.device_id == devices[0].id for e in entities)
    assert len(entities) >= 20

    assert hass.states.get("sensor.vmc_outdoor_temperature").state == "22.7"
    assert hass.states.get("sensor.vmc_supply_fan_speed").state == "1798.0"
    assert hass.states.get("select.vmc_season").state == "summer"
    assert hass.states.get("number.vmc_fan_speed").state == "40.0"
    assert hass.states.get("switch.vmc_power").state == "on"
    assert hass.states.get("switch.vmc_boost").state == "off"
    assert hass.states.get("binary_sensor.vmc_bypass").state == "off"
    assert fake.cursor == "home"

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.vmc_fan_speed", "value": 65},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert fake.speed == 65
    assert hass.states.get("number.vmc_fan_speed").state == "65.0"

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.vmc_temperature_set_point", "value": 20.6},
        blocking=True,
    )
    assert fake.setpoint == pytest.approx(20.6)

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.vmc_boost_duration", "value": 15},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.states.get("switch.vmc_boost").state == "on"
    assert hass.states.get("number.vmc_boost_duration").state in ("14", "15")
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.vmc_boost"}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get("switch.vmc_boost").state == "off"

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.vmc_season", "option": "winter"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert fake.season == 0
    assert fake.cursor == "home"
    assert hass.states.get("select.vmc_season").state == "winter"

    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.vmc_power"}, blocking=True
    )
    await hass.async_block_till_done()
    assert not fake.on
    assert hass.states.get("switch.vmc_power").state == "off"
    assert hass.states.get("number.vmc_fan_speed").state == "unknown"


async def test_duplicate_and_second_unit(hass: HomeAssistant, fake: FakeVmc) -> None:
    await _setup(hass, fake)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: fake.host, CONF_NAME: "Altra"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"

    second = FakeVmc()
    server = TestServer(second.app(), host="127.0.0.1")
    await server.start_server()
    second.host = f"127.0.0.1:{server.port}"
    try:
        await _setup(hass, second, name="VMC 2")
        assert hass.states.get("sensor.vmc_2_outdoor_temperature").state == "22.7"
        assert len(dr.async_get(hass).devices) == 2
    finally:
        await server.close()


async def test_cannot_connect(hass: HomeAssistant, socket_enabled) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1:1", CONF_NAME: "VMC"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
