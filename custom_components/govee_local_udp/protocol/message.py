"""Message definitions for Govee local API."""

from __future__ import annotations

import json
import logging
from typing import ClassVar, Optional, Tuple, Union

from dataclasses import dataclass
from enum import IntEnum

_LOGGER = logging.getLogger(__name__)

MSG_SCAN = "scan"
MSG_STATUS = "devStatus"
MSG_TURN = "turn"
MSG_BRIGHTNESS = "brightness"
MSG_COLOR = "colorwc"
MSG_COMMAND = "ptReal"


class GoveeLightFeatures(IntEnum):
    """Features supported by the light."""

    NONE = 0
    BRIGHTNESS = 1
    COLOR_RGB = 2
    COLOR_KELVIN_TEMPERATURE = 4
    SCENES = 8
    SEGMENT_CONTROL = 16


@dataclass
class GoveeMessage:
    """Base class for all Govee messages."""

    command: ClassVar[str]
    
    def to_bytes(self) -> bytes:
        """Convert the message to bytes to be sent over the network."""
        msg_dict = {"msg": {"cmd": self.command, "data": self.to_dict()}}
        return json.dumps(msg_dict).encode("utf-8")
        
    def to_dict(self) -> dict:
        """Convert message to dict format."""
        return {}


@dataclass
class ScanMessage(GoveeMessage):
    """Scan for devices on the network."""

    command: ClassVar[str] = MSG_SCAN
    
    def to_dict(self) -> dict:
        """Convert message to dict format."""
        return {"account_topic": "reserve"}


@dataclass
class DevStatusMessage(GoveeMessage):
    """Request device status."""

    command: ClassVar[str] = MSG_STATUS


@dataclass
class OnOffMessage(GoveeMessage):
    """Turn the device on or off."""

    command: ClassVar[str] = MSG_TURN
    on: bool
    
    def to_dict(self) -> dict:
        """Convert message to dict format."""
        return {"value": 1 if self.on else 0}


@dataclass
class BrightnessMessage(GoveeMessage):
    """Set the brightness of the device."""

    command: ClassVar[str] = MSG_BRIGHTNESS
    value: int
    
    def to_dict(self) -> dict:
        """Convert message to dict format."""
        return {"value": self.value}


@dataclass
class ColorMessage(GoveeMessage):
    """Set the color of the device."""

    command: ClassVar[str] = MSG_COLOR
    rgb: Optional[Tuple[int, int, int]] = None
    temperature: Optional[int] = None
    
    def to_dict(self) -> dict:
        """Convert message to dict format."""
        if self.rgb is not None:
            r, g, b = self.rgb
            return {
                "color": {"r": r, "g": g, "b": b},
                "colorTemInKelvin": 0,
            }
        else:
            return {
                "color": {"r": 0, "g": 0, "b": 0},
                "colorTemInKelvin": self.temperature or 0,
            }


@dataclass
class SceneMessage(GoveeMessage):
    """Set a scene."""

    command: ClassVar[str] = MSG_COMMAND
    scene_code: bytes
    
    def to_dict(self) -> dict:
        """Convert message to dict format."""
        # Convert scene code to base64 command format
        # This is a simplified version, the actual implementation would need to properly encode the scene
        return {"command": [self.scene_code.hex()]}


@dataclass
class SegmentColorMessage(GoveeMessage):
    """Set segment color."""

    command: ClassVar[str] = MSG_COMMAND
    segment_data: bytes
    rgb: Tuple[int, int, int]
    
    def to_dict(self) -> dict:
        """Convert message to dict format."""
        # This is a placeholder - segment control requires special encoding
        # The actual implementation would need to properly encode the segment data
        return {"command": [self.segment_data.hex()]}


# Response objects

@dataclass
class DeviceColor:
    """RGB color of a device."""

    r: int
    g: int
    b: int


@dataclass
class DeviceStatus:
    """Device status response."""

    on: bool
    brightness: int
    color: DeviceColor
    color_temperature_kelvin: int


@dataclass
class GoveeDevice:
    """Information about a Govee device."""

    ip: str
    device_id: str
    model: str
    ble_hardware_version: str
    ble_software_version: str
    wifi_hardware_version: str
    wifi_software_version: str


class MessageResponseFactory:
    """Factory for creating response messages."""

    def create_message(self, data: bytes) -> Optional[Union[GoveeDevice, DeviceStatus]]:
        """Parse response data and create the appropriate message object."""
        try:
            json_str = data.decode("utf-8")
            _LOGGER.debug(f"Received message: {json_str[:200]}")
            json_data = json.loads(json_str)
            
            # Check if it's a valid message format
            if not json_data.get("msg"):
                _LOGGER.warning("Invalid message format, missing 'msg' field")
                return None
                
            msg = json_data["msg"]
            cmd = msg.get("cmd")
            msg_data = msg.get("data", {})
            
            if not cmd or not msg_data:
                _LOGGER.warning(f"Invalid message format, missing 'cmd' or 'data' field: {json_data}")
                return None
            
            # First, try to handle scan responses (device discovery)
            if cmd == MSG_SCAN:
                # The device field can be either a string (device ID) or an object
                device_field = msg_data.get("device")
                ip = msg_data.get("ip", "unknown")
                device_id = ""
                sku = ""
                
                # If device is a string, it's likely the device ID
                if isinstance(device_field, str):
                    device_id = device_field
                    _LOGGER.debug(f"Device ID from string: {device_id}")
                    # Get SKU (model) from main data object
                    sku = msg_data.get("sku", "")
                elif isinstance(device_field, dict):
                    # Otherwise it's an object with a deviceId field
                    device_id = device_field.get("deviceId", "")
                    _LOGGER.debug(f"Device ID from object: {device_id}")
                    # Try to get SKU from device object first
                    sku = device_field.get("sku", "")
                
                # If we still don't have a device ID, try finding it in the main data
                if not device_id and "deviceId" in msg_data:
                    device_id = msg_data["deviceId"]
                
                # If we still don't have a SKU, try the main data
                if not sku and "sku" in msg_data:
                    sku = msg_data["sku"]
                
                _LOGGER.debug(f"Found device: ID={device_id}, SKU={sku}, IP={ip}")
                
                # Hardware/software versions
                ble_hw = msg_data.get("bleVersionHard", "")
                ble_sw = msg_data.get("bleVersionSoft", "")
                wifi_hw = msg_data.get("wifiVersionHard", "")
                wifi_sw = msg_data.get("wifiVersionSoft", "")
                
                if not device_id:
                    _LOGGER.warning(f"Could not extract device ID from message: {json_str[:200]}")
                    return None
                
                return GoveeDevice(
                    ip=ip,
                    device_id=device_id,
                    model=sku,
                    ble_hardware_version=ble_hw,
                    ble_software_version=ble_sw,
                    wifi_hardware_version=wifi_hw,
                    wifi_software_version=wifi_sw,
                )
            # Handle status responses
            elif cmd == MSG_STATUS:
                color_data = msg_data.get("color", {})
                return DeviceStatus(
                    on=msg_data.get("onOff", 0) == 1,
                    brightness=msg_data.get("brightness", 0),
                    color=DeviceColor(
                        r=color_data.get("r", 0),
                        g=color_data.get("g", 0),
                        b=color_data.get("b", 0),
                    ),
                    color_temperature_kelvin=msg_data.get("colorTemInKelvin", 0),
                )
                
        except json.JSONDecodeError as ex:
            _LOGGER.warning(f"Failed to decode JSON: {ex}")
        except Exception as ex:
            _LOGGER.warning(f"Error parsing message: {ex}, data: {data[:200]}")
            
        return None
