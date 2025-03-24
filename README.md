# Govee Local UDP

This is a Home Assistant integration that provides local control of Govee devices using the local UDP protocol. This implementation follows best practices and includes robust retry logic for improved reliability.

## Features

- Local control of Govee devices over UDP (no cloud dependency)
- Robust command execution with retry logic
- State verification to ensure commands were successfully applied
- Support for lights with various capabilities (on/off, brightness, color, temperature, scenes)
- Auto-discovery of devices on the local network
- Temperature-only mode option for better HomeKit compatibility

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant instance
2. Go to "Integrations"
3. Click the three dots in the top right corner and select "Custom repositories"
4. Add the URL of this repository and select "Integration" as the category
5. Click "Add"
6. Search for "Govee Local UDP" and install it
7. Restart Home Assistant

### Manual Installation

1. Download or clone this repository
2. Copy the `custom_components/govee_local_udp` folder to the `custom_components` folder in your Home Assistant configuration directory
3. Restart Home Assistant

## Configuration

This integration can be configured through the Home Assistant UI:

1. Go to Configuration > Integrations
2. Click the "+ Add Integration" button
3. Search for "Govee Local UDP"
4. Follow the configuration steps

### Options

You can configure additional options by clicking on the "Configure" button on the integration:

- **Temperature-only mode**: When enabled, RGB control will be disabled and the lights will only use color temperature mode. This is useful for better HomeKit compatibility, as HomeKit sometimes sends RGB values for color temperature presets which can make the lights appear dimmer than expected.

## Supported Devices

Any Govee device that supports the local UDP API should work with this integration.
