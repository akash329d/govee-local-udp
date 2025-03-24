"""Controller for Govee local devices."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple, cast

from .capabilities import GoveeLightCapabilities, get_capabilities_for_model
from .message import (
    BrightnessMessage,
    ColorMessage,
    DevStatusMessage,
    DeviceStatus,
    GoveeDevice,
    GoveeLightFeatures,
    GoveeMessage,
    MessageResponseFactory,
    OnOffMessage,
    SceneMessage,
    SegmentColorMessage,
    ScanMessage,
)

_LOGGER = logging.getLogger(__name__)

# Network configuration
BROADCAST_ADDRESS = "239.255.255.250"
BROADCAST_PORT = 4001
LISTENING_PORT = 4002
COMMAND_PORT = 4003

# Timers and intervals
DISCOVERY_INTERVAL = 60  # Search for new devices every 60 seconds
EVICT_INTERVAL = DISCOVERY_INTERVAL * 3  # Remove devices after 3x discovery interval
UPDATE_INTERVAL = 30  # Update device status every 30 seconds
RETRY_PATTERN = [0.2, 0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 7.0, 10.0]  # Retry backoff pattern

# Connection retry settings
CONNECTION_RETRY_ATTEMPTS = 5
CONNECTION_RETRY_DELAY = 2  # seconds


class GoveeLocalDevice:
    """Representation of a Govee device on the local network."""

    def __init__(
        self,
        controller: GoveeController,
        ip: str,
        device_id: str,
        model: str,
        capabilities: Optional[GoveeLightCapabilities] = None,
        is_manual: bool = False,
        ble_hardware_version: str = "",
        ble_software_version: str = "",
        wifi_hardware_version: str = "",
        wifi_software_version: str = "",
    ) -> None:
        """Initialize the device."""
        self._controller = controller
        self._ip = ip
        self._device_id = device_id
        self._model = model
        self._capabilities = capabilities or get_capabilities_for_model(model)
        self._is_manual = is_manual
        self._update_callbacks: List[Callable[[GoveeLocalDevice], None]] = []
        
        # Version information
        self._ble_hardware_version = ble_hardware_version
        self._ble_software_version = ble_software_version
        self._wifi_hardware_version = wifi_hardware_version
        self._wifi_software_version = wifi_software_version
        
        # State properties
        self._on: bool = False
        self._brightness: int = 100
        self._rgb_color: Optional[Tuple[int, int, int]] = (255, 255, 255)
        self._color_temp: Optional[int] = None
        self._lastseen = datetime.now()
    
    @property
    def ip(self) -> str:
        """Return the device IP address."""
        return self._ip
    
    @property
    def device_id(self) -> str:
        """Return the device ID."""
        return self._device_id
        
    @property
    def model(self) -> str:
        """Return the device model."""
        return self._model
    
    @property
    def fingerprint(self) -> str:
        """Return a unique identifier for this device."""
        return self._device_id
    
    @property
    def capabilities(self) -> GoveeLightCapabilities:
        """Return the device capabilities."""
        return self._capabilities
    
    @property
    def is_manual(self) -> bool:
        """Return whether this device was manually added."""
        return self._is_manual
    
    @property
    def on(self) -> bool:
        """Return whether the device is on."""
        return self._on
    
    @property
    def brightness(self) -> int:
        """Return the device brightness (0-100)."""
        return self._brightness
    
    @property
    def rgb_color(self) -> Optional[Tuple[int, int, int]]:
        """Return the device RGB color."""
        return self._rgb_color
    
    @property
    def temperature_color(self) -> Optional[int]:
        """Return the device color temperature in Kelvin."""
        return self._color_temp
    
    @property
    def lastseen(self) -> datetime:
        """Return when the device was last seen."""
        return self._lastseen
        
    @property
    def ble_hardware_version(self) -> str:
        """Return the BLE hardware version."""
        return self._ble_hardware_version
        
    @property
    def ble_software_version(self) -> str:
        """Return the BLE software version."""
        return self._ble_software_version
        
    @property
    def wifi_hardware_version(self) -> str:
        """Return the WiFi hardware version."""
        return self._wifi_hardware_version
        
    @property
    def wifi_software_version(self) -> str:
        """Return the WiFi software version."""
        return self._wifi_software_version
    
    def update_lastseen(self) -> None:
        """Update the last seen timestamp."""
        self._lastseen = datetime.now()
    
    def add_update_callback(self, callback: Callable[[GoveeLocalDevice], None]) -> None:
        """Add a callback to call when the device state changes."""
        self._update_callbacks.append(callback)
    
    def remove_update_callback(self, callback: Callable[[GoveeLocalDevice], None]) -> None:
        """Remove an update callback."""
        if callback in self._update_callbacks:
            self._update_callbacks.remove(callback)
    
    def update(self, status: DeviceStatus) -> None:
        """Update the device state from a status message."""
        self._on = status.on
        self._brightness = status.brightness
        self._rgb_color = (status.color.r, status.color.g, status.color.b)
        
        if status.color_temperature_kelvin > 0:
            self._color_temp = status.color_temperature_kelvin
        
        self.update_lastseen()
        
        # Notify callbacks
        for callback in self._update_callbacks:
            callback(self)
    
    async def turn_on(self) -> None:
        """Turn the device on."""
        if self._controller:
            await self._controller.turn_on_off(self, True)
    
    async def turn_off(self) -> None:
        """Turn the device off."""
        if self._controller:
            await self._controller.turn_on_off(self, False)
    
    async def set_brightness(self, brightness: int) -> None:
        """Set the device brightness (0-100)."""
        if self._controller:
            await self._controller.set_brightness(self, brightness)
    
    async def set_rgb_color(self, red: int, green: int, blue: int) -> None:
        """Set the device RGB color."""
        if self._controller:
            await self._controller.set_color(self, rgb=(red, green, blue))
    
    async def set_temperature(self, temperature: int) -> None:
        """Set the device color temperature in Kelvin."""
        if self._controller:
            await self._controller.set_color(self, temperature=temperature)
    
    async def set_scene(self, scene: str) -> None:
        """Set the device to a scene."""
        if self._controller:
            await self._controller.set_scene(self, scene)
    
    def __str__(self) -> str:
        """Return a string representation of the device."""
        return f"GoveeLocalDevice({self._model}, {self._ip}, {self._device_id})"


class GoveeController:
    """Controller for Govee devices on the local network."""

    def __init__(
        self,
        loop=None,
        broadcast_address: str = BROADCAST_ADDRESS,
        broadcast_port: int = BROADCAST_PORT,
        listening_address: str = "0.0.0.0",
        listening_port: int = LISTENING_PORT,
        device_command_port: int = COMMAND_PORT,
        discovery_enabled: bool = False,
        discovery_interval: int = DISCOVERY_INTERVAL,
        evict_enabled: bool = False,
        evict_interval: int = EVICT_INTERVAL,
        update_enabled: bool = True,
        update_interval: int = UPDATE_INTERVAL,
        discovered_callback: Optional[Callable[[GoveeLocalDevice, bool], bool]] = None,
        evicted_callback: Optional[Callable[[GoveeLocalDevice], None]] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        """Initialize the controller."""
        self._logger = logger or _LOGGER
        
        # Network settings
        self._transport: Any = None
        self._protocol = None
        self._broadcast_address = broadcast_address
        self._broadcast_port = broadcast_port
        self._listening_address = listening_address
        self._listening_port = listening_port
        self._device_command_port = device_command_port
        
        # Asyncio and message handling
        self._loop = loop or asyncio.get_running_loop()
        self._cleanup_done: asyncio.Event = asyncio.Event()
        self._message_factory = MessageResponseFactory()
        
        # Device tracking
        self._devices: Dict[str, GoveeLocalDevice] = {}
        self._device_queue: Set[str] = set()
        
        # Timers and intervals
        self._discovery_enabled = discovery_enabled
        self._discovery_interval = discovery_interval
        self._update_enabled = update_enabled
        self._update_interval = update_interval
        self._evict_enabled = evict_enabled
        self._evict_interval = evict_interval
        
        # Callbacks
        self._device_discovered_callback = discovered_callback
        self._device_evicted_callback = evicted_callback
        
        # Timer handles
        self._discovery_handle: Optional[asyncio.TimerHandle] = None
        self._update_handle: Optional[asyncio.TimerHandle] = None
        
        # Command retry tracking
        self._pending_command_tasks: Dict[str, asyncio.Task] = {}
        self._state_verification_events: Dict[str, Tuple[asyncio.Event, Callable]] = {}
    
    async def start(self) -> None:
        """Start the controller."""
        self._transport, self._protocol = await self._loop.create_datagram_endpoint(
            lambda: self, local_addr=(self._listening_address, self._listening_port)
        )
        
        if self._discovery_enabled:
            self.send_discovery_message()
        if self._update_enabled:
            self.send_update_message()
    
    def cleanup(self) -> asyncio.Event:
        """Stop and clean up the controller."""
        self._cleanup_done.clear()
        self.set_update_enabled(False)
        self.set_discovery_enabled(False)
        
        if self._transport:
            self._transport.close()
        
        # Cancel all pending commands
        for task in self._pending_command_tasks.values():
            if not task.done():
                task.cancel()
        
        self._devices.clear()
        self._device_queue.clear()
        return self._cleanup_done
    
    def add_device_to_queue(self, ip: str) -> bool:
        """Add a device to the discovery queue."""
        if ip in self._device_queue:
            return False
        
        self._device_queue.add(ip)
        if not self._discovery_enabled:
            self.send_discovery_message()
        return True
    
    def remove_device_from_queue(self, ip: str) -> bool:
        """Remove a device from the discovery queue."""
        if ip in self._device_queue:
            self._device_queue.remove(ip)
            return True
        return False
    
    @property
    def device_queue(self) -> Set[str]:
        """Return the set of devices in the discovery queue."""
        return self._device_queue
    
    def remove_device(self, device: str | GoveeLocalDevice) -> None:
        """Remove a device."""
        if isinstance(device, GoveeLocalDevice):
            device = device.fingerprint
        
        if device in self._devices:
            # Clear any pending tasks for this device
            keys_to_remove = [
                key for key in self._pending_command_tasks if key.startswith(f"{device}_")
            ]
            for key in keys_to_remove:
                task = self._pending_command_tasks.pop(key)
                if not task.done():
                    task.cancel()
            
            # Remove verification events
            if device in self._state_verification_events:
                del self._state_verification_events[device]
            
            # Remove the device itself
            del self._devices[device]
    
    @property
    def evict_enabled(self) -> bool:
        """Return whether device eviction is enabled."""
        return self._evict_enabled
    
    def set_evict_enabled(self, enabled: bool) -> None:
        """Set whether device eviction is enabled."""
        self._evict_enabled = enabled
    
    def set_discovery_enabled(self, enabled: bool) -> None:
        """Set whether device discovery is enabled."""
        if self._discovery_enabled == enabled:
            return
        
        self._discovery_enabled = enabled
        if enabled:
            self.send_discovery_message()
        elif self._discovery_handle:
            self._discovery_handle.cancel()
            self._discovery_handle = None
    
    @property
    def discovery_enabled(self) -> bool:
        """Return whether device discovery is enabled."""
        return self._discovery_enabled
    
    def set_discovery_interval(self, interval: int) -> None:
        """Set the discovery interval."""
        self._discovery_interval = interval
    
    @property
    def discovery_interval(self) -> int:
        """Return the discovery interval."""
        return self._discovery_interval
    
    def set_device_discovered_callback(
        self, callback: Optional[Callable[[GoveeLocalDevice, bool], bool]]
    ) -> Optional[Callable[[GoveeLocalDevice, bool], bool]]:
        """Set the callback for device discovery."""
        old_callback = self._device_discovered_callback
        self._device_discovered_callback = callback
        return old_callback
    
    def set_update_enabled(self, enabled: bool) -> None:
        """Set whether device updates are enabled."""
        if self._update_enabled == enabled:
            return
        
        self._update_enabled = enabled
        if enabled:
            self.send_update_message()
        elif self._update_handle:
            self._update_handle.cancel()
            self._update_handle = None
    
    @property
    def update_enabled(self) -> bool:
        """Return whether device updates are enabled."""
        return self._update_enabled
    
    def send_discovery_message(self) -> None:
        """Send a discovery message to find devices."""
        if not self._transport:
            return
        
        # Create message
        message = ScanMessage()
        
        # Send to multicast group
        if self._discovery_enabled:
            self._transport.sendto(
                message.to_bytes(),
                (self._broadcast_address, self._broadcast_port)
            )
        
        # Send to queued devices
        for ip in self._device_queue:
            self._transport.sendto(
                message.to_bytes(),
                (ip, self._broadcast_port)
            )
        
        # Send to manually added devices
        manually_added_devices = [device.ip for device in self._devices.values() if device.is_manual]
        for ip in manually_added_devices:
            self._transport.sendto(
                message.to_bytes(),
                (ip, self._broadcast_port)
            )
        
        # Schedule next discovery if enabled
        if self._discovery_enabled:
            self._discovery_handle = self._loop.call_later(
                self._discovery_interval, self.send_discovery_message
            )
    
    def send_update_message(self, device: Optional[GoveeLocalDevice] = None) -> None:
        """Send an update message to get device status."""
        if not self._transport:
            return
        
        if device:
            self._send_update_message(device)
        else:
            for d in self._devices.values():
                self._send_update_message(d)
        
        # Schedule next update if enabled
        if self._update_enabled and not device:  # Only reschedule if not for a specific device
            self._update_handle = self._loop.call_later(
                self._update_interval, self.send_update_message
            )
    
    async def _execute_command(
        self,
        device: GoveeLocalDevice,
        message: GoveeMessage,
        verify_state_callback=None
    ) -> None:
        """Execute a command with retry queue and optional state verification."""
        device_key = f"{device.fingerprint}_{message.command}"
        
        # Cancel any existing task for this device and command
        if device_key in self._pending_command_tasks:
            existing_task = self._pending_command_tasks[device_key]
            if not existing_task.done():
                existing_task.cancel()
                try:
                    await existing_task
                except asyncio.CancelledError:
                    self._logger.debug(f"Cancelled pending {message.command} task for device {device}")
        
        # Create and store the new task
        task = self._loop.create_task(
            self._execute_with_retries(device, message, verify_state_callback)
        )
        self._pending_command_tasks[device_key] = task
        
        task.add_done_callback(
            lambda t: self._pending_command_tasks.pop(device_key, None)
        )
        
        await task
    
    async def _execute_with_retries(
        self,
        device: GoveeLocalDevice,
        message: GoveeMessage,
        verify_state_callback=None,
        max_retries: int = len(RETRY_PATTERN)
    ) -> None:
        """Execute a command with multiple retries and optional state verification."""
        # Send the initial message immediately
        self._send_message(message, device)
        
        # Always wait 100ms between msg and status update to lessen spam
        await asyncio.sleep(0.1)
        
        # Request initial status update
        self._send_update_message(device)
        
        # If no verification callback, just use retries without verification
        if not verify_state_callback:
            return await self._execute_basic_retries(device, message, max_retries)
        
        # Create a state verification event
        state_changed_event = asyncio.Event()
        device_key = device.fingerprint
        
        # Register our event and verification callback
        self._state_verification_events[device_key] = (state_changed_event, verify_state_callback)
        
        try:
            # Send retries with increasing delays
            for i, delay in enumerate(RETRY_PATTERN[:max_retries-1]):
                try:
                    # Wait for either the delay to complete or the state to change
                    state_changed_task = asyncio.create_task(state_changed_event.wait())
                    delay_task = asyncio.create_task(asyncio.sleep(delay))
                    
                    # Wait for either task to complete
                    try:
                        done, pending = await asyncio.wait(
                            [state_changed_task, delay_task],
                            return_when=asyncio.FIRST_COMPLETED
                        )
                        
                        # Cancel the pending task
                        for task in pending:
                            task.cancel()
                            try:
                                # Wait for the cancelled task to complete
                                await task
                            except asyncio.CancelledError:
                                # This is expected for cancelled tasks
                                pass
                        
                        # If state changed, we're done
                        if state_changed_task in done and not state_changed_task.cancelled():
                            if state_changed_task.result():
                                self._logger.debug(
                                    f"Stopping retries for {device}: {message.command} - desired state reached"
                                )
                                return
                    except asyncio.CancelledError:
                        state_changed_task.cancel()
                        delay_task.cancel()
                        try:
                            await asyncio.gather(state_changed_task, delay_task, return_exceptions=True)
                        except asyncio.CancelledError:
                            pass
                        raise
                    
                    # Check if we've been cancelled
                    if asyncio.current_task().cancelled():
                        return
                    
                    # Send the command again
                    self._send_message(message, device)
                    await asyncio.sleep(0.1)
                    self._send_update_message(device)
                    self._logger.debug(f"Retry {i+1} for {device}: {message.command}")
                except asyncio.CancelledError:
                    self._logger.debug(f"Cancelled during retry {i+1} for {device}")
                    raise
        finally:
            # Clean up our event registration
            self._state_verification_events.pop(device_key, None)
    
    async def _execute_basic_retries(
        self,
        device: GoveeLocalDevice,
        message: GoveeMessage,
        max_retries: int = len(RETRY_PATTERN)
    ) -> None:
        """Simple retry pattern without state verification."""
        # Send retries with increasing delays
        for i, delay in enumerate(RETRY_PATTERN[:max_retries-1]):
            try:
                await asyncio.sleep(delay)
                
                # Check if we've been cancelled
                if asyncio.current_task().cancelled():
                    return
                
                self._send_message(message, device)
                
                # Request a status update after sending the command
                self._send_update_message(device)
                self._logger.debug(f"Retry {i+1} for {device}: {message.command}")
            except asyncio.CancelledError:
                self._logger.debug(f"Cancelled during retry {i+1} for {device}")
                raise
    
    async def turn_on_off(self, device: GoveeLocalDevice, status: bool) -> None:
        """Turn a device on or off."""
        message = OnOffMessage(on=status)
        
        # Verification callback to check if device status matches desired state
        def verify_state(device):
            return device.on == status
        
        await self._execute_command(device, message, verify_state)
    
    async def set_brightness(self, device: GoveeLocalDevice, brightness: int) -> None:
        """Set device brightness."""
        message = BrightnessMessage(value=brightness)
        
        # Verification callback to check if device brightness matches desired value
        def verify_state(device):
            return device.brightness == brightness
        
        await self._execute_command(device, message, verify_state)
    
    async def set_color(
        self,
        device: GoveeLocalDevice,
        *,
        rgb: Optional[Tuple[int, int, int]] = None,
        temperature: Optional[int] = None,
    ) -> None:
        """Set device color."""
        message = ColorMessage(rgb=rgb, temperature=temperature)
        
        # Verification callback to check if device color matches desired values
        def verify_state(device):
            if rgb and device.rgb_color:
                # Allow for small differences in RGB values
                return all(abs(a - b) <= 5 for a, b in zip(device.rgb_color, rgb))
            elif temperature and device.temperature_color:
                # Allow for small differences in temperature
                return abs(device.temperature_color - temperature) <= 100
            return False
        
        await self._execute_command(device, message, verify_state)
    
    async def set_scene(self, device: GoveeLocalDevice, scene: str) -> None:
        """Set device to a scene."""
        if (
            not device.capabilities or
            GoveeLightFeatures.SCENES & device.capabilities.features == 0
        ):
            self._logger.warning(f"Scenes are not supported by device {device}")
            return
        
        scene_code = device.capabilities.scenes.get(scene.lower())
        if not scene_code:
            self._logger.warning(f"Scene {scene} is not available for device {device}")
            return
        
        message = SceneMessage(scene_code=scene_code)
        await self._execute_command(device, message)
    
    async def set_segment_color(
        self, device: GoveeLocalDevice, segment: int, rgb: Tuple[int, int, int]
    ) -> None:
        """Set color for a specific segment of the device."""
        if (
            not device.capabilities or
            GoveeLightFeatures.SEGMENT_CONTROL & device.capabilities.features == 0
        ):
            self._logger.warning(f"Segment control is not supported by device {device}")
            return
        
        if segment < 1 or segment > len(device.capabilities.segments):
            self._logger.warning(f"Segment index {segment} is not valid for device {device}")
            return
        
        segment_data = device.capabilities.segments[segment - 1]
        if not segment_data:
            self._logger.warning(f"Segment {segment} is not supported by device {device}")
            return
        
        message = SegmentColorMessage(segment_data=segment_data, rgb=rgb)
        await self._execute_command(device, message)
    
    def get_device_by_ip(self, ip: str) -> Optional[GoveeLocalDevice]:
        """Get a device by IP address."""
        for device in self._devices.values():
            if device.ip == ip:
                return device
        return None
    
    def get_device_by_model(self, model: str) -> List[GoveeLocalDevice]:
        """Get devices by model."""
        return [device for device in self._devices.values() if device.model == model]
    
    def get_device_by_fingerprint(self, fingerprint: str) -> Optional[GoveeLocalDevice]:
        """Get a device by fingerprint."""
        return self._devices.get(fingerprint)
    
    @property
    def devices(self) -> List[GoveeLocalDevice]:
        """Return a list of all devices."""
        return list(self._devices.values())
    
    @property
    def has_devices(self) -> bool:
        """Return whether there are any devices."""
        return bool(self._devices)
    
    @property
    def has_queued_devices(self) -> bool:
        """Return whether there are any queued devices."""
        return bool(self._device_queue)
    
    def connection_made(self, transport) -> None:
        """Handle connection made."""
        self._transport = transport
        sock = self._transport.get_extra_info("socket")
        
        # Set socket options for broadcast and multicast
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        
        broadcast_ip = ipaddress.ip_address(self._broadcast_address)
        
        if broadcast_ip.is_multicast:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            
            sock.setsockopt(
                socket.SOL_IP,
                socket.IP_MULTICAST_IF,
                socket.inet_aton(self._listening_address),
            )
            sock.setsockopt(
                socket.SOL_IP,
                socket.IP_ADD_MEMBERSHIP,
                socket.inet_aton(self._broadcast_address)
                + socket.inet_aton(self._listening_address),
            )
    
    def connection_lost(self, exc) -> None:
        """Handle connection lost."""
        if self._transport:
            broadcast_ip = ipaddress.ip_address(self._broadcast_address)
            if broadcast_ip.is_multicast:
                sock = self._transport.get_extra_info("socket")
                sock.setsockopt(
                    socket.SOL_IP,
                    socket.IP_DROP_MEMBERSHIP,
                    socket.inet_aton(self._broadcast_address)
                    + socket.inet_aton(self._listening_address),
                )
        
        self._cleanup_done.set()
        self._logger.debug("Disconnected")
    
    def datagram_received(self, data: bytes, addr: Tuple) -> None:
        """Handle received datagram."""
        if data:
            self._logger.debug(f"Received {len(data)} bytes from {addr}")
            self._loop.create_task(self._handle_datagram_received(data, addr))
    
    async def _handle_datagram_received(self, data: bytes, addr: Tuple) -> None:
        """Handle the received datagram asynchronously."""
        try:
            # Log the raw data for debugging
            try:
                json_str = data.decode("utf-8")
                self._logger.debug(f"Raw data from {addr}: {json_str[:200]}")
            except:
                self._logger.debug(f"Non-text data received from {addr}")
            
            message = self._message_factory.create_message(data)
            if not message:
                self._logger.debug(f"Message factory couldn't parse data from {addr}. First 100 bytes: {data[:100]}")
                return
            
            if isinstance(message, GoveeDevice):
                self._logger.debug(f"Device info message received from {addr}: {message.device_id}")
                await self._handle_scan_response(message)
            elif isinstance(message, DeviceStatus):
                self._logger.debug(f"Status update message received from {addr}")
                await self._handle_status_update_response(message, addr)
            else:
                self._logger.debug(f"Unknown message type received: {type(message)}")
        except Exception as ex:
            self._logger.error(f"Error handling message: {ex}")
            import traceback
            self._logger.error(traceback.format_exc())
    
    async def _handle_status_update_response(self, message: DeviceStatus, addr: Tuple) -> None:
        """Handle a status update response."""
        ip = addr[0]
        device = self.get_device_by_ip(ip)
        
        if device:
            device.update(message)
            
            # Check if we're waiting for a state verification on this device
            device_key = device.fingerprint
            if device_key in self._state_verification_events:
                event, verify_callback = self._state_verification_events[device_key]
                # Check if the new state matches what we're waiting for
                if verify_callback(device):
                    self._logger.debug(f"Device {device} reached desired state")
                    event.set()
    
    async def _handle_scan_response(self, device_info: GoveeDevice) -> None:
        """Handle a scan response."""
        if not device_info.device_id:
            self._logger.warning("Received device info with empty device_id")
            return
            
        fingerprint = device_info.device_id
        self._logger.debug(f"Processing scan response for device with ID: {fingerprint}")
        device = self.get_device_by_fingerprint(fingerprint)
        
        if device:
            # Update existing device's IP if it changed
            if device.ip != device_info.ip and device_info.ip != "unknown":
                self._logger.info(f"Device {fingerprint} IP changed from {device.ip} to {device_info.ip}")
                device._ip = device_info.ip
            
            if self._call_discovered_callback(device, False):
                device.update_lastseen()
                self._logger.debug(f"Device updated: {device}")
        else:
            # Create a new device
            self._logger.info(f"Creating new device: ID={device_info.device_id}, Model={device_info.model}, IP={device_info.ip}")
            device = GoveeLocalDevice(
                controller=self,
                ip=device_info.ip,
                device_id=device_info.device_id,
                model=device_info.model,
                ble_hardware_version=device_info.ble_hardware_version,
                ble_software_version=device_info.ble_software_version,
                wifi_hardware_version=device_info.wifi_hardware_version,
                wifi_software_version=device_info.wifi_software_version,
            )
            
            if self._call_discovered_callback(device, True):
                self._devices[fingerprint] = device
                self._logger.info(f"Device discovered: {device}")
            else:
                self._logger.debug(f"Device {device} ignored by callback")
        
        # Evict old devices if enabled
        if self._evict_enabled:
            self._evict()
    
    def _call_discovered_callback(self, device: GoveeLocalDevice, is_new: bool) -> bool:
        """Call the discovered callback and return the result."""
        if not self._device_discovered_callback:
            return True
        return self._device_discovered_callback(device, is_new)
    
    def _send_message(self, message: GoveeMessage, device: GoveeLocalDevice) -> None:
        """Send a message to a device."""
        self._transport.sendto(
            message.to_bytes(),
            (device.ip, self._device_command_port)
        )
    
    def _send_update_message(self, device: GoveeLocalDevice) -> None:
        """Send an update message to a device."""
        self._send_message(DevStatusMessage(), device)
    
    def _evict(self) -> None:
        """Evict devices that haven't been seen for a while."""
        now = datetime.now()
        devices_to_evict = []
        
        for fingerprint, device in self._devices.items():
            diff = now - device.lastseen
            if diff.total_seconds() >= self._evict_interval:
                devices_to_evict.append(fingerprint)
        
        for fingerprint in devices_to_evict:
            device = self._devices[fingerprint]
            device._controller = None
            del self._devices[fingerprint]
            
            self._logger.debug(f"Device evicted: {device}")
            if self._device_evicted_callback:
                self._device_evicted_callback(device)