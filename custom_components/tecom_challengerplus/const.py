"""Constants for the Tecom ChallengerPlus integration."""

DOMAIN = "tecom_challengerplus"

# Defaults align with Tecom docs that commonly use port 3001 for IP comms.
DEFAULT_SEND_PORT = 3001
DEFAULT_LISTEN_PORT = 3001

DEFAULT_POLL_INTERVAL_SECONDS = 1800

# Connection modes
MODE_CTPLUS = "ctplus"          # Management software (CTPlus-style) – binary protocol (experimental)
MODE_PRINTER = "printer"        # Printer / Computer Event Driven text stream – events only

TRANSPORT_UDP = "udp"
TRANSPORT_TCP = "tcp"

TCP_ROLE_CLIENT = "client"
TCP_ROLE_SERVER = "server"

# Encryption types (Path Encryption Settings)
ENC_NONE = "none"
ENC_TWOFISH = "twofish"   # management software option per docs
ENC_AES128 = "aes128"     # IP receiver option per docs
ENC_AES256 = "aes256"     # IP receiver option per docs

# Config keys
CONF_MODE = "mode"
CONF_HOST = "host"
CONF_TRANSPORT = "transport"
CONF_SEND_PORT = "send_port"
CONF_LISTEN_PORT = "listen_port"
CONF_BIND_HOST = "bind_host"
CONF_TCP_ROLE = "tcp_role"

CONF_ACCOUNT_CODE = "account_code"
CONF_COMPUTER_PASSWORD = "computer_password"
CONF_AUTH_USERNAME = "auth_username"
CONF_AUTH_PASSWORD = "auth_password"

CONF_ENCRYPTION_TYPE = "encryption_type"
CONF_ENCRYPTION_KEY = "encryption_key"

CONF_POLL_INTERVAL = "poll_interval"

CONF_INPUTS_COUNT = "inputs_count"
CONF_RELAYS_COUNT = "relays_count"
CONF_DOORS_COUNT = "doors_count"
CONF_AREAS_COUNT = "areas_count"

# Door numbering options
CONF_DOOR_FIRST = "door_first_number"
CONF_DOOR_LAST = "door_last_number"

# Relay numbering options
CONF_RELAY_RANGES = "relay_ranges"  # e.g. "1-16,21-24,49-56"

# Advanced / diagnostics options (Options Flow)
CONF_INPUT_RANGES = "input_ranges"  # e.g. "1-16,21-24,49-56" (overrides inputs_count when set)
CONF_INPUT_MAPPING_MODE = "input_mapping_mode"
INPUT_MAPPING_CTPLUS = "ctplus"
INPUT_MAPPING_LEGACY_INVERTED = "legacy_inverted"
INPUT_MAPPING_STATUS_ONLY = "status_only"
DEFAULT_INPUT_MAPPING_MODE = INPUT_MAPPING_CTPLUS

CONF_SEND_ACKS = "send_acks"
CONF_SEND_HEARTBEATS = "send_heartbeats"
CONF_HEARTBEAT_INTERVAL = "heartbeat_interval"  # seconds

CONF_MIN_SEND_INTERVAL_MS = "min_send_interval_ms"  # milliseconds between UDP frames (rate limit)
CONF_DOOR_STATUS_MODE = "door_status_mode"  # "round_robin" or "all_each_cycle"
CONF_DOOR_STATUS_PER_CYCLE = "door_status_per_cycle"  # how many doors to poll per cycle when round-robin
CONF_DOOR_POLL_STARTUP_ONLY = "door_poll_startup_only"  # only do broad door polling during initial startup sync
CONF_RUNTIME_POLLING = "runtime_polling"  # legacy broad runtime polling flag
CONF_RUNTIME_POLL_INPUTS = "runtime_poll_inputs"
CONF_RUNTIME_POLL_AREAS = "runtime_poll_areas"
CONF_RUNTIME_POLL_RELAYS = "runtime_poll_relays"
CONF_RUNTIME_POLL_DOORS = "runtime_poll_doors"
CONF_RUNTIME_POLL_RAS = "runtime_poll_ras"
DEFAULT_RUNTIME_POLLING = False
DEFAULT_RUNTIME_POLL_INPUTS = False
DEFAULT_RUNTIME_POLL_AREAS = False
DEFAULT_RUNTIME_POLL_RELAYS = False
DEFAULT_RUNTIME_POLL_DOORS = False
DEFAULT_RUNTIME_POLL_RAS = False

DEFAULT_SEND_ACKS = True
DEFAULT_SEND_HEARTBEATS = True
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 60
DEFAULT_MIN_SEND_INTERVAL_MS = 250
DEFAULT_DOOR_STATUS_MODE = "round_robin"
DEFAULT_DOOR_STATUS_PER_CYCLE = 1
DEFAULT_DOOR_POLL_STARTUP_ONLY = True
DEFAULT_DGP_DOOR_RANGES = ""
DEFAULT_RAS_DOOR_RANGES = ""
CONF_DGP_DOOR_RANGES = "dgp_door_ranges"  # e.g. "17-20,21-24,33-36"
CONF_RAS_DOOR_RANGES = "ras_door_ranges"  # e.g. "3,6,8" or "1-16"

CONF_PANEL_EXPORT_PATH = "panel_export_path"
CONF_PANEL_EXPORT_RENAME_AREAS = "panel_export_rename_areas"
CONF_PANEL_EXPORT_RENAME_INPUTS = "panel_export_rename_inputs"
CONF_PANEL_EXPORT_RENAME_DOORS = "panel_export_rename_doors"
CONF_PANEL_EXPORT_RENAME_RELAYS = "panel_export_rename_relays"
CONF_PANEL_EXPORT_RENAME_RASES = "panel_export_rename_rases"

DEFAULT_PANEL_EXPORT_PATH = ""
DEFAULT_PANEL_EXPORT_RENAME_AREAS = True
DEFAULT_PANEL_EXPORT_RENAME_INPUTS = True
DEFAULT_PANEL_EXPORT_RENAME_DOORS = True
DEFAULT_PANEL_EXPORT_RENAME_RELAYS = True
DEFAULT_PANEL_EXPORT_RENAME_RASES = True
