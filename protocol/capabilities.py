"""Govee light capabilities definition."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from .message import GoveeLightFeatures

_LOGGER = logging.getLogger(__name__)

@dataclass
class GoveeLightCapabilities:
    """Capabilities of a Govee light."""

    features: GoveeLightFeatures = GoveeLightFeatures.NONE
    scenes: Dict[str, bytes] = None
    segments: List[bytes] = None
    
    def __post_init__(self):
        """Initialize the scenes and segments dictionaries if needed."""
        if self.scenes is None:
            self.scenes = {}
        if self.segments is None:
            self.segments = []


# Basic capability with just on/off functionality
ON_OFF_CAPABILITIES = GoveeLightCapabilities(
    features=GoveeLightFeatures.NONE,
)

# Standard RGB light capability profile with brightness, color, and temperature
STANDARD_LIGHT_CAPABILITIES = GoveeLightCapabilities(
    features=(
        GoveeLightFeatures.BRIGHTNESS 
        | GoveeLightFeatures.COLOR_RGB 
        | GoveeLightFeatures.COLOR_KELVIN_TEMPERATURE
    ),
)

# This is a simplified version of the capabilities database
# In a real implementation, we would have a more complete database of models and their capabilities
# This would be populated from external sources or through discovery
GOVEE_LIGHT_CAPABILITIES: Dict[str, GoveeLightCapabilities] = {
    # H6160: RGB LED Strip
    "H6160": GoveeLightCapabilities(
        features=(
            GoveeLightFeatures.BRIGHTNESS 
            | GoveeLightFeatures.COLOR_RGB
        ),
    ),
    
    # H6163: RGB LED Strip with temperature
    "H6163": GoveeLightCapabilities(
        features=(
            GoveeLightFeatures.BRIGHTNESS 
            | GoveeLightFeatures.COLOR_RGB 
            | GoveeLightFeatures.COLOR_KELVIN_TEMPERATURE
        ),
    ),
    
    # H6104: RGB Bulb
    "H6104": GoveeLightCapabilities(
        features=(
            GoveeLightFeatures.BRIGHTNESS 
            | GoveeLightFeatures.COLOR_RGB 
            | GoveeLightFeatures.COLOR_KELVIN_TEMPERATURE
        ),
    ),
    
    # H6199: RGB LED Strip
    "H6199": GoveeLightCapabilities(
        features=(
            GoveeLightFeatures.BRIGHTNESS 
            | GoveeLightFeatures.COLOR_RGB
        ),
    ),
    
    # H7022: Bedside Lamp
    "H7022": GoveeLightCapabilities(
        features=(
            GoveeLightFeatures.BRIGHTNESS 
            | GoveeLightFeatures.COLOR_RGB 
            | GoveeLightFeatures.COLOR_KELVIN_TEMPERATURE
        ),
    ),
    
    # H6198: RGB Floor Lamp
    "H6198": GoveeLightCapabilities(
        features=(
            GoveeLightFeatures.BRIGHTNESS 
            | GoveeLightFeatures.COLOR_RGB 
            | GoveeLightFeatures.COLOR_KELVIN_TEMPERATURE
        ),
    ),
    
    # Default capabilities for unknown devices - only enable basic features
    "unknown": STANDARD_LIGHT_CAPABILITIES,
}


def get_capabilities_for_model(model: str) -> GoveeLightCapabilities:
    """Get the capabilities for a given model number."""
    if model in GOVEE_LIGHT_CAPABILITIES:
        return GOVEE_LIGHT_CAPABILITIES[model]
    
    _LOGGER.warning(
        "Unknown Govee model: %s. Using default capabilities. "
        "Please report this to improve device support.",
        model
    )
    return GOVEE_LIGHT_CAPABILITIES["unknown"]