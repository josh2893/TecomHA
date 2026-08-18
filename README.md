<img width="1536" height="1024" alt="TECOM-CHALLENGER-FOR-HA-BANNER" src="https://github.com/user-attachments/assets/2f9fa5ed-bc6c-4c04-86b5-c18dc6daab78" />

# Tecom ChallengerPlus Home Assistant Integration

A Home Assistant custom integration for **Aritech / Tecom ChallengerPlus** panels.

This project talks to the panel using the **CTPlus / Management Software binary protocol**, built by reverse engineering CTPlus traffic, packet captures, logs, and event tables. It is a community project, and as of the 3.2.x series it runs reliably for extended periods without intervention.

> **Important**
> This is **not** an official Aritech / Tecom integration. Use it carefully, especially on live security systems. A dedicated panel comms path for Home Assistant is strongly recommended.

---

## Version 3.3.2

Fixes the issues reported against 3.3.0.

### Access events now name the user in Activity

Home Assistant's Activity feed renders an event entity's `event_type` and nothing else, so a card swipe showed only `access_granted` even though the user was present in the entity's attributes. A logbook platform lets the integration write its own lines:

| Situation | Activity line |
|---|---|
| Card, name synced | `Access granted - J. Smith` |
| Card, sync off | `Access granted - user 2307` |
| Panel opened the door | `Access granted - system` |
| Exit button | `Access granted (exit button)` |
| Door forced | `Door forced` |
| Open too long | `Door open too long` |

Door exceptions carry no attribution, since a forced door has no user by nature. Lines attach to the door's access event entity, so filtering Activity by that entity still works.

Home Assistant may render both this line and the event entity's own `access_granted` line. To show only the descriptive one:

```yaml
logbook:
  exclude:
    entity_globs:
      - event.*_access
```

### Duplicate per-input alarm entities removed

3.3.0 added a separate `_alarm` binary sensor for every input, which on a 26-input panel doubled the entity list for information that could have lived on the existing sensor.

Alarm state is now an attribute on the input sensor:

| Attribute | Meaning |
|---|---|
| `in_alarm` | Whether this input is currently in alarm |
| `alarm_area` | The area it belongs to, when in alarm |
| `alarm_area_name` | Friendly name of that area |

Use `state_attr('binary_sensor.input_6', 'in_alarm')` in templates and automations. Area-level reporting is unchanged.

After upgrading, the old `_alarm` entities show as unavailable and can be removed under Settings → Devices & Services → Entities.

### Card user no longer masked by a following access

The access event entity reports the most recent event, so where a door emits a second access shortly after a card read — an interlock, a macro, or an exit-button grant — the credentialed access was immediately overwritten.

The last access carrying a credential is now tracked per door and exposed as `last_user` and `last_user_name` alongside the current event's `user` / `user_name`.

### Debug dumps diagnose access and user sync

A `user_sync` block reports enabled state, startup and periodic settings, interval, time since last successful sync, download progress, known user count, and whether the cache was restored from storage.

An `access` block logs the last 40 decoded access events:

```json
{ "door": 17, "code": "0x92", "kind": "granted",
  "user": 2307, "name_known": true, "raw_user_bytes": "0309" }
```

`raw_user_bytes` is bytes 10-11 of the event body verbatim — `"0000"` means the panel reported no credential, so nothing was lost in decoding. A `summary` counts events with and without a user, egress events, and names resolved. `last_credentialed` shows the most recent carded access per door with its age.

`input_alarms` and `area_alarms` are also included.

User names are never written to a dump — only numbers, counts, and a `name_known` flag, since dumps get attached to issue reports.

---

## Version 3.3.0

Door control, area arming, alarm detection, and access events with user names. Every command in this release was confirmed against a packet capture of the official software rather than inferred.

### Door lock and unlock are now real commands

The lock entity previously only ever sent one thing. `unlock` and `open` both issued the momentary access command, and `lock` did nothing at all — so the lock/unlock slider and the Open Door button behaved identically and the door never actually latched.

Door control uses the form `04 02 <action> <door>`:

| Action | Byte | Panel confirms with |
|---|---|---|
| Lock | `0x01` | `0x87` Door locked, then `0xAF` Door secured |
| Unlock | `0x02` | `0x86` Door unlocked, then `0xAE` Door unsecured |
| Momentary open | `0x04` | access grant, lock mode unchanged |

Lock and unlock latch the door until changed; Open Door remains a momentary release that leaves the lock mode alone.

### Arm, Force Arm, and Arm Home

Area control uses the form `02 02 <action> <area>`. Earlier builds used the forcing action for everything and sent an unverified byte for arm home:

| Action | Byte | Behaviour | Panel confirms with |
|---|---|---|---|
| Disarm | `0x05` | | `0x0C` Area disarmed |
| Arm | `0x09` | Validates first; refused if any input is unsealed | `0x0B` Area secured |
| Force arm | `0x06` | Arms regardless of unsealed inputs | `0x0B` Area secured |
| Arm home / stay | `0x0A` | | `0x6C` Area secured stay |

- **Arm away** sends the validated arm (`0x09`)
- **Custom bypass** sends force arm (`0x06`), which is what arm away used to do
- The `tecom_challengerplus.force_arm_area` service also force-arms

A refused action is decoded and reported rather than silently leaving the optimistic armed state in place. The area rolls back and a `tecom_challengerplus_control_failed` event fires with the action, reason, object number and object name.

Stay-armed areas now report as **Armed Home**. Event code `0x6C` was previously unhandled, so a stay-armed area fell through and displayed as Armed Away.

### Alarm detection

Nothing previously detected an alarm. The alarm panel entity had a `TRIGGERED` state but nothing ever set it, so an area in alarm continued to display as simply armed.

Plain zone alarm is event code `0x00`. This was not identifiable from the shipped event table, where `(0, 0)` is "Comms - offline" — the code is context-dependent.

Alarm codes are point-scoped, but the event body carries the area alongside the object, so no zone-to-area mapping is required:

```
0F 0C <timestamp x4> <code> <object:2> <area> <user>
```

| Alarm | Restore | Meaning |
|---|---|---|
| `0x00` | `0x02` | Alarm |
| `0x04` | `0x05` | Secure alarm |
| `0x57` | `0x58` | Multi-break alarm |
| `0x67` | `0x68` | Exit alarm |
| `0xC2` | `0xC3` | Local alarm |

An area with any point in alarm reports `TRIGGERED` and lists the offending points in its `alarm_inputs` and `alarm_input_names` attributes. Individual inputs expose `in_alarm` (plus `alarm_area`) as attributes on the existing input sensor rather than as extra entities. When the last alarm clears the area returns to the mode it held beforehand. Status polling no longer overwrites an alarm or stay-armed state.

### Access events in Activity

Access activity was already being received and fired on the event bus, but had nowhere to surface — the Activity feed shows entity state changes, and a card swipe changes no entity.

Each door now has an **Access** event entity:

| Code | Event type |
|---|---|
| `0x92` | `access_granted` |
| `0x9D` | `access_granted_egress` |
| `0xA7` | `door_forced` |
| `0xA9` | `door_open_too_long` |

The user number is a 16-bit little-endian value at bytes 10-11, and is read only on access codes — other event types use those bytes for unrelated fields.

Access events appear in the Activity feed with the user named — `Access granted - J. Smith` — via a logbook platform. Without it Home Assistant renders only the bare `event_type`, since the Activity feed does not read entity attributes.

A user of 0 means the panel opened the door itself — a macro-driven unlock rather than a presented credential. These are genuine accesses and are reported as such with no user attached.

Because a panel-initiated access often lands within a second of a real card read, the last access that *did* carry a credential is preserved separately and exposed as `last_user` / `last_user_name`, so who badged is not immediately masked.

### User name sync

The user number is carried at bytes 10-11 of the event body, but the name is not on the wire. The panel supplies the mapping on request:

```
Request:   25 05 1D <start:2 LE> FF FF
Response:  7D <len> 1D 2B <record x 2>     43 bytes per record
End:       empty acknowledgement
```

User name sync is **off by default** and configurable from both the setup wizard and the options screen:

| Setting | Default | Purpose |
|---|---|---|
| Sync user names from panel | Off | Master switch for the feature |
| Sync users on startup | On | Refresh each time the integration starts |
| Periodically re-sync users | Off | Also re-sync on a schedule |
| User re-sync interval | 24 h | How often, when periodic sync is on |

Names are cached to Home Assistant storage, so access events stay labelled across restarts without waiting for a download. A **Sync Users Now** button and the `tecom_challengerplus.download_users` service both trigger an immediate refresh.

**Only user numbers and names are read.** Each panel record also contains card and PIN material; that is deliberately never extracted, so none of it reaches memory, storage, or debug dumps. Names are limited to 16 characters by the panel itself.

---

## Version 3.2.8

### Input seal state now decoded with a two-bit mask

Bits 5 (`0x20`) and 6 (`0x40`) of the input status byte together carry the seal indication, and which of the two clears when an input goes unsealed depends on how that input is programmed on the panel:

| Byte | Bits 6:5 | Meaning |
|---|---|---|
| `0x63` / `0x61` | `11` | Sealed |
| `0x43` | `10` | Unsealed — standard input types |
| `0x23` / `0x21` | `01` | Unsealed — Type 20 (input to activate event flag, 24 hour) |

Earlier builds tested bit `0x20` alone. A Type 20 input keeps that bit set in both states, so it reported **permanently sealed** regardless of the physical contact — and because status polling runs continuously, it would overwrite the correct state that the panel's own `0x96`/`0x97` events had just delivered.

Seal state is now derived from the mask, which is type-agnostic. Validated against every recorded status sample paired with the panel's own seal events: all bit-level disagreements resolved.

Anything that is not an explicit sealed pattern is reported as active, so an unexpected or fault condition stays visible rather than being indistinguishable from a closed contact.

### Event decoder no longer mis-reads timestamps as event data

`parse_event()` tried a loose scan for byte `0x8A` before checking the anchored `0F 0C` frame form. Event bodies carry a four-byte timestamp that regularly contains `0x8A`, so well-formed events were being silently mangled:

```
0f0c88488a4da511000000000000
        ^^ 0x8A inside the timestamp
```

That decoded as code `0x4D` object 4517 instead of `0xA5` object 17 — *Door 17 Open*. When the bytes following a timestamp `0x8A` happened to land on an area arm/disarm code, it also wrote phantom area numbers into state built out of timestamp bytes (an `Area 38404` was observed).

The anchored form is now checked first, with the `0x8A` scan kept only as a fallback.

---

## Version 3.2.7

This release closes out the last known protocol-level failure mode — a stall where the panel's event queue would stop draining and could only be cleared by disabling and re-enabling the comms path, then reloading the integration.

### Byte-stuffing now covers the full frame

The protocol uses `0x5E` as the frame sync marker and escapes any literal `0x5E` elsewhere in the frame as `0x5E 0xFF`. Earlier builds applied this rule only from the body onward, treating the first five bytes (sync, type, flags, seq) as a fixed-width header.

That breaks when the sequence counter reaches `0x5E`:

```
5e 40 80 00 5e ff 0f 0c ...
^^ sync      ^^ seq = 0x5E
                ^^ escape byte for the seq
```

The escape byte was absorbed as the first body byte, the CRC check failed, and the frame fell through to the unparsed path — which never sends an ACK. The panel retransmitted indefinitely and the queue stalled.

The transmit path had the same gap in reverse: an ACK for seq `0x5E` went out with the seq byte unescaped, so the panel read it as a sync marker and discarded it. The stall could not be broken from either direction.

Stuffing and unstuffing now apply to everything after the sync byte. This closes the second of two sequence values that could wedge the comms path — the first (`0x36`, where the *CRC* contained `0x5E`) was fixed earlier in the 3.2.x series.

Validated against 3990 frames captured across recorded failure and steady-state sessions: zero regressions, 45 previously unparseable frames now decode. Exhaustively round-trip tested across 16,384 combinations of frame type, sequence value, and payload.

### Receive watchdog

The integration sent heartbeats but never checked whether the panel was answering. After a network interruption or a wedged session it would keep transmitting into a dead socket until manually reloaded.

The heartbeat loop now tracks time since the last received frame. If nothing arrives for 4× the heartbeat interval (minimum 120 seconds), the transport is restarted and the session reinitialised, with a 180-second cooldown to prevent restart loops.

This covers silent dropouts specifically. It will not fire during a queue stall, where frames are still arriving — the two fixes address different failure modes.

### Also in the 3.2.x series

- **Area armed/disarmed detection** now tests bit 7 (`0x0080`) of the area status word instead of matching against a list of known-disarmed values. Areas with isolated inputs (`0x0004`) were previously reported as armed on startup.
- Debug dumps include `seconds_since_last_rx` and `rx_watchdog_timeout`.
- Watchdog restarts are recorded in the frame ring buffer as `rx_watchdog_restart:no_rx_for_<n>s` and logged at warning level.

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

- **Door state modelling.** The protocol distinguishes contact open/closed, secured/unsecured, locked/unlocked, auto-locked/auto-unlocked, access granted, forced, and open-too-long. Home Assistant currently exposes a practical subset of this richer model.
- **Door contact detection.** Much improved, but still best-effort. Some installations may need tuning to cleanly separate physical contact state from secure/lock state.

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
- Encryption is not implemented for CTPlus mode
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

## Version history

### 3.3.2
Removed the duplicate per-input alarm entities in favour of an `in_alarm` attribute. Added a logbook platform so access events name the user in the Activity feed. Preserved the last credentialed access per door so a following access no longer masks who badged. Added access and user-sync diagnostics to debug dumps.

### 3.3.0
Door lock/unlock as distinct commands. Arm, force arm, and arm home/stay separated and corrected. Alarm detection with per-input alarm sensors and area `TRIGGERED` state. Door access event entities with optional user name sync from the panel.

### 3.2.8
Input seal state decoded via the `0x60` two-bit mask, fixing Type 20 inputs that reported permanently sealed. Event decoder no longer mistakes timestamp bytes for event codes.

### 3.2.7
Full-frame byte-stuffing fix (sequence value `0x5E`); receive watchdog for automatic recovery from silent dropouts.

### 3.2.x
Byte-stuffing fix for CRC values containing `0x5E` (sequence value `0x36`) — the original cause of multi-hour comms failures. Area armed state detection via bit 7 instead of a value whitelist.

### 3.1.8
Parser support for byte-stuffed event frames. Startup does one controlled full sync then stays event-driven. Quiet mode toggle and session quiet-mode recovery. `0x49` backoff handling.

### 3.0.6
CTPlus-style quiet idle behaviour with 60-second heartbeats. Automatic UDP transport rebuild on repeated panel retries. Door lock entities restore state after reload.

### 2.0.70
Relay switches grouped under the Tecom device with debug attributes. Door lock entities prefer explicit lock/secure events over the raw door word.

---

## Disclaimer

This project is community-built and reverse engineered. It is not affiliated with Aritech or Tecom. Use it carefully, test thoroughly, and treat it as an evolving integration rather than a finished commercial product.
