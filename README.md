# Tecom ChallengerPlus (CTPlus) Home Assistant Integration (Experimental)

This is an **experimental** custom integration based on observed CTPlus ↔ ChallengerPlus packet captures with **Encryption=None**.

## Implemented in v0.2.0 (this zip)
- **Inputs**
  - Poll status (request range) and update HA binary_sensors
  - Real-time events: sealed (0x96) / unsealed (0x97)
- **Relays**
  - Control: set/reset (0x03 0x03)
  - Poll status (0x66/0x67) and real-time events: on (0x84) / off (0x85)
- **Areas**
  - Control: arm away (0x02 0x02 0x06) / disarm (0x02 0x02 0x05)
  - Real-time events: armed (0x0B) / disarmed (0x0C)
- **Doors**
  - Control: unlock/open (0x04 0x02 0x04 <door>)
  - Door state is best-effort (audit events may be seen, but not treated as lock state).

## Notes
- The integration currently expects **UDP/IP** and a fixed port (commonly 3001) like CTPlus.
- If you enable encryption on the panel path, the integration will refuse to start (encryption not implemented yet).
- TCP mode is experimental.
