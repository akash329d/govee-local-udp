"""Config flow for Govee Local UDP integration."""

from __future__ import annotations

import asyncio
from contextlib import suppress
import logging
from typing import Any

import voluptuous as vol

from homeassistant.components import network
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.const import CONF_IP_ADDRESS
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.device_registry import format_mac

from .const import (
    CONF_DISCOVERY_INTERVAL_DEFAULT,
    CONF_FORCED_IP_ADDRESS,
    CONF_LISTENING_PORT_DEFAULT,
    CONF_MULTICAST_ADDRESS_DEFAULT,
    CONF_TARGET_PORT_DEFAULT,
    CONF_TEMP_ONLY_MODE,
    DISCOVERY_TIMEOUT,
    DOMAIN,
)
from .protocol.controller import GoveeController

_LOGGER = logging.getLogger(__name__)


async def async_discover_devices(hass: HomeAssistant) -> bool:
    """Discover Govee devices on the network."""
    adapter = await network.async_get_source_ip(hass, network.PUBLIC_TARGET_IP)

    controller = GoveeController(
        loop=hass.loop,
        logger=_LOGGER,
        listening_address=adapter,
        broadcast_address=CONF_MULTICAST_ADDRESS_DEFAULT,
        broadcast_port=CONF_TARGET_PORT_DEFAULT,
        listening_port=CONF_LISTENING_PORT_DEFAULT,
        discovery_enabled=True,
        discovery_interval=5,  # Use a shorter interval for discovery
        update_enabled=True,
    )

    try:
        await controller.start()
    except OSError as ex:
        _LOGGER.error("Failed to start discovery controller: %s", ex)
        return False

    try:
        # Wait for devices to be discovered
        async with asyncio.timeout(DISCOVERY_TIMEOUT):
            while not controller.has_devices:
                await asyncio.sleep(1)
    except TimeoutError:
        _LOGGER.debug("No devices found during discovery")

    devices_found = controller.has_devices
    cleanup_complete = controller.cleanup()
    
    with suppress(TimeoutError):
        await asyncio.wait_for(cleanup_complete.wait(), 1)

    return devices_found


class GoveeLocalProConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Govee Local Pro."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        # Check if already configured
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            # If the user provided a forced IP address, validate it
            if forced_ip := user_input.get(CONF_FORCED_IP_ADDRESS):
                return self.async_create_entry(
                    title="Govee Local UDP",
                    data={CONF_FORCED_IP_ADDRESS: forced_ip},
                    options={CONF_TEMP_ONLY_MODE: False},
                )
            
            # Otherwise proceed with automatic discovery
            return await self.async_step_confirm()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Optional(CONF_FORCED_IP_ADDRESS): cv.string,
            }),
        )

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the confirmation step."""
        if user_input is not None:
            if not await async_discover_devices(self.hass):
                return self.async_abort(reason="no_devices_found")
            
            return self.async_create_entry(
                title="Govee Local UDP",
                data={},
                options={CONF_TEMP_ONLY_MODE: False},
            )

        return self.async_show_form(
            step_id="confirm",
        )
        
    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return GoveeLocalProOptionsFlow(config_entry)


class GoveeLocalProOptionsFlow(OptionsFlow):
    """Handle options for the Govee Local Pro integration."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_TEMP_ONLY_MODE,
                    default=self.config_entry.options.get(CONF_TEMP_ONLY_MODE, False),
                ): bool,
            }),
        )