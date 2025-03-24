"""Config flow for Govee Local UDP integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.const import CONF_IP_ADDRESS
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv

from .const import CONF_TEMP_ONLY_MODE, CONF_FORCED_IP_ADDRESS, DOMAIN

_LOGGER = logging.getLogger(__name__)


class GoveeLocalUdpFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Govee Local UDP."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            # Extract the forced_ip_address if provided
            forced_ip = user_input.get(CONF_FORCED_IP_ADDRESS)
            data = {}
            if forced_ip:
                data[CONF_FORCED_IP_ADDRESS] = forced_ip
                
            return self.async_create_entry(
                title="Govee Local UDP",
                data=data,
                options={CONF_TEMP_ONLY_MODE: False},
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Optional(CONF_FORCED_IP_ADDRESS): str,
            }),
            description_placeholders={
                "note": "Discovery will automatically search for Govee devices on your network. If your devices aren't discovered, you can specify the IP address here."
            }
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(OptionsFlow):
    """Handle options for the Govee Local UDP integration."""

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