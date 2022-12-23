"""Main integration"""

from __future__ import annotations
import async_timeout
from datetime import timedelta
from decimal import Decimal
import logging
import voluptuous as vol

from homeassistant.components.media_player import (
    PLATFORM_SCHEMA,
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)

from homeassistant.const import CONF_HOST, CONF_NAME, CONF_UNIQUE_ID
from homeassistant.core import callback, HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.reload import async_setup_reload_service
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from audiocontrol_director_telnet.telnet_client import InputID, OutputID, TelnetClient

from .const import DOMAIN, PLATFORMS

_LOGGER = logging.getLogger("audiocontrol_director")

# Validation of user configuration
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {vol.Optional(CONF_NAME): cv.string, vol.Required(CONF_HOST): cv.string}
)


async def async_setup_entry(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Setup config entry"""
    await async_setup_reload_service(hass, DOMAIN, PLATFORMS)

    coordinator = AudioControlDirectorCoordinator(hass, config)

    await coordinator.async_config_entry_first_refresh()

    system_status = coordinator.data["system_status"]
    if system_status is not None:
        async_add_entities([DirectorDevice(coordinator)])
        async_add_entities(
            OutputDevice(coordinator, output_id)
            for output_id, output in system_status.outputs.items()
        )


class AudioControlDirectorTelnetError(Exception):
    """Represents a telnet communication error with the AudioControl Director M6400/6800"""


class AudioControlDirectorCoordinator(DataUpdateCoordinator):
    """AudioControl Director M6400/M6800 data update coordinator."""

    def __init__(self, hass, config):
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name="AudioControl Director",
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(seconds=2),
        )
        self.config = config
        self.host = hass.data[DOMAIN][config.entry_id]
        # self.telnet_client = TelnetClient(self.host)

    async def _async_update_data(self):
        """Update the data from the Director"""
        system_status = None
        caught_error = None
        try:
            try:
                # Note: asyncio.TimeoutError and aiohttp.ClientError are already
                # handled by the data update coordinator.
                async with async_timeout.timeout(10):
                    system_status = await self.async_fetch_system_status()
            except AudioControlDirectorTelnetError as err:
                raise UpdateFailed(
                    f"Error communicating with AudioControl Director M6400/M6800 telnet interface: {err}"
                ) from err
        except UpdateFailed as err:
            caught_error = err

        return {"system_status": system_status, "error": caught_error}

    async def _connect_telnet_client(self):
        """Create and connect a telnet client"""
        telnet_client = TelnetClient(self.host)
        await telnet_client.async_connect()
        return telnet_client

    async def async_fetch_system_status(self):
        """Get system status."""
        telnet_client = await self._connect_telnet_client()
        system_status = await telnet_client.async_get_system_status()
        telnet_client.disconnect()
        return system_status

    async def async_set_output_power_state(self, output_id: OutputID, state: bool):
        """Set output power status to on (True) or off (False)"""
        telnet_client = await self._connect_telnet_client()
        await telnet_client.async_set_output_power_state(output_id, state)
        telnet_client.disconnect()

    async def async_set_output_volume(self, output_id: OutputID, volume: int):
        """Set output volume"""
        telnet_client = await self._connect_telnet_client()
        await telnet_client.async_set_output_volume(output_id, volume)
        telnet_client.disconnect()

    async def async_set_output_input(self, output_id: OutputID, input_id: InputID):
        """Set output input"""
        telnet_client = await self._connect_telnet_client()
        await telnet_client.async_map_input_to_output(input_id, output_id)
        telnet_client.disconnect()


class DirectorDevice(CoordinatorEntity, MediaPlayerEntity):
    """AudioControl Director M6400/M6800 device."""

    def __init__(self, coordinator):
        """Initialize."""
        super().__init__(coordinator)

        system_status = self.coordinator.data["system_status"]

        self._attr_unique_id = self.coordinator.config.data[CONF_UNIQUE_ID]
        self._attr_device_class = MediaPlayerDeviceClass.RECEIVER
        self._attr_icon = "mdi:audio-video"
        self._attr_name = system_status.name

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._attr_unique_id)},
            manufacturer="AudioControl",
            model="Director M6400/M6800",
            name=self._attr_name,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_available = self.coordinator.data["error"] is None
        self._attr_state = (
            MediaPlayerState.ON
            if self.coordinator.data["error"] is None
            else MediaPlayerState.OFF
        )

        self.async_write_ha_state()


class OutputDevice(CoordinatorEntity, MediaPlayerEntity):
    """AudioControl Director M6400/M6800 output device."""

    _attr_supported_features = (
        MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.SELECT_SOURCE
    )

    _available_inputs = InputID.all()
    _input_id_to_input_name = dict(map(lambda i: (i, i.name), _available_inputs))
    _input_name_to_input_id = {v: k for k, v in _input_id_to_input_name.items()}

    def __init__(self, coordinator, output_id):
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(coordinator)

        output_status = self.coordinator.data["system_status"].outputs[str(output_id)]
        self.output_id = output_id

        self._attr_unique_id = (
            f"{self.coordinator.config.data[CONF_UNIQUE_ID]}_output_{output_id}"
        )
        self._attr_device_class = MediaPlayerDeviceClass.SPEAKER
        self._attr_name = output_status.name
        self._attr_source_list = list(OutputDevice._input_name_to_input_id.keys())

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._attr_unique_id)},
            manufacturer="AudioControl",
            model="Director M6400/M6800",
            name=self._attr_name,
            via_device=(DOMAIN, self.coordinator.config.data[CONF_UNIQUE_ID]),
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data["error"] is not None:
            self._attr_available = False
        else:
            self._attr_available = True

            output_status = self.coordinator.data["system_status"].outputs[
                str(self.output_id)
            ]

            self._attr_state = (
                MediaPlayerState.ON if output_status.is_on else MediaPlayerState.OFF
            )
            self._attr_volume_level = float(
                Decimal(output_status.volume) / Decimal(100)
            )
            self._attr_source = output_status.input_id.name

        self.async_write_ha_state()

    async def async_select_source(self, source: str) -> None:
        """Set input source."""
        if source not in OutputDevice._input_name_to_input_id:
            return

        await self.coordinator.async_set_output_input(
            self.output_id, OutputDevice._input_name_to_input_id[source]
        )
        self._attr_source = source
        self.async_write_ha_state()

    async def async_turn_on(self) -> None:
        """Turn on."""
        await self.coordinator.async_set_output_power_state(self.output_id, True)
        self._attr_state = MediaPlayerState.ON
        self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        """Turn off."""
        await self.coordinator.async_set_output_power_state(self.output_id, False)
        self._attr_state = MediaPlayerState.OFF
        self.async_write_ha_state()

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute (true) or unmute (false)."""
        await self.async_set_volume_level(0 if mute else 0.05)

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        if volume < 0.0 or volume > 100.0:
            return

        int_volume = int(round(Decimal(volume) * Decimal(100)))
        await self.coordinator.async_set_output_volume(self.output_id, int_volume)
        self._attr_volume_level = volume
        self._attr_is_volume_muted = int_volume == 0
        self.async_write_ha_state()

    async def async_volume_up(self) -> None:
        """Volume step up."""
        await self.async_set_volume_level(min(1.0, self._attr_volume_level + 0.05))

    async def async_volume_down(self) -> None:
        """Volume step down."""
        await self.async_set_volume_level(max(0.0, self._attr_volume_level - 0.05))
