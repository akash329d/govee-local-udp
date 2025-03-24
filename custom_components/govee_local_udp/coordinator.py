"""Coordinator for the Govee Local UDP integration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any, List, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_DISCOVERY_INTERVAL_DEFAULT,
    CONF_LISTENING_PORT_DEFAULT,
    CONF_MULTICAST_ADDRESS_DEFAULT,
    CONF_TARGET_PORT_DEFAULT,
    DOMAIN,
    SCAN_INTERVAL,
)
from .protocol.controller import GoveeController, GoveeLocalDevice

_LOGGER = logging.getLogger(__name__)


class GoveeLocalUdpCoordinator(DataUpdateCoordinator[List[GoveeLocalDevice]]):
    """Coordinator for Govee Local UDP integration."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass=hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )

        self._controller = GoveeController(
            loop=hass.loop,
            logger=_LOGGER,
            broadcast_address=CONF_MULTICAST_ADDRESS_DEFAULT,
            broadcast_port=CONF_TARGET_PORT_DEFAULT,
            listening_port=CONF_LISTENING_PORT_DEFAULT,
            discovery_enabled=True,
            discovery_interval=CONF_DISCOVERY_INTERVAL_DEFAULT,
            discovered_callback=None,
            update_enabled=True,
        )

    async def start(self) -> None:
        """Start the coordinator."""
        await self._controller.start()

    async def set_discovery_callback(
        self, callback: Callable[[GoveeLocalDevice, bool], bool]
    ) -> None:
        """Set discovery callback for automatic Govee light discovery."""
        self._controller.set_device_discovered_callback(callback)

    def cleanup(self) -> asyncio.Event:
        """Stop and cleanup the coordinator."""
        return self._controller.cleanup()

    async def turn_on(self, device: GoveeLocalDevice) -> None:
        """Turn on the light."""
        await device.turn_on()

    async def turn_off(self, device: GoveeLocalDevice) -> None:
        """Turn off the light."""
        await device.turn_off()

    async def set_brightness(self, device: GoveeLocalDevice, brightness: int) -> None:
        """Set light brightness."""
        await device.set_brightness(brightness)

    async def set_rgb_color(
        self, device: GoveeLocalDevice, red: int, green: int, blue: int
    ) -> None:
        """Set light RGB color."""
        await device.set_rgb_color(red, green, blue)

    async def set_temperature(self, device: GoveeLocalDevice, temperature: int) -> None:
        """Set light color in kelvin."""
        await device.set_temperature(temperature)

    async def set_scene(self, device: GoveeLocalDevice, scene: str) -> None:
        """Set light scene."""
        await device.set_scene(scene)

    @property
    def devices(self) -> List[GoveeLocalDevice]:
        """Return a list of discovered Govee devices."""
        return self._controller.devices

    async def _async_update_data(self) -> List[GoveeLocalDevice]:
        """Update device data."""
        self._controller.send_update_message()
        return self._controller.devices