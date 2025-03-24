"""Light platform for the Govee Local UDP integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_EFFECT,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
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

# Scene that represents no active scene
SCENE_NONE = "none"


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
    _attr_effect: str | None = None
    _supported_color_modes: set[ColorMode]
    _fixed_color_mode: ColorMode | None = None
    _last_color_state: (
        tuple[
            ColorMode | str | None,
            int | None,
            tuple[int, int, int] | int | None,
        ]
        | None
    ) = None

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

        # Get device capabilities
        capabilities = device.capabilities
        color_modes = {ColorMode.ONOFF}

        # Check if temperature-only mode is enabled globally
        self._temperature_only_mode = coordinator.config_entry.options.get(CONF_TEMP_ONLY_MODE, False)

        # Map features to color modes
        if GoveeLightFeatures.BRIGHTNESS & capabilities.features:
            color_modes.add(ColorMode.BRIGHTNESS)
            
        # Only add RGB mode if not in temperature-only mode
        if (GoveeLightFeatures.COLOR_RGB & capabilities.features) and not self._temperature_only_mode:
            color_modes.add(ColorMode.RGB)
            
        if GoveeLightFeatures.COLOR_KELVIN_TEMPERATURE & capabilities.features:
            color_modes.add(ColorMode.COLOR_TEMP)
            self._attr_min_color_temp_kelvin = 2000
            self._attr_max_color_temp_kelvin = 9000

        # Set scenes as effects if supported
        if GoveeLightFeatures.SCENES & capabilities.features and capabilities.scenes:
            self._attr_supported_features = LightEntityFeature.EFFECT
            self._attr_effect_list = [SCENE_NONE, *capabilities.scenes.keys()]

        # Filter and set the supported color modes
        self._supported_color_modes = filter_supported_color_modes(color_modes)
        if len(self._supported_color_modes) == 1:
            self._fixed_color_mode = next(iter(self._supported_color_modes))

        # Device info
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

    @property
    def is_on(self) -> bool:
        """Return true if the light is on."""
        return self._device.on

    @property
    def brightness(self) -> int | None:
        """Return the brightness of the light."""
        if ColorMode.BRIGHTNESS not in self._supported_color_modes:
            return None
        return int((self._device.brightness / 100.0) * 255.0)

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        """Return the RGB color of the light."""
        if ColorMode.RGB not in self._supported_color_modes:
            return None
        return self._device.rgb_color

    @property
    def color_temp_kelvin(self) -> int | None:
        """Return the color temperature in Kelvin."""
        if ColorMode.COLOR_TEMP not in self._supported_color_modes:
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
            ColorMode.COLOR_TEMP in self._supported_color_modes
            and self._device.temperature_color is not None
            and self._device.temperature_color > 0
        ):
            return ColorMode.COLOR_TEMP

        if ColorMode.RGB in self._supported_color_modes:
            return ColorMode.RGB

        if ColorMode.BRIGHTNESS in self._supported_color_modes:
            return ColorMode.BRIGHTNESS

        return ColorMode.ONOFF

    @callback
    def _device_updated(self, device: GoveeLocalDevice) -> None:
        """Handle device updates."""
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

        # Apply colors/temperature - store last mode for scene restoration
        if ATTR_RGB_COLOR in kwargs:
            self._attr_effect = None
            self._save_last_color_state()
            red, green, blue = kwargs[ATTR_RGB_COLOR]
            await self.coordinator.set_rgb_color(self._device, red, green, blue)
        elif ATTR_COLOR_TEMP_KELVIN in kwargs:
            self._attr_effect = None
            self._save_last_color_state()
            temperature = int(kwargs[ATTR_COLOR_TEMP_KELVIN])
            await self.coordinator.set_temperature(self._device, temperature)
        
        # Apply scene/effect if provided
        elif ATTR_EFFECT in kwargs and self.supported_features & LightEntityFeature.EFFECT:
            effect = kwargs[ATTR_EFFECT]
            if effect and self.effect_list and effect in self.effect_list:
                if effect == SCENE_NONE:
                    self._attr_effect = None
                    await self._restore_last_color_state()
                else:
                    self._save_last_color_state()
                    self._attr_effect = effect
                    await self.coordinator.set_scene(self._device, effect)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        await self.coordinator.turn_off(self._device)

    def _save_last_color_state(self) -> None:
        """Save the last color state for restoration after scenes."""
        color_mode = self.color_mode
        
        if color_mode == ColorMode.COLOR_TEMP:
            color_data = self.color_temp_kelvin
        elif color_mode == ColorMode.RGB:
            color_data = self.rgb_color
        else:
            color_data = None
            
        self._last_color_state = (color_mode, self.brightness, color_data)

    async def _restore_last_color_state(self) -> None:
        """Restore the previously saved color state."""
        if not self._last_color_state:
            return
            
        color_mode, brightness, color_data = self._last_color_state
        
        # Restore color/temperature
        if color_mode == ColorMode.COLOR_TEMP and isinstance(color_data, int):
            await self.coordinator.set_temperature(self._device, color_data)
        elif color_mode == ColorMode.RGB and isinstance(color_data, tuple) and len(color_data) == 3:
            await self.coordinator.set_rgb_color(self._device, *color_data)
            
        # Restore brightness
        if brightness is not None:
            await self.coordinator.set_brightness(
                self._device, int((brightness / 255.0) * 100.0)
            )
            
        self._last_color_state = None