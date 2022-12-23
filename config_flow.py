"""Config flow"""

from __future__ import annotations

import logging

import voluptuous as vol

import re

from homeassistant import config_entries, exceptions
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_UNIQUE_ID
from homeassistant.core import HomeAssistant

from audiocontrol_director_telnet.telnet_client import TelnetClient

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

INIT_DATA_SCHEMA = vol.Schema({vol.Required(CONF_HOST): str})

IDENTIFIERS_DATA_SCHEMA = vol.Schema(
    {vol.Required(CONF_UNIQUE_ID): str, vol.Required(CONF_NAME): str}
)


def is_valid_hostname(hostname):
    """Validate hostname string"""
    if len(hostname) > 255:
        return False
    if hostname[-1] == ".":
        hostname = hostname[:-1]  # strip exactly one dot from the right, if present
    allowed = re.compile(r"(?!-)[A-Z\d-]{1,63}(?<!-)$", re.IGNORECASE)
    return all(allowed.match(x) for x in hostname.split("."))


async def async_validate_host(hass: HomeAssistant, data: dict):
    """Validate the user input, allowing us to connect.
    Data has the keys from INIT_DATA_SCHEMA with values provided by the user.
    """
    # Validate the data can be used to set up a connection.
    if not is_valid_hostname(data[CONF_HOST]):
        raise InvalidHost

    telnet_client = TelnetClient(data[CONF_HOST])

    # Ensure connection succeeds and sample command works
    try:
        await telnet_client.async_connect()
        await telnet_client.async_get_system_status()
    except Exception as exc:
        raise CannotConnect from exc


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for AudioControl Director M6400/M6800."""

    VERSION = 1
    # Pick one of the available connection classes in homeassistant/config_entries.py
    # This tells HA if it should be asking for updates, or it'll be notified of updates
    # automatically.
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    def __init__(self):
        self._host = None

    async def async_step_user(self, user_input=None):
        """Start the user config flow."""
        return await self.async_step_init()

    async def async_step_init(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            try:
                await async_validate_host(self.hass, user_input)
                self._host = user_input[CONF_HOST]
                return await self.async_step_identifiers()
            except CannotConnect:
                errors[CONF_HOST] = "cannot_connect"
            except InvalidHost:
                errors[CONF_HOST] = "invalid_host"
            except:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
                raise

        return self.async_show_form(
            step_id="init", data_schema=INIT_DATA_SCHEMA, errors=errors
        )

    async def async_step_identifiers(self, user_input=None):
        """Handle the identifiers step."""
        errors = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_UNIQUE_ID])
            self._abort_if_unique_id_configured()

            entry_data = {
                "host": self._host,
                "unique_id": user_input[CONF_UNIQUE_ID],
                "name": user_input[CONF_NAME],
            }

            return self.async_create_entry(title=entry_data["name"], data=entry_data)

        return self.async_show_form(
            step_id="identifiers", data_schema=IDENTIFIERS_DATA_SCHEMA, errors=errors
        )


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidHost(exceptions.HomeAssistantError):
    """Error to indicate there is an invalid hostname."""
