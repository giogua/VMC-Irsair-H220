"""Config flow for the Irsap VMC integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import IrsapVmcClient, IrsapVmcConnectionError, IrsapVmcError
from .const import (
    CONF_MENU_INTERVAL,
    CONF_SCAN_INTERVAL,
    DEFAULT_MENU_INTERVAL,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_MENU_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .coordinator import IrsapVmcConfigEntry

_LOGGER = logging.getLogger(__name__)


def _normalize_host(host: str) -> str:
    host = host.strip().rstrip("/")
    for prefix in ("http://", "https://"):
        if host.lower().startswith(prefix):
            host = host[len(prefix) :]
    return host


class IrsapVmcConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow: one entry per VMC unit."""

    VERSION = 1

    async def _async_validate(self, host: str) -> dict[str, str]:
        client = IrsapVmcClient(host, async_get_clientsession(self.hass))
        try:
            await client.async_validate()
        except IrsapVmcConnectionError:
            return {"base": "cannot_connect"}
        except IrsapVmcError:
            return {"base": "invalid_device"}
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error validating %s", host)
            return {"base": "unknown"}
        return {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the IP address of the unit."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = _normalize_host(user_input[CONF_HOST])
            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()
            errors = await self._async_validate(host)
            if not errors:
                return self.async_create_entry(
                    title=user_input[CONF_NAME], data={CONF_HOST: host}
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_HOST): str,
                        vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                    }
                ),
                user_input,
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the IP address of an existing unit."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = _normalize_host(user_input[CONF_HOST])
            await self.async_set_unique_id(host)
            if host != entry.unique_id:
                self._abort_if_unique_id_configured()
            errors = await self._async_validate(host)
            if not errors:
                return self.async_update_reload_and_abort(
                    entry, unique_id=host, data_updates={CONF_HOST: host}
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {vol.Required(CONF_HOST, default=entry.data[CONF_HOST]): str}
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: IrsapVmcConfigEntry) -> OptionsFlow:
        """Options: polling intervals."""
        return IrsapVmcOptionsFlow()


class IrsapVmcOptionsFlow(OptionsFlow):
    """Polling intervals."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ): vol.All(
                        vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=3600)
                    ),
                    vol.Required(
                        CONF_MENU_INTERVAL,
                        default=options.get(CONF_MENU_INTERVAL, DEFAULT_MENU_INTERVAL),
                    ): vol.All(
                        vol.Coerce(int), vol.Range(min=MIN_MENU_INTERVAL, max=86400)
                    ),
                }
            ),
        )
