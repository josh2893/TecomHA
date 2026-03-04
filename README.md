# Tecom ChallengerPlus Home Assistant Integration (Experimental)

A Home Assistant custom integration for **Aritech / Tecom ChallengerPlus** panels.  
It talks to the panel using **CTPlus / “Management software” binary protocol** (reverse‑engineered from packet captures).

> ⚠️ **Experimental / community project**  
> This is **not** an official Aritech/Tecom integration. It’s built from observed traffic and may not cover every panel feature or firmware variation. Test in a safe environment before relying on it.

---

## What you get

### CTPlus / Management mode (recommended)
- **Inputs** → `binary_sensor` (polling + real‑time sealed/unsealed events)
- **Relays** → `switch` (on/off control + status)
- **Doors** → `lock` (momentary **unlock/open** command)
  - Lock state is **best‑effort** (panel doesn’t expose a clean “locked/unlocked” bit in the current mapping)
- **Areas** → `alarm_control_panel` (arm away / disarm + status events/polling)
- **Events (Developer Tools → Events)**
  - `tecom_challengerplus_event`
  - `tecom_challengerplus_ctplus_event` (same payload, easier to filter)
- **Services**
  - `tecom_challengerplus.send_raw_hex` (protocol testing / reverse engineering)
  - `tecom_challengerplus.test_event` (fires a test HA event)

### Printer mode (events only)
- Supports the “Printer / Computer Event Driven” style text stream
- **No control** (no doors/relays/areas), events only

---

## Requirements / assumptions

- Panel reachable on your LAN (ideally same VLAN or permitted by firewall rules)
- **Encryption set to `None`** on the panel path used for CTPlus mode
  - (Twofish/AES not implemented yet)
- A dedicated panel “computer”/CTPlus style path configured for Home Assistant

---

## Installation

### Option A — HACS (recommended)
1. HACS → **Integrations** → **⋮** → **Custom repositories**
2. Add your repo URL (e.g. `https://github.com/josh2893/TecomHA/wiki/README`)
3. Category: **Integration**
4. Install **Tecom ChallengerPlus**
5. Restart Home Assistant

### Option B — Manual
1. Copy `custom_components/tecom_challengerplus/` into:
   - `/config/custom_components/tecom_challengerplus/`
2. Restart Home Assistant

---

## Panel programming (important)

### Use a dedicated CTPlus/Computer interface for Home Assistant
Create/configure a comms path specifically for Home Assistant **using CTPlus/Computer Event Driven style settings**.

Typical settings (panel-side):
- **UDP/IP**
- **Client**
- **Send to address:** your HA host IP
- **Send port / Receive port:** choose a dedicated port (example: `5051`)
- **Encryption:** `None`
- **Account code / Computer password:** set and keep consistent with HA config

### Running CTPlus software and Home Assistant at the same time
You can run both **as long as you do NOT share the same port/path**.

Example:
- **CTPlus PC**: Comms Path 3, port `3001`
- **Home Assistant**: Comms Path 1, port `5051`

This matches Tecom’s guidance that ports should not be shared by other management software.

---

## Home Assistant setup

1. Settings → Devices & Services → **Add integration**
2. Search: **Tecom ChallengerPlus**
3. Configure:

### Common fields
- **mode**
  - `CTPlus / Management software (binary protocol)` *(recommended)*
  - `Printer / Computer Event Driven` *(events only)*
- **host**: panel IP address
- **transport**: UDP/IP recommended (TCP is experimental)
- **send_port / listen_port**
  - For CTPlus mode, these must match the **panel path you configured for Home Assistant**
  - Example: `5051` / `5051`
- **bind_host**
  - Usually `0.0.0.0`
  - If HA has multiple interfaces/VLANs, set it to the specific HA IP used by the panel path
- **poll_interval**
  - Default `10` seconds
  - If you see intermittent supervision/path dropouts, try `5`

### Entity creation (counts/ranges)
These control which entities Home Assistant creates:

- **inputs_count**  
  Creates `Input 1 … Input N`
- **areas_count**  
  Creates `Area 1 … Area N`
- **door_first_number / door_last_number**  
  Creates `Door X … Door Y` (inclusive). Set last to `0` to disable doors.
- **relays_count**  
  Creates `Relay 1 … Relay N`
- **relay_ranges** *(optional)*  
  Overrides relays_count using ranges like: `1-16,21-24,49-56`

> After changing options, Home Assistant may reload the integration. If you still see stale entities, restart HA once.

---

## How entities behave

### Inputs (`binary_sensor`)
- **ON** = **Unsealed / Active**
- **OFF** = **Sealed / Normal**

### Doors (`lock`)
- **Unlock/Open** triggers the panel’s “open door” command (momentary unlock)
- **Lock** is currently a no-op (to avoid UI errors)

### Areas (`alarm_control_panel`)
- Supports:
  - Arm Away
  - Disarm
- State mapping is best-effort; raw protocol values may be exposed via logs during development

### Relays (`switch`)
- ON/OFF control + status

---

## Events

Developer Tools → Events → listen to:
- `tecom_challengerplus_ctplus_event`

Example payload:
```yaml
event_type: tecom_challengerplus_ctplus_event
data:
  code: 144
  code_hex: "0x90"
  object: 16
  object_hex: "0x10"
  raw: "0f0c63c884ab5a10000000010000"
  message: "CTPlus event 0x90 object 16 (0x10)"
```

The `message` field is a best-effort decoder and will improve over time.

---

## Debug logging / troubleshooting

### Enable debug logs
Add to `configuration.yaml`:
```yaml
logger:
  default: info
  logs:
    custom_components.tecom_challengerplus: debug
```
Restart Home Assistant and check Settings → System → Logs.

### Common issues

**1) “Comms path fail/restored” events in CTPlus**
- Wrong port configured (panel path and HA ports must match)
- Port conflict (CTPlus software and HA sharing the same port)
- Encryption enabled on the panel path (must be None for CTPlus mode)
- Firewall/VLAN rules blocking UDP

**2) Entities stuck as `Unknown`**
- Panel not replying on the configured port/path
- Wrong account code / computer password
- Wrong comms path type (must be a CTPlus/Computer interface style path for CTPlus mode)

**3) Door open causes unexpected egress/input behavior**
- Usually indicates panel input wiring/config/timers (EOL/NO/NC/REX timing), not HA “changing config”
- Confirm Input type/EOL settings in CTPlus for the affected input

### Capturing traffic (Wireshark)
Filter examples:
- `udp.port == 5051`
- `ip.addr == <panel_ip> && udp`

---

## Security notes
- This integration is intended for **local network** use.
- CTPlus mode currently runs **without encryption** (panel path encryption must be None).
- Use VLANs/firewall rules to limit access to the panel interface where possible.

---

## Support / contributing
- Issues: use the repo issue tracker
- PRs welcome (pcaps and log snippets are extremely helpful)

---

## Disclaimer
This project is community-driven and **not affiliated with Aritech/Tecom**.  
Use at your own risk—especially in environments where security/alarm availability is critical.
