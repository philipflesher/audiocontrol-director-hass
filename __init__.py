"""AudioControl Director M6400/M6800 Integration"""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.reload import async_setup_reload_service

from audiocontrol_director_telnet.telnet_client import TelnetClient

from .const import DOMAIN, PLATFORMS


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Setup config entry"""
    await async_setup_reload_service(hass, DOMAIN, PLATFORMS)

    host: str = entry.data["host"]

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = host

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload config entry"""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
