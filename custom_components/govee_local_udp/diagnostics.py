"""Diagnostics support for the Govee Local UDP integration."""

from __future__ import annotations

from typing import Any, Dict

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_IP_ADDRESS
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import GoveeLocalUdpCoordinator
from .protocol.controller import GoveeLocalDevice

# Keys to redact from the diagnostics data
TO_REDACT = {CONF_IP_ADDRESS, "ip"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> Dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: GoveeLocalUdpCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Convert device objects to dictionaries
    devices_data = []
    for device in coordinator.devices:
        devices_data.append({
            "device_id": device.device_id,
            "model": device.model,
            "ip": device.ip,
            "ble_hardware_version": device.ble_hardware_version,
            "ble_software_version": device.ble_software_version,
            "wifi_hardware_version": device.wifi_hardware_version,
            "wifi_software_version": device.wifi_software_version,
            "on": device.on,
            "brightness": device.brightness,
            "rgb_color": device.rgb_color,
            "temperature_color": device.temperature_color,
            "capabilities": {
                "features": int(device.capabilities.features),
                "has_brightness": bool(device.capabilities.features & 1),
                "has_color_rgb": bool(device.capabilities.features & 2),
                "has_color_temperature": bool(device.capabilities.features & 4),
                "has_scenes": bool(device.capabilities.features & 8),
                "has_segments": bool(device.capabilities.features & 16),
                "scenes_count": len(device.capabilities.scenes),
                "segments_count": len(device.capabilities.segments),
            },
        })

    diagnostics_data = {
        "config_entry": {
            "title": entry.title,
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "devices": devices_data,
    }

    return async_redact_data(diagnostics_data, TO_REDACT)