"""Tests of the standalone client against the fake unit."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import aiohttp
import pytest
from aiohttp.test_utils import TestServer

sys.path.insert(0, str(Path(__file__).parent))
from fake_vmc import FakeVmc  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "irsap_api", Path(__file__).parents[1] / "custom_components/irsap_vmc/api.py"
)
api = importlib.util.module_from_spec(_spec)
sys.modules["irsap_api"] = api
_spec.loader.exec_module(api)


@pytest.fixture
async def env():
    fake = FakeVmc()
    server = TestServer(fake.app())
    await server.start_server()
    async with aiohttp.ClientSession() as session:
        client = api.IrsapVmcClient(
            f"{server.host}:{server.port}", session, season_change_interval=0.3
        )
        yield fake, client
    await server.close()


def test_parsers():
    assert api.parse_timer("00.09.58") == 598
    assert api.parse_timer("") is None
    assert api.parse_status_line("Te(Esterna)022.7") == ("temp_outdoor", 22.7)
    assert api.parse_status_line("Ti(Ingr.)  023.9") == ("temp_supply", 23.9)
    assert api.parse_status_line("Vent.Ingr.  1798") == ("supply_fan_rpm", 1798.0)
    assert api.parse_status_line("VentI.Remoto Off") == ("supply_fan_remote", False)
    assert api.parse_status_line("Ore Vent.  13644") == ("fan_hours", 13644.0)
    assert api.parse_status_line("Bypass       Off") == ("bypass", False)
    page = api.parse_page(
        '<html><body><img src="l.gif"><a href="cmd_sel0880menu.html">Home</a> &gt; '
        '<a href="cmd_sel0882menu.html">Menu</a> &gt; Parametri<pre>Stagione  Estate</pre>'
        '<form action="menu.html"><input type="image" name="inc0801"></form></body></html>'
    )
    assert page.breadcrumb == "Parametri"
    assert page.links["Home"] == "cmd_sel0880menu.html"


async def test_read_home(env):
    fake, client = env
    data = await client.async_get_data()
    assert data.temp_outdoor == 22.7
    assert data.temp_extract == 23.3
    assert data.temp_supply == 23.8
    assert data.speed == 40
    assert data.setpoint == 22.0
    assert data.is_on is True
    assert data.bypass is False
    assert data.alarm is False
    assert data.boost_remaining == 0
    # reading must not move the menu cursor
    assert fake.cursor == "home"


async def test_menu_data_restores_home(env):
    fake, client = env
    season, status = await client.async_get_menu_data()
    assert season == "Estate"
    assert status["supply_fan_rpm"] == 1798
    assert status["exhaust_fan_rpm"] == 1736
    assert status["fan_hours"] == 13644
    assert status["antifreeze"] is False
    assert status["bypass"] is False
    assert len(status) == 11
    assert fake.cursor == "home"


async def test_menu_from_unexpected_position(env):
    fake, client = env
    fake.cursor = "Stato"
    fake.stato_offset = 2
    season, _ = await client.async_get_menu_data()
    assert season == "Estate"
    assert fake.cursor == "home"


async def test_set_speed(env):
    fake, client = env
    assert await client.async_set_speed(73) == 73
    assert fake.speed == 73
    assert await client.async_set_speed(35) == 35
    # limit: the unit refuses to go below 20
    assert await client.async_set_speed(5) == 20


async def test_set_setpoint(env):
    fake, client = env
    assert await client.async_set_setpoint(19.4) == pytest.approx(19.4)
    assert fake.setpoint == pytest.approx(19.4)
    assert await client.async_set_setpoint(24) == pytest.approx(24.0)


async def test_power(env):
    fake, client = env
    await client.async_toggle_power()
    data = await client.async_get_data()
    assert data.is_on is False
    with pytest.raises(api.IrsapVmcError):
        await client.async_set_speed(50)
    await client.async_toggle_power()
    assert (await client.async_get_data()).is_on is True


async def test_boost(env):
    fake, client = env
    remaining = await client.async_start_boost(25)
    assert round(remaining / 60) == 25
    remaining = await client.async_start_boost(3)
    assert round(remaining / 60) == 3
    data = await client.async_get_data()
    assert data.boost_active
    await client.async_stop_boost()
    assert not (await client.async_get_data()).boost_active
    remaining = await client.async_start_boost()
    assert round(remaining / 60) == 10


async def test_season(env):
    fake, client = env
    assert await client.async_set_season("Inverno") == "Inverno"
    assert fake.season == 0
    assert fake.cursor == "home"
    assert await client.async_set_season("Estate") == "Estate"
    assert fake.season == 1
    assert fake.season_changes[1] - fake.season_changes[0] >= 0.3
    # no-op when already set
    assert await client.async_set_season("Estate") == "Estate"
    assert len(fake.season_changes) == 2
