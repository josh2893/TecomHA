<img width="1536" height="1024" alt="TECOM-CHALLENGER-FOR-HA-BANNER" src="https://github.com/user-attachments/assets/89b5e061-2192-4047-ad73-23bc7123234a" />

## Tecom ChallengerPlus Home Assistant Integration

A Home Assistant custom integration for **Aritech / Tecom ChallengerPlus** panels.

This project talks to the panel using the **CTPlus / Management Software binary protocol** and exposes panel state and control inside Home Assistant. It is a **community reverse-engineered integration**, not an official Aritech / Tecom product.

The integration has been built and refined from:

- CTPlus packet captures
- panel event tables
- protocol analysis of live ChallengerPlus traffic
- comparison against CTPlus behaviour over long runtimes

> [!IMPORTANT]
> This integration is intended for users who understand their panel programming and network path configuration.
> Use a **dedicated comms path** for Home Assistant wherever possible.

---

## Version 3.2.6 highlights

Version **3.2.6** is the current stable release and includes the long-running CTPlus comms-path stability fix.

### Major stability fix
A long-standing issue could cause the panel event queue to wedge after hours or days of runtime. The root cause was an outgoing ACK/heartbeat framing edge case:

- Challenger uses `0x5E` as the frame sync marker.
- Some outgoing ACK frames could legitimately contain `0x5E` inside the payload/CRC portion.
- The panel could misread that byte as a new frame sync and discard the ACK.
- The event then stayed at the head of the queue and retried forever, eventually causing **path fail / too many event tries** behaviour.

Version 3.2.6 fixes this by applying the required **outgoing byte-stuffing** rule after the header so literal `0x5E` bytes are transmitted safely.

### Also included in the current stable branch

- Startup **full state bootstrap** followed by quieter **event-driven runtime**
- Configurable **runtime polling groups** for inputs, areas, relays, doors, and RAS objects
- **Periodic session refresh** option for long-running CTPlus sessions
- CTPlus event decoding using bundled event-table data
- Import of friendly names from a CTPlus `export.panel`
- Debug dump service for support and reverse engineering
- Manual recovery / maintenance services such as full sync, session reinitialisation, and comms-path event-buffer reset

---

## Current status

### Working well in CTPlus / Management Software mode

- Realtime CTPlus event delivery
- Inputs / zones as binary sensors
- Areas as alarm control panels
- Relays as switches
- DGP doors as door-control lock entities with **Open** support
- RAS / keypad door objects as door entities and optional contact-style sensors
- Friendly naming from `export.panel`
- Debug JSON dumps for troubleshooting

### Still best described as practical / best-effort

- Some of the underlying Challenger door model is richer than Home Assistant's entity model
- Physical door open/closed state is best represented by the actual reed/input where available
- Printer mode is intentionally much more limited than CTPlus mode

---

## Supported modes

### 1. CTPlus / Management Software mode
This is the main mode and the recommended mode for most users.

It provides:

- live events
- state bootstrap and refresh
- areas
- inputs
- relays
- doors
- control functions

### 2. Printer / Computer Event Driven mode
This is a more limited text-event mode.

It is useful for:

- basic event monitoring
- simpler integrations
- environments where CTPlus mode is not available

It does **not** provide the same structured state model or control capability as CTPlus mode.

---

## Installation

### HACS

1. Open **HACS**
2. Go to **Integrations**
3. Add this repository as a **Custom repository**
4. Category: **Integration**
5. Install **Tecom ChallengerPlus**
6. Restart Home Assistant

### Manual install

Copy `custom_components/tecom_challengerplus` to:

```text
/config/custom_components/tecom_challengerplus
```

Then restart Home Assistant.

No YAML configuration is required.

---

## Recommended panel setup

### Use a dedicated CTPlus / Management Software path
Do **not** share the same management path between CTPlus desktop software and Home Assistant.

Recommended approach:

- **CTPlus desktop** on one path/port
- **Home Assistant** on a separate path/port

This makes troubleshooting easier and avoids clients interfering with each other.

### Recommended path characteristics

For CTPlus mode, use a path configured like a **Management Software / Computer** style connection, typically:

- **UDP/IP** transport
- Home Assistant host IP as the destination
- matching panel and HA ports
- **Encryption = None**

> [!NOTE]
> The config flow exposes encryption settings for completeness, but encrypted CTPlus transport is **not implemented** in this integration. Use **None**.

### Event filters matter
If the panel path is filtering out events, Home Assistant may still connect but important realtime updates will be missing.

In practice, make sure the path includes the event categories you actually care about, especially:

- alarm events
- access events
- system / comms events

---

## Home Assistant configuration

The integration uses the UI config flow and options flow.

### Important options

#### Connection
- **Mode**
- **Host**
- **Transport**
- **Panel port**
- **Local listen port**
- **Local bind address**
- **TCP role** if using TCP

#### Object layout
- **Input ranges** or input count
- **Area count**
- **Relay ranges** or relay count
- **DGP door ranges**
- **RAS door numbers**

#### Runtime behaviour
- **Runtime polling interval**
- **Enable runtime polling** per object group
- **Runtime door polling mode**
- **Doors polled per runtime cycle**
- **Send heartbeats**
- **Heartbeat interval**
- **Minimum delay between host frames**

#### ACK / session tuning
- **Panel ACK delay**
- **Enable follow-up ACK for repeated retries**
- **Follow-up ACK delay**
- **Enable quiet-mode retry backoff**
- **Enable periodic session refresh**
- **Periodic session refresh interval (hours)**

### General guidance

- Leave runtime polling conservative unless you have a good reason to enable more of it.
- The integration always performs a **startup state sync** after connecting.
- Runtime polling options control **ongoing** refresh behaviour after startup.
- For older or more sensitive panels, a small **Panel ACK delay** such as **20-25 ms** may behave better than instant ACKs.

---

## Entities created

### Inputs / zones
Created as **binary sensors**.

- Entity type: `binary_sensor`
- Example: `binary_sensor.input_17`
- Includes useful raw status attributes and event metadata

The default CTPlus input mapping is:

- `0x96` = **Unsealed** = `on`
- `0x97` = **Sealed** = `off`
- status byte `0x20` = sealed / normal

Alternative input mapping modes are available in the options flow for panels or legacy setups that need different behaviour.

### Areas
Created as **alarm control panels**.

Supported actions:

- arm away
- arm home
- disarm

State changes coming from outside Home Assistant are reflected back into HA.

### Relays
Created as **switches**.

Supported actions:

- turn on
- turn off

### DGP doors
Created as **lock entities** with **Open** support.

Important notes:

- These entities are primarily for **door control / release** semantics.
- Lock state is derived from explicit CTPlus secure/lock style events where possible.
- Physical contact state is **not** modelled as a separate DGP door contact entity by default.
- If you have a real door reed wired as an input, that input is usually the best source of truth for open/closed automations.

### RAS / keypad / simple controller doors
Created as:

- **lock entities** for the RAS object itself
- **binary sensors** for configured RAS contact-style status

These are exposed on a best-effort basis because RAS status is not the same as a full DGP door model.

### Last event sensor
A single sensor is created for the most recent decoded event.

- Entity type: `sensor`
- Name: **Last event**

It includes attributes such as:

- last event code
- last event object
- raw event hex
- input mapping mode

---

## Event bus events

The integration fires Home Assistant events that can be used in automations or diagnostics.

### `tecom_challengerplus_event`
General event stream.

- In printer mode, this carries raw text events.
- In CTPlus mode, this carries decoded CTPlus event payloads.

### `tecom_challengerplus_ctplus_event`
Extra CTPlus-specific event stream for easier filtering in automations.

Typical payload fields include:

- `code`
- `code_hex`
- `object`
- `object_hex`
- `raw`
- `text`
- `message`
- event-table metadata when available

### `tecom_challengerplus_raw`
Low-level raw protocol data for troubleshooting and reverse engineering.

### `tecom_challengerplus_test`
Generated by the built-in test service.

---

## Services

The integration registers several services.

### `tecom_challengerplus.request_full_sync`
Run a broad CTPlus-style state refresh for the selected panel.

### `tecom_challengerplus.reinitialize_session`
Re-send the CTPlus session hello, session parameters, and door-status init sequence.

This is a **soft** session recovery / refresh, not a panel comms-path reset.

### `tecom_challengerplus.reset_comms_path_event_buffer`
Maintenance action that sends the CTPlus maintenance command used to clear/reset the current comms-path event buffer.

This is **not** intended for normal runtime use.

### `tecom_challengerplus.retrieve_events`
Legacy alias for `reset_comms_path_event_buffer`.

### `tecom_challengerplus.dump_debug`
Write a debug JSON file for support and analysis.

### `tecom_challengerplus.send_raw_hex`
Send an arbitrary raw hex payload to the panel.

This is intended for protocol testing and reverse engineering.

### `tecom_challengerplus.test_event`
Fire an internal Home Assistant test event.

> [!TIP]
> If you have more than one Tecom entry loaded, pass `entry_id` to the service call so the correct panel is targeted.

---

## Importing names from a CTPlus `export.panel`

The integration can optionally read a CTPlus `export.panel` file and use it to apply friendly names to entities that are **already loaded in Home Assistant**.

This import is intentionally **name-only**.

It does **not**:

- create extra entities
- load objects that are outside your configured ranges
- change entity IDs or unique IDs

It only updates the friendly/display names of objects that the integration has already loaded.

### How to use it

1. Copy `export.panel` somewhere inside Home Assistant, for example:

```text
/config/export.panel
```

2. Open the integration **Options**
3. Set **CTPlus export.panel path**
4. Enable the rename toggles you want:
   - areas
   - inputs
   - doors
   - relays
   - RAS
5. Save the options so the integration reloads

### Naming behaviour
Imported names are intentionally prefixed with the object number, for example:

- `Door 17 - Front Door`
- `Input 19 - Front Door Egress`
- `Area 2 - Warehouse`

This keeps Home Assistant objects grouped and sortable by panel number.

---

## Debugging

The integration includes a debug dump service designed for support and reverse engineering.

### What the debug dump includes

Depending on the current build, the dump can include:

- current config snapshot
- live state snapshot
- recent RX/TX frame history
- last event details
- repeated-event tracking
- ACK timing and related diagnostics

This has been especially useful for comparing Home Assistant behaviour against CTPlus over long runtimes.

### Suggested troubleshooting approach

When something goes wrong:

1. Trigger `tecom_challengerplus.dump_debug`
2. Save the JSON file before making panel changes
3. If relevant, also capture CTPlus traffic on a separate management path
4. Compare:
   - repeated event frames
   - ACK timing
   - whether the panel path is still alive
   - what the last successful events were

---

## Known limitations

- This is a **reverse-engineered** integration, not an official Tecom/Aritech product.
- **Encryption is not implemented**. Use `None`.
- CTPlus / Management Software mode is the primary target; Printer mode is intentionally limited.
- Challenger door semantics are richer than the current HA entity model, so some door-related state is necessarily simplified.
- The integration exposes a practical and useful subset of the protocol rather than every possible panel function.

---

## Recommended usage notes

- Use a **dedicated comms path** for Home Assistant.
- Prefer **UDP with encryption disabled** unless you specifically need TCP.
- Keep runtime polling modest and let the event stream do most of the work.
- Use actual input/reed sensors for physical door open/closed automations when available.
- Treat `reset_comms_path_event_buffer` as a maintenance tool, not a normal runtime action.

---

## Disclaimer

This software is provided as-is, without warranty.

Test carefully before relying on it in a live security environment.

If you find a protocol quirk, packet capture and debug data are extremely valuable for improving the integration.
