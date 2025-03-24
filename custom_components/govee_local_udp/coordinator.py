"""Coordinator for the Govee Local UDP integration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import List

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_DISCOVERY_INTERVAL_DEFAULT,
    CONF_FORCED_IP_ADDRESSES,
    CONF_LISTENING_PORT_DEFAULT,
    CONF_MULTICAST_ADDRESS_DEFAULT,
    CONF_TARGET_PORT_DEFAULT,
    CONF_TEMP_ONLY_MODE,
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
        
        self.config_entry = config_entry
        self._device_callbacks = {}
        
        # Check if forced IP addresses were provided
        forced_ips = config_entry.data.get(CONF_FORCED_IP_ADDRESSES, [])
        
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
        
        # Add any forced IPs to the discovery queue
        if forced_ips:
            for ip in forced_ips:
                _LOGGER.debug(f"Adding forced IP to discovery queue: {ip}")
                self._controller.add_device_to_queue(ip)
        
        # Register update listener for configuration changes
        config_entry.async_on_unload(
            config_entry.add_update_listener(self.async_options_updated)
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


    @property
    def devices(self) -> List[GoveeLocalDevice]:
        """Return a list of discovered Govee devices."""
        return self._controller.devices

    async def _async_update_data(self) -> List[GoveeLocalDevice]:
        """Update device data."""
        self._controller.send_update_message()
        return self._controller.devices
        
    @callback
    def register_device_callback(self, device_id: str, callback_fn):
        """Register a callback for configuration changes affecting a device."""
        self._device_callbacks[device_id] = callback_fn
        
    @callback
    def unregister_device_callback(self, device_id: str):
        """Unregister a device callback."""
        if device_id in self._device_callbacks:
            del self._device_callbacks[device_id]
    
    @staticmethod
    async def async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Handle options update."""
        coordinator = hass.data[DOMAIN][entry.entry_id]
        
        # Notify all lights of the options change
        for device_id, callback_fn in coordinator._device_callbacks.items():
            callback_fn(entry.options)