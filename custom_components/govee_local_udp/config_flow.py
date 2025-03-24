"""Config flow for Govee Local UDP integration."""

from __future__ import annotations

import logging
import ipaddress
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.const import CONF_IP_ADDRESS
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv

from .const import CONF_TEMP_ONLY_MODE, CONF_FORCED_IP_ADDRESSES, DOMAIN

_LOGGER = logging.getLogger(__name__)


class GoveeLocalUdpFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Govee Local UDP."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        errors = {}

        if user_input is not None:
            # Extract and validate the forced IP addresses if provided
            ip_addresses = []
            if forced_ips := user_input.get(CONF_FORCED_IP_ADDRESSES):
                for ip in [ip.strip() for ip in forced_ips.split(",")]:
                    if ip:
                        try:
                            ipaddress.ip_address(ip)
                            ip_addresses.append(ip)
                        except ValueError:
                            errors[CONF_FORCED_IP_ADDRESSES] = "invalid_ip_address"
            
            # If no errors, create the config entry
            if not errors:
                data = {}
                if ip_addresses:
                    data[CONF_FORCED_IP_ADDRESSES] = ip_addresses
                    
                return self.async_create_entry(
                    title="Govee Local UDP",
                    data=data,
                    options={CONF_TEMP_ONLY_MODE: False},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Optional(CONF_FORCED_IP_ADDRESSES): str,
            }),
            errors=errors,
            description_placeholders={
                "note": "Discovery will automatically search for Govee devices on your network. If your devices aren't discovered, you can specify their IP addresses here (comma-separated, e.g., 192.168.1.100, 192.168.1.101)."
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
        errors = {}

        if user_input is not None:
            # Extract and validate the forced IP addresses if provided
            ip_addresses = []
            if forced_ips := user_input.get(CONF_FORCED_IP_ADDRESSES):
                for ip in [ip.strip() for ip in forced_ips.split(",")]:
                    if ip:
                        try:
                            ipaddress.ip_address(ip)
                            ip_addresses.append(ip)
                        except ValueError:
                            errors[CONF_FORCED_IP_ADDRESSES] = "invalid_ip_address"
            
            # If no errors, update the config entry
            if not errors:
                data = {**user_input}
                if ip_addresses:
                    data[CONF_FORCED_IP_ADDRESSES] = ip_addresses
                else:
                    data.pop(CONF_FORCED_IP_ADDRESSES, None)
                    
                return self.async_create_entry(title="", data=data)

        # Get current forced IP addresses as a comma-separated string
        current_ips = self.config_entry.data.get(CONF_FORCED_IP_ADDRESSES, [])
        ip_string = ", ".join(current_ips) if current_ips else ""

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_TEMP_ONLY_MODE,
                    default=self.config_entry.options.get(CONF_TEMP_ONLY_MODE, False),
                ): bool,
                vol.Optional(
                    CONF_FORCED_IP_ADDRESSES,
                    default=ip_string,
                ): str,
            }),
            errors=errors,
        )