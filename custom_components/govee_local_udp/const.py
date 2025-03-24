"""Constants for the Govee Local UDP integration."""

from datetime import timedelta

DOMAIN = "govee_local_udp"
MANUFACTURER = "Govee"

# Default configuration values
CONF_MULTICAST_ADDRESS_DEFAULT = "239.255.255.250"
CONF_TARGET_PORT_DEFAULT = 4001
CONF_LISTENING_PORT_DEFAULT = 4002
CONF_DISCOVERY_INTERVAL_DEFAULT = 60
CONF_FORCED_IP_ADDRESSES = "forced_ip_addresses"

# Timeouts and intervals
SCAN_INTERVAL = timedelta(seconds=30)
DISCOVERY_TIMEOUT = 10
STATUS_TIMEOUT = 5

# Entity settings
ATTR_SCENE = "scene"

# Configuration options
CONF_TEMP_ONLY_MODE = "temperature_only_mode"  # To force a light to only use temperature mode