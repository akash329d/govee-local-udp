"""Services for the Govee Local UDP integration."""

import logging
import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_component import EntityComponent

from .const import DOMAIN
from .light import GoveeLocalUdpLight

_LOGGER = logging.getLogger(__name__)

# Service constants
SERVICE_SET_SCENE = "set_scene"

SERVICE_SET_SCENE_SCHEMA = vol.Schema({
    vol.Required("entity_id"): cv.entity_ids,
    vol.Required("scene"): cv.string,
})


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up the Govee Local UDP services."""
    component = EntityComponent(_LOGGER, DOMAIN, hass)

    async def handle_set_scene(service_call: ServiceCall) -> None:
        """Handle the set_scene service call."""
        entity_ids = service_call.data["entity_id"]
        scene = service_call.data["scene"]

        target_lights = []
        for entity_id in entity_ids:
            entity = component.get_entity(entity_id)
            if entity is None:
                _LOGGER.warning("Entity %s not found", entity_id)
                continue
                
            if not isinstance(entity, GoveeLocalUdpLight):
                _LOGGER.warning("Entity %s is not a Govee light", entity_id)
                continue
                
            target_lights.append(entity)
        
        if not target_lights:
            raise HomeAssistantError("No valid Govee lights found with the provided entity IDs")
        
        # Set scene for all target lights
        for light in target_lights:
            if light.effect_list and scene in light.effect_list:
                await light.async_turn_on(effect=scene)
            else:
                _LOGGER.warning(
                    "Scene %s not supported by light %s. Available scenes: %s",
                    scene, light.entity_id, light.effect_list
                )

    # Register services
    hass.services.async_register(
        DOMAIN, SERVICE_SET_SCENE, handle_set_scene, schema=SERVICE_SET_SCENE_SCHEMA
    )


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload Govee Local UDP services."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_SCENE):
        hass.services.async_remove(DOMAIN, SERVICE_SET_SCENE)