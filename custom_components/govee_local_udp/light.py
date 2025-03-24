"""Light platform for the Govee Local UDP integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
    filter_supported_color_modes,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_TEMP_ONLY_MODE, DOMAIN, MANUFACTURER
from .coordinator import GoveeLocalUdpCoordinator
from .protocol.controller import GoveeLocalDevice
from .protocol.message import GoveeLightFeatures

_LOGGER = logging.getLogger(__name__)



async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Govee lights from config entry."""
    coordinator: GoveeLocalUdpCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    # Add all current devices
    async_add_entities(
        GoveeLocalUdpLight(coordinator, device) for device in coordinator.devices
    )

    # Register callback for future device discovery
    @callback
    def device_discovery(device: GoveeLocalDevice, is_new: bool) -> bool:
        """Handle discovery of a new device."""
        if is_new:
            async_add_entities([GoveeLocalUdpLight(coordinator, device)])
        return True

    await coordinator.set_discovery_callback(device_discovery)


class GoveeLocalUdpLight(CoordinatorEntity[GoveeLocalUdpCoordinator], LightEntity):
    """Representation of a Govee light."""

    _attr_has_entity_name = True
    _attr_name = None
    _supported_color_modes: set[ColorMode]
    _fixed_color_mode: ColorMode | None = None

    def __init__(
        self,
        coordinator: GoveeLocalUdpCoordinator,
        device: GoveeLocalDevice,
    ) -> None:
        """Initialize a Govee light."""
        super().__init__(coordinator)
        self._device = device
        device.add_update_callback(self._device_updated)

        # Entity attributes
        self._attr_unique_id = f"{DOMAIN}_{device.device_id}"
        
        # Register for coordinator options updates
        coordinator.register_device_callback(device.device_id, self._handle_options_update)

        # Get device capabilities
        self._capabilities = device.capabilities
        self._device_id = device.device_id
        self._model = device.model
        
        # Check if temperature-only mode is enabled globally
        self._temperature_only_mode = coordinator.config_entry.options.get(CONF_TEMP_ONLY_MODE, False)

        # Set up device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.device_id)},
            name=f"Govee {device.model}",
            manufacturer=MANUFACTURER,
            model=device.model,
        )
        
        # Add version information if available
        ble_sw = getattr(device, "ble_software_version", "")
        wifi_sw = getattr(device, "wifi_software_version", "")
        if ble_sw or wifi_sw:
            self._attr_device_info["sw_version"] = f"{ble_sw} / {wifi_sw}"

        # Build available color modes based on current options
        self._setup_color_modes()
        
    def _setup_color_modes(self) -> None:
        """Set up supported color modes based on capabilities and current options."""
        # For simplicity, all Govee lights support at least brightness
        color_modes = {ColorMode.ONOFF, ColorMode.BRIGHTNESS}
            
        # Only add RGB mode if not in temperature-only mode
        if (GoveeLightFeatures.COLOR_RGB & self._capabilities.features) and not self._temperature_only_mode:
            color_modes.add(ColorMode.RGB)
            
        if GoveeLightFeatures.COLOR_KELVIN_TEMPERATURE & self._capabilities.features:
            color_modes.add(ColorMode.COLOR_TEMP)
            self._attr_min_color_temp_kelvin = self._capabilities.min_kelvin
            self._attr_max_color_temp_kelvin = self._capabilities.max_kelvin
        
        # Filter and set the supported color modes
        self._supported_color_modes = filter_supported_color_modes(color_modes)
        if len(self._supported_color_modes) == 1:
            self._fixed_color_mode = next(iter(self._supported_color_modes))
        else:
            self._fixed_color_mode = None

    @property
    def is_on(self) -> bool:
        """Return true if the light is on."""
        return self._device.on

    @property
    def brightness(self) -> int | None:
        """Return the brightness of the light."""
        # Always return brightness if we have it, even if the color mode doesn't indicate it
        if self._device.brightness is not None:
            return int((self._device.brightness / 100.0) * 255.0)
        return None

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        """Return the RGB color of the light."""
        if ColorMode.RGB not in self.supported_color_modes:
            return None
        return self._device.rgb_color

    @property
    def color_temp_kelvin(self) -> int | None:
        """Return the color temperature in Kelvin."""
        if ColorMode.COLOR_TEMP not in self.supported_color_modes:
            return None
        return self._device.temperature_color

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        """Return the supported color modes."""
        return self._supported_color_modes

    @property
    def color_mode(self) -> ColorMode | str | None:
        """Return the current color mode of the light."""
        if self._fixed_color_mode:
            return self._fixed_color_mode

        # Determine which mode the device is in
        if (
            ColorMode.COLOR_TEMP in self.supported_color_modes
            and self._device.temperature_color is not None
            and self._device.temperature_color > 0
        ):
            return ColorMode.COLOR_TEMP

        if ColorMode.RGB in self.supported_color_modes:
            return ColorMode.RGB

        if ColorMode.BRIGHTNESS in self.supported_color_modes:
            return ColorMode.BRIGHTNESS

        return ColorMode.ONOFF

    @callback
    def _device_updated(self, device: GoveeLocalDevice) -> None:
        """Handle device updates."""
        self.async_write_ha_state()
        
    @callback
    def _handle_options_update(self, options) -> None:
        """Handle options updates."""
        new_temp_only_mode = options.get(CONF_TEMP_ONLY_MODE, False)
        
        # Only update if the temperature-only mode setting has changed
        if new_temp_only_mode != self._temperature_only_mode:
            self._temperature_only_mode = new_temp_only_mode
            self._setup_color_modes()
            _LOGGER.debug(f"Updated temperature-only mode to {new_temp_only_mode} for {self.entity_id}")
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light."""
        # If no state-changing parameters are provided or light is off, turn it on
        if not self.is_on or not kwargs:
            await self.coordinator.turn_on(self._device)

        # Apply brightness if provided
        if ATTR_BRIGHTNESS in kwargs:
            brightness = int((kwargs[ATTR_BRIGHTNESS] / 255.0) * 100.0)
            await self.coordinator.set_brightness(self._device, brightness)

        # Apply colors/temperature
        if ATTR_RGB_COLOR in kwargs:
            red, green, blue = kwargs[ATTR_RGB_COLOR]
            await self.coordinator.set_rgb_color(self._device, red, green, blue)
        elif ATTR_COLOR_TEMP_KELVIN in kwargs:
            temperature = int(kwargs[ATTR_COLOR_TEMP_KELVIN])
            await self.coordinator.set_temperature(self._device, temperature)
        

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        await self.coordinator.turn_off(self._device)
        
    async def async_will_remove_from_hass(self) -> None:
        """Clean up resources when entity is removed."""
        # Remove the options update callback
        self.coordinator.unregister_device_callback(self._device.device_id)
        await super().async_will_remove_from_hass()

