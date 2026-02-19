"""Constants for the Tecom ChallengerPlus integration."""

DOMAIN = "tecom_challengerplus"

# Defaults align with Tecom docs that commonly use port 3001 for IP comms.
DEFAULT_SEND_PORT = 3001
DEFAULT_LISTEN_PORT = 3001

DEFAULT_POLL_INTERVAL_SECONDS = 10

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
