"""The Govee Local UDP integration."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from errno import EADDRINUSE
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_FORCED_IP_ADDRESSES, CONF_TEMP_ONLY_MODE, DISCOVERY_TIMEOUT, DOMAIN
from .coordinator import GoveeLocalUdpCoordinator
from .protocol.controller import LISTENING_PORT
from .services import async_setup_services, async_unload_services

PLATFORMS: list[Platform] = [Platform.LIGHT]

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Govee Local UDP component."""
    await async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Govee Local UDP from a config entry."""
    # Ensure we have an options dictionary with temp_only_mode
    if not entry.options:
        hass.config_entries.async_update_entry(
            entry, options={CONF_TEMP_ONLY_MODE: False}
        )
        
    coordinator = GoveeLocalUdpCoordinator(hass, entry)
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    async def await_cleanup():
        """Wait for cleanup to complete."""
        cleanup_complete = coordinator.cleanup()
        with suppress(TimeoutError):
            await asyncio.wait_for(cleanup_complete.wait(), 1)

    entry.async_on_unload(await_cleanup)

    try:
        await coordinator.start()
    except OSError as ex:
        if ex.errno != EADDRINUSE:
            _LOGGER.error("Start failed, errno: %d", ex.errno)
            return False
        _LOGGER.error("Port %s already in use", LISTENING_PORT)
        raise ConfigEntryNotReady from ex

    await coordinator.async_config_entry_first_refresh()

    # Wait for at least one device to be discovered
    try:
        async with asyncio.timeout(DISCOVERY_TIMEOUT):
            while not coordinator.devices:
                await asyncio.sleep(1)
    except TimeoutError as ex:
        _LOGGER.warning("No devices found during setup. Integration will continue "
                       "looking for devices in the background.")

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
            await async_unload_services(hass)
    return unload_ok