<img width="1983" height="793" alt="Tecom-HA-Banner" src="https://github.com/user-attachments/assets/2a9c3255-5609-4662-9141-48926897dcb0" />

# Tecom ChallengerPlus & Discovery Home Assistant Integration

A Home Assistant custom integration for **Aritech / Tecom ChallengerPlus and Discovery** panels.

This project talks to the panel using the **CTPlus / Management Software binary protocol**, built by reverse engineering CTPlus traffic, packet captures, logs, and event tables. It is a community project, and as of the 3.2.x series it runs reliably for extended periods without intervention.

> **Important**
> This is **not** an official Aritech / Tecom integration. Use it carefully, especially on live security systems. A dedicated panel comms path for Home Assistant is strongly recommended.

---

## Releases and changes

Version history, protocol findings and upgrade notes live in **[CHANGELOG.md](CHANGELOG.md)**.

Published releases with downloadable archives are on the
[Releases page](https://github.com/josh2893/TecomHA/releases).

---

## Current status

### Working well

- **Panel connection** in CTPlus / Management Software mode
- **Realtime event delivery** via `tecom_challengerplus_ctplus_event` and `tecom_challengerplus_event`
- **Inputs / zones** as binary sensors
- **Areas** as alarm control panels — arm away, arm home, disarm, with external state changes reflected back into HA
- **Relays** as switches
- **DGP doors (17+)** as lock entities with an Open / Unlock action
- **Event decoding** using CTPlus event-table data
- **Debug dump service** for troubleshooting
- **Long-run stability** — the protocol-level stalls that previously required manual recovery are resolved
- **Optional dashboard tiles** via a [companion repository](https://github.com/josh2893/TecomHA-Tiles-and-Addons)

### Still under refinement

- **Door state modelling.** The protocol distinguishes contact open/closed, secured/unsecured, locked/unlocked, auto-locked/auto-unlocked, access granted, forced, and open-too-long. Home Assistant exposes a practical subset of this richer model.

---

## Supported modes

### CTPlus / Management Software mode

The main mode, and the one most people should use. Provides inputs, areas, relays, doors, realtime events, and control functions.

### Printer / Computer Event Driven mode

More limited, mainly useful for basic event-driven monitoring. Does not expose the same level of control or structured status.

---

## Installation

### HACS

1. Open **HACS** → **Integrations**
2. Add this repository as a **Custom repository**, category **Integration**
3. Install **Tecom ChallengerPlus**
4. Restart Home Assistant

### Manual

1. Copy `custom_components/tecom_challengerplus` into `/config/custom_components/tecom_challengerplus`
2. Restart Home Assistant

Upgrading from an earlier 3.x build is a drop-in replacement with no configuration changes required.

## Dashboard tiles

A companion set of Lovelace tiles is available separately:

**[TecomHA-Tiles-and-Addons](https://github.com/josh2893/TecomHA-Tiles-and-Addons)**

It provides alarm, door and relay tiles that surface the integration's entities in a compact dashboard form — arm/force arm/disarm buttons, door lock and momentary open, reed contact state, schedule status, and last access with the user's name.

The tiles are a frontend only; all behaviour comes from the entities this integration exposes. Tile versions track integration features, so keep both reasonably current — the current tiles expect **3.3.0 or later** for force arm, alarm cause reporting and access user display.

---

## Panel programming and path setup

### Use a dedicated comms path

Home Assistant should have its **own** Management Software / CTPlus style path. Do not share a path and port with the CTPlus desktop software — one client will steal the other's traffic and troubleshooting becomes very difficult.

### Recommended path settings

Use a computer / management software style path configured for Home Assistant:

- UDP/IP
- Client / computer style operation
- Send to the Home Assistant host IP
- Matching send/receive port
- Encryption set to **None**

### Event filters matter

The path's event filter controls what Home Assistant receives. These categories are the important ones:

- alarm events
- access events
- system / communications events

If a category is filtered out, Home Assistant can still poll status but will miss the corresponding realtime events. Relay state changes in particular will only arrive if output events are enabled on the path.

---

## Authentication and encryption

The integration supports both authentication methods the panel offers, and all
three encryption ciphers. These must match the panel's comms path exactly — the
panel does not report a rejected credential or a wrong key, it simply stops
responding, so a mismatch looks like the panel being offline.

### Authentication

| Method | Notes |
|---|---|
| Security / computer password | The 10 digit password from the comms path. Panel default is `0000000000`, which cannot be used if Home Assistant connects over DHCP. |
| Path user name and password | Supported by ChallengerPlus, Discovery, NACs and Challenger from firmware V10-06.19251. Allows longer passwords and logs activity against the path user name. |

The **Authentication type** on the panel's path must match the method selected
in Home Assistant.

### Encryption

| Panel setting | Key length |
|---|---|
| AES CBC (128 bit) | up to 16 alphanumeric characters |
| AES CBC (256 bit) | up to 32 alphanumeric characters |
| TwoFish (128 bit) | up to 16 alphanumeric characters |

The key must match the panel exactly. The panel uses the key text directly, so a
longer mixed key is meaningfully stronger than a short numeric one at the same
setting.

AES is recommended where the panel allows a choice. TwoFish is supported for
panels already configured for it, but is implemented in Python and is slower.

---

## Home Assistant configuration

Options include host, transport, bind host, send/listen ports, poll interval, and the counts and ranges for inputs, doors, relays, and areas.

Guidance:

- Keep Home Assistant on the same port the panel path sends to
- Set a specific `bind_host` if Home Assistant has multiple interfaces
- Use a dedicated comms path rather than sharing with CTPlus

### Defaults

| Setting | Default |
|---|---|
| Poll interval | 1800 s (30 min) |
| Heartbeat interval | 60 s |
| Minimum send interval | 250 ms |
| Door polling | Startup only |
| Quiet mode | Enabled |
| Periodic session refresh | Disabled (12 h when enabled) |

The integration is event-driven during normal runtime. Broad polling happens once at startup and after reconnect; the long poll interval is a safety net, not the primary update mechanism.

### Importing names from a CTPlus `export.panel`

The integration can read a CTPlus `export.panel` file and apply friendly names to entities already loaded in Home Assistant. This is **name-only** — it does not create entities or remap door logic.

1. Copy `export.panel` somewhere under `/config`
2. Open the integration **Options**
3. Set **Panel export path**, e.g. `/config/export.panel`
4. Enable the rename toggles you want (areas, inputs, doors, relays, RAS)
5. Save to reload

Only objects the integration has actually loaded are renamed; entity IDs and unique IDs are left alone. Names are prefixed with the panel object number so Home Assistant keeps things sorted numerically rather than alphabetically:

- `Door 17` → `Door 17 - Front Entry`
- `Input 19` → `Input 19 - Front Entry Egress`
- `Area 2` → `Area 2 - Workshop`

---

## Entities

### Inputs (`binary_sensor`)

- **On** = unsealed / active
- **Off** = sealed / normal

Updated from a mix of event traffic and targeted status recalls.

Seal state is decoded from bits 5 and 6 of the status byte together (sealed only when both are set). This is deliberately type-agnostic: standard inputs signal unsealed by clearing bit `0x20`, while Type 20 inputs clear bit `0x40` instead. The raw status byte is exposed as an entity attribute for diagnostics.

### Areas (`alarm_control_panel`)

Supports arm away (validated), force arm via custom bypass, arm home/stay, and disarm. Changes made from a keypad, CTPlus, or a mobile app are reflected back into Home Assistant.

Stay-armed areas report as **Armed Home**. This distinction comes from the panel's event stream (`0x6C` stay, `0x0B` away) — the polled area status word only carries a single armed bit and cannot tell the two apart, so an area stay-armed before Home Assistant started may show as Armed Away until the next arm/disarm cycle.

Armed state is determined from bit 7 (`0x0080`) of the area status word, so modifier flags such as isolated inputs do not affect the reported state.

### Relays (`switch`)

Standard switches. Live state updates require output events to be enabled on the panel comms path.

### Doors (`lock` + contact sensor)

Doors are represented as a **lock entity** for control and a **Door Contact** binary sensor for contact state.

Lock and unlock latch the door until changed. **Open Door** is a separate momentary access grant that does not alter the lock mode — useful for letting someone through without leaving the door on free access.

- **DGP doors (17+)** support lock, unlock, and a separate momentary open
- **RAS doors (1–16)** are surfaced more conservatively, since a RAS may be acting as a keypad rather than a normal door controller

A Challenger door is more than open/closed — the panel tracks contact, secure, and lock state as separate concepts. Exposing that more cleanly is ongoing work.

---

## Events

Listen in **Developer Tools → Events** for `tecom_challengerplus_ctplus_event` or `tecom_challengerplus_event`.

```yaml
event_type: tecom_challengerplus_ctplus_event
data:
  code: 165
  code_hex: "0xA5"
  object: 17
  object_hex: "0x0011"
  raw: "0f0c68c8389fa511000000000000"
  text: "Door 17 Open"
  message: "Door 17 Open"
```

Where available, event-table fields are also included: `eventtable_description`, `eventtable_response_required`, `eventtable_required_2nd_response`, `eventtable_send_reset_to_panel`, `eventtable_restore_event_code`, `eventtable_update_status`, `eventtable_status_options`.

---

## Known event mappings

### Doors and access

| Code | Meaning |
|---|---|
| `0x86` | Door unlocked |
| `0x87` | Door locked |
| `0x88` | Door auto unlocked |
| `0x89` | Door auto locked |
| `0x92` | Access granted |
| `0x9D` | Access granted — egress |
| `0xA5` | Door open |
| `0xA6` | Door closed |
| `0xA7` | Door forced |
| `0xA8` | Door forced restored |
| `0xA9` | Door open too long |
| `0xAA` | Door open too long restored |
| `0xAE` | Door unsecured |
| `0xAF` | Door secured |

### Outputs

| Code | Meaning |
|---|---|
| `0x84` | Output active |
| `0x85` | Output normal |

### Inputs

| Code | Meaning |
|---|---|
| `0x96` | Unsealed (HA state: on) |
| `0x97` | Sealed (HA state: off) |

Seal state from polled status is decoded from bits 5 and 6 together — see the Inputs entity section above. Alternative mapping modes are available in the options for panels that behaved differently under earlier 2.x builds.

### Alarms

Alarm events are point-scoped and carry the area in the event body.

| Alarm | Restore | Meaning |
|---|---|---|
| `0x00` | `0x02` | Alarm |
| `0x04` | `0x05` | Secure alarm |
| `0x57` | `0x58` | Multi-break alarm |
| `0x67` | `0x68` | Exit alarm |
| `0xC2` | `0xC3` | Local alarm |

Note that `0x00` collides with "Comms - offline" in the event table; the meaning is context-dependent.

### Areas

| Code | Meaning |
|---|---|
| `0x0B` | Area armed (away) |
| `0x0C` | Area disarmed |
| `0x6C` | Area armed (stay / home) |

### Communications and modules

| Code | Meaning |
|---|---|
| `0x59` | Comms path fail |
| `0x5A` | Comms path restored |
| `0x5B` | Expander communications fault |
| `0x5C` | Expander communications restored |

---

## Services

| Service | Purpose |
|---|---|
| `tecom_challengerplus.dump_debug` | Write a JSON debug dump for all loaded hubs |
| `tecom_challengerplus.force_arm_area` | Arm an area regardless of unsealed inputs |
| `tecom_challengerplus.download_users` | Fetch user names from the panel for access events |
| `tecom_challengerplus.request_full_sync` | Force a full status sync |
| `tecom_challengerplus.retrieve_events` | Request delivery of queued panel events |
| `tecom_challengerplus.reinitialize_session` | Rebuild the CTPlus session |
| `tecom_challengerplus.reset_comms_path_event_buffer` | Clear the comms path event buffer |
| `tecom_challengerplus.send_raw_hex` | Send a raw hex payload (protocol testing) |
| `tecom_challengerplus.test_event` | Fire an internal test event |

The debug dump is the single most useful troubleshooting tool. It captures a configuration and state snapshot plus a ring buffer of recent transmitted and received frames — enough to diagnose most issues without a packet capture.

---

## Troubleshooting

### Enable debug logging

```yaml
logger:
  default: info
  logs:
    custom_components.tecom_challengerplus: debug
```

### Wireshark filters

```text
udp.port == 3001
udp.port == 3006
ip.addr == <panel_ip> && udp
```

### Common symptoms

**`Unknown` states after startup** — usually wrong path type, wrong port, encryption enabled on the panel path, or the panel not sending to the configured HA path.

**The same event repeating** — the panel still considers that event to be at the head of its queue. The known protocol causes are fixed as of 3.2.7; if you see this on a current build, capture a debug dump. Look for `last_event` beginning with `RAW`, which indicates a frame that failed to parse and therefore was never acknowledged.

**`Comms path fail` / `Comms path restored`** — these are real panel events, but historically they were a *symptom* of a stuck queue rather than a cause.

**Nothing received for minutes, then recovery** — expected behaviour if the receive watchdog fired. Check the debug dump for `rx_watchdog_restart` entries and `seconds_since_last_rx`.

**An input never leaves the off/sealed state** — on builds before 3.2.8 this affected inputs programmed as Type 20, which keep bit `0x20` set even when unsealed. Check the raw status byte in the entity attributes: if it reads `0x23` or `0x21` while the contact is open, you are seeing this bug.

**Relay states only updating on reload** — output events are filtered out on the panel comms path. Enable them in the path's event filter.

**Door state not matching the physical door** — an ongoing refinement area. The panel tracks several overlapping door concepts and sites map them differently depending on programming.

---

## Protocol notes

Things worth knowing if you want to work on this:

**The panel is queue-driven.** It keeps separate Alarm and Access event queues. If the queue head is not retired properly, the same event is resent, later events are blocked behind it, and the path may start to flap.

**Frame integrity is unforgiving.** A single misplaced byte — a `0x5E` in the wrong position, an ACK the panel can't parse — is enough to stall the queue indefinitely. Both known instances of this took protocol-level packet analysis to find, because normal operation gave no indication of what was wrong.

**CTPlus uses targeted recalls** for specific doors, inputs, areas, and DGP states rather than solving everything with broad polling. This integration follows the same approach.

**Polling should not dominate.** It is useful for startup sync and reconnect recovery, but heavy polling at the wrong moment competes with live event handling.

---

## Current limitations

- Door modelling is still evolving
- Panel object names are not pulled from the panel directly (use `export.panel` import)
- Some behaviour varies by panel programming and site-specific door logic

---

## Future work

- Cleaner separation of door contact, secure, and lock state
- Better handling of forced and open-too-long scenarios
- Investigating panel record requests for area, door, and input names

---

## Contributing

The most useful thing you can provide is a **debug dump taken while the problem is happening** — it contains the frame ring buffer, which is usually enough to identify the root cause. Packet captures are valuable too, especially of the official CTPlus software doing the same thing correctly.

Good captures are simple ones: one path, one client, one action sequence, no unrelated activity during the recording.

---

## Disclaimer

This project is community-built and reverse engineered. It is not affiliated with Aritech or Tecom. Use it carefully, test thoroughly, and treat it as an evolving integration rather than a finished commercial product.
