# Tecom ChallengerPlus Home Assistant Integration

A Home Assistant custom integration for **Aritech / Tecom ChallengerPlus** panels.

This project talks to the panel using the **CTPlus / Management Software binary protocol** and has been built by reverse engineering CTPlus traffic, packet captures, logs, and event tables. It is a community project and is still evolving, but it is now far enough along to be genuinely useful for monitoring and a fair bit of control.

> **Important**
> This is **not** an official Aritech / Tecom integration. Use it carefully, especially on live security systems. A dedicated panel path for Home Assistant is strongly recommended.

---

## Version 3.0.2 highlights

- New **session quiet-mode recovery** for CTPlus-style comms path protection.
  - When the same queued panel event is retried repeatedly, the integration now stops host-initiated recalls for a while and leaves only heartbeats + immediate event ACKs running.
  - This is designed to mimic CTPlus/ARES behaviour more closely when the panel is under retry pressure.
- A short **0x49 backoff** path has been added. If the panel starts replying to recalls with short `0x49` frames, the integration treats that as a signal to back off instead of continuing to poll.
- After quiet mode, the integration performs a slower **session reinitialisation** and backlog drain before broad status sync resumes.
- Safer defaults aimed at Challenger management-path stability:
  - poll interval = **30 seconds**
  - min send interval = **250 ms**
  - door polling = **startup only** by default

- Door lock/release state now only comes from explicit CTPlus secure/lock events; it no longer guesses from the door contact/status word.
- Door secure/unlock caches are cleared on session reinitialisation/reconnect so stale door-release states are less likely after reconnects.
- Debug dumps now include `door_secure` and `door_lock` maps for easier troubleshooting.


- CTPlus-style **session reinitialisation** with paced hello / params / door-status init
- **Immediate ACK support on both UDP and TCP** transports
- Better **TCP client reconnect** behaviour
- Official CTPlus-style default input mapping:
  - `0x96 = Unsealed = on`
  - `0x97 = Sealed = off`
  - status byte `0x20 = sealed / normal`
- New selectable **input mapping mode** options for panels that behaved differently in earlier 2.x builds
- New services:
  - `tecom_challengerplus.request_full_sync`
  - `tecom_challengerplus.retrieve_events`
  - `tecom_challengerplus.reinitialize_session`
- RAS / keypad door contacts can now be surfaced as binary sensors when configured
- Expanded debug / last-event metadata for troubleshooting

---

## Current status

### Working well
- **Panel connection in CTPlus / Management Software mode**
- **Realtime event delivery** into Home Assistant via:
  - `tecom_challengerplus_ctplus_event`
  - `tecom_challengerplus_event`
- **Inputs / zones** as binary sensors
- **Areas** as alarm control panels
  - arm away
  - arm home
  - disarm
  - state updates from outside Home Assistant are reflected back into HA
- **Relays** as switches
- **DGP doors (17+)** as lock entities with an **Open / Unlock** action
- **Event decoding** using CTPlus event-table data for many common event types
- **Debug dump service** for reverse engineering and troubleshooting

### Working, but still under active refinement
- **Door state modelling**
  - The protocol clearly distinguishes multiple door concepts such as:
    - contact open / closed
    - secured / unsecured
    - locked / unlocked
    - auto unlocked / auto locked
    - access granted / access granted - egress
    - forced / forced restored
    - open too long / restored
  - Home Assistant currently exposes a practical subset of this, but the raw panel model is richer than the current HA entities.
- **Door contact detection**
  - This is much better than it was early on, but still best described as **best-effort**.
  - Some installations may need additional tuning or further protocol work to separate physical contact state from secure/lock state perfectly.
- **Event-burst handling**
  - The panel uses command and event queues.
  - Event acknowledgement is now substantially better than in earlier builds, but queue-heavy conditions are still being refined.

---

## What this integration is based on

This project has been built from:
- CTPlus packet captures
- CTPlus logs
- observed UDP event and status traffic
- the CTPlus event table
- comparison against a Control4 Tecom driver

That work has already revealed a few important protocol facts:
- the panel has separate **Alarm** and **Access** event queues
- the panel expects event acknowledgements in a very specific format
- some event classes need nothing more than an immediate ACK
- the protocol supports **targeted status recalls** for specific objects
- door behaviour is more complex than a single open/closed bit

---

## Supported modes

### 1. CTPlus / Management Software mode
This is the main mode and the one most people should use.

It provides:
- inputs
- areas
- relays
- doors
- realtime CTPlus-style events
- control functions

### 2. Printer / Computer Event Driven mode
This is more limited and is mainly useful for basic event-driven monitoring.

It does **not** expose the same level of control or structured status as CTPlus mode.

---

## Installation

### HACS
1. Open **HACS**
2. Go to **Integrations**
3. Add the repository as a **Custom repository**
4. Category: **Integration**
5. Install **Tecom ChallengerPlus**
6. Restart Home Assistant

### Manual install
1. Copy `custom_components/tecom_challengerplus` into:
   `/config/custom_components/tecom_challengerplus`
2. Restart Home Assistant

---

## Panel programming and path setup

### Use a dedicated panel path for Home Assistant
Home Assistant should have its **own Management Software / CTPlus style path**.
Do **not** share the same comms path and port with the CTPlus desktop software.

A good example is:
- **CTPlus desktop** on one path/port
- **Home Assistant** on a separate path/port

That makes troubleshooting much easier and avoids one client stealing the other client’s traffic.

### Recommended path settings
Use a **computer / management software** style path configured for Home Assistant.
The exact menu wording varies a bit depending on panel programming, but the important parts are:
- UDP/IP
- Client / computer style operation
- send to the Home Assistant host IP
- matching send/receive port
- encryption set to **None**

### Event filters matter
On the panel path, the event filter controls what Home Assistant will receive.
During reverse engineering, these categories were especially important:
- alarm events
- access events
- system / communications events

If these are filtered out, Home Assistant may still be able to poll statuses, but it will miss useful realtime events.

---

## Home Assistant configuration

The integration supports a fairly flexible entity layout.
Typical options include:
- host
- transport
- bind host
- send port / listen port
- poll interval
- counts and ranges for inputs, doors, relays, and areas

### General guidance
- Keep Home Assistant on the **same port** the panel path is configured to send to.
- Use a specific `bind_host` if Home Assistant has multiple interfaces.
- Keep polling conservative while troubleshooting.
- Use a dedicated comms path for HA rather than sharing with CTPlus.

---


### Importing names from a CTPlus `export.panel`
The integration can optionally read a CTPlus `export.panel` file and use it to apply friendly names to entities that are **already loaded in Home Assistant**.

This import is intentionally **name-only** for now. It does **not** create extra entities and it does **not** currently remap door contact logic from the export.

How it works:
- copy `export.panel` into Home Assistant, typically somewhere under `/config`
- open the integration **Options**
- set **Panel export path** to the file, for example `/config/export.panel`
- enable whichever rename toggles you want (areas, inputs, doors, relays, RAS)
- save the options so the integration reloads

Important behavior:
- only objects that the integration has actually loaded will be renamed
- unloaded panel objects are ignored
- entity IDs and unique IDs are left alone; only the friendly/display names change

Example:
- `Door 17` can become `Door 17 - Front Door - 17B`
- `Input 19` can become `Input 19 - Front Door Egress - 17B`
- `Area 2` can become `Area 2 - Shed 17B Nimrod`

Imported names are prefixed this way on purpose so Home Assistant keeps doors, inputs and other objects grouped and sorted by their panel numbers instead of alphabetically by description alone.

This makes dashboards and automations easier to understand without implying that Home Assistant is monitoring every object in the panel export.

## Entities

### Inputs (`binary_sensor`)
Inputs are exposed as binary sensors.

Current behaviour:
- **On** = unsealed / active
- **Off** = sealed / normal

These are updated from a mix of event-driven traffic and targeted/status recalls.

### Areas (`alarm_control_panel`)
Areas are exposed as Home Assistant alarm entities.

Current supported actions:
- arm away
- arm home
- disarm

External changes, such as arming or disarming from another keypad, CTPlus, or a mobile app, are reflected back into Home Assistant when the event path is behaving normally.

### Relays (`switch`)
Relays are exposed as normal Home Assistant switches.

### Doors (`lock` + contact sensor)
Doors are currently represented in two main ways:

- **Lock entity** for door control
- **Door Contact** binary sensor for contact-style state

#### DGP doors (17+)
These currently support a momentary **unlock / open** style command.

#### RAS doors (1-16)
These are surfaced more conservatively because a RAS may be acting as a keypad / simple door controller rather than a normal DGP door.

### Door modelling note
A Challenger door is not just “open” or “closed”. The event table and CTPlus behaviour show several overlapping concepts:
- contact open / closed
- secured / unsecured
- locked / unlocked
- auto unlocked / auto locked
- access granted
- access granted - egress
- forced / forced restored
- open too long / restored

So while the current HA entities are already useful, the long-term goal is to expose this more cleanly.

---

## Events in Home Assistant

Listen in **Developer Tools → Events** for:
- `tecom_challengerplus_ctplus_event`
- `tecom_challengerplus_event`

Example payload:

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

Recent builds also include extra event-table fields where available, such as:
- `eventtable_description`
- `eventtable_response_required`
- `eventtable_required_2nd_response`
- `eventtable_send_reset_to_panel`
- `eventtable_restore_event_code`
- `eventtable_update_status`
- `eventtable_status_options`

These are especially useful while reverse engineering the protocol.

---

## Known event mappings

The CTPlus event table has been folded into the decoder for many common event types.
Some especially useful ones are:

### Door state and access
- `0x86` = Door unlocked
- `0x87` = Door locked
- `0x88` = Door auto unlocked
- `0x89` = Door auto locked
- `0x92` = Door access granted
- `0x9D` = Door access granted - egress
- `0xA5` = Door open
- `0xA6` = Door closed
- `0xA7` = Door forced
- `0xA8` = Door forced restored
- `0xA9` = Door open too long
- `0xAA` = Door open too long restored
- `0xAE` = Door unsecured
- `0xAF` = Door secured

### Communications and module status
- `0x59` = Comms path fail
- `0x5A` = Comms path restored
- `0x5B` = Expander communications fault
- `0x5C` = Expander communications restored

### Inputs
The live captures showed the practical input mapping used by the integration is:
- `0x96` = sealed
- `0x97` = unsealed

This is intentionally based on observed live behaviour.

---

## Services

The integration currently exposes these services:

### `tecom_challengerplus.send_raw_hex`
Send a raw hex payload to the panel.

This is mainly for protocol testing and reverse engineering.

### `tecom_challengerplus.test_event`
Fire an internal Home Assistant test event.

### `tecom_challengerplus.dump_debug`
Write a JSON debug dump for all loaded Tecom hubs.

This is extremely useful when investigating:
- stuck event queues
- repeated events
- path fail / restore loops
- status refresh timing

The debug dump includes things like:
- current configuration snapshot
- current state snapshot
- recent transmitted frames
- recent received frames

---

## Debugging and troubleshooting

### Enable debug logging
Add this to `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.tecom_challengerplus: debug
```

Then restart Home Assistant.

### Useful Wireshark filters
Examples:

```text
udp.port == 3001
udp.port == 3006
ip.addr == <panel_ip> && udp
```

### Common symptoms and what they usually mean

#### 1. `Unknown` states after startup
Usually means one of:
- wrong path type
- wrong port
- encryption enabled on the panel path
- the panel is not sending replies to the configured HA path

#### 2. Same event repeating over and over
This normally means the panel still considers that event to be at the head of the queue.
Typical causes:
- incorrect event acknowledgement
- queue handling getting stuck during a burst
- a specific event class still not being handled correctly

When this happens, CTPlus diagnostics often show:
- event buffer growth
- repeated retries
- path fail / path restored messages

#### 3. `Comms path fail` / `Comms path restored`
These events are real panel events, not just bad decoding.
In practice they have often been a **symptom** of a stuck event queue rather than the root cause.

#### 4. Door state does not match the physical door perfectly
This is one of the current refinement areas.
The panel tracks more than one door concept, and some sites map “secured” or “unsecured” differently depending on their programming.

#### 5. Queue drains after a reload, then later jams again
That usually suggests:
- the basic transport is working
- the panel can deliver and HA can ACK a burst
- but a specific later event class still needs better handling

---

## Important practical notes learned during reverse engineering

### The panel is queue-driven
This turned out to be one of the biggest discoveries.
The panel keeps separate event queues, especially:
- **Alarm queue**
- **Access queue**

When the queue head is not retired properly:
- the same event is resent
- later events can be blocked behind it
- the comms path may start to flap

### ACK format matters
The panel is very sensitive to the exact ACK frame shape.
A small ACK-format issue was enough to cause:
- repeated identical events
- event queues that would not drain
- path flapping

### CTPlus uses targeted recalls
CTPlus does not appear to solve everything with broad polling.
It uses targeted recalls for specific objects such as:
- doors
- inputs
- areas
- DGP / comms related states

That is the direction this integration is moving toward as well.

### Polling still matters, but should not dominate
Polling is still useful for:
- startup sync
- recovery after reconnect
- filling in missed state changes

But heavy polling at the wrong time can compete with live event handling.
So the integration tries to balance event-driven updates with targeted recalls and conservative background polling.

---

## Current limitations

- Door modelling is still evolving
- Some rare event classes may still need additional response handling
- Panel object names are not yet pulled from the panel
- Encryption is not implemented for CTPlus mode
- Some behaviour may vary by panel programming and site-specific door logic

---

## Future work

The main next steps are:
- better separation of door **contact**, **secure**, and **lock** state
- cleaner handling of forced and open-too-long scenarios
- investigating panel record requests for:
  - area names
  - door names
  - input names
- continuing to reduce queue-stall edge cases

---

## Contributing

Useful things to capture when troubleshooting:
- packet captures with clear filenames
- CTPlus logs
- screenshots of path diagnostics and event buffers
- the exact action taken during the capture

The best captures are usually the simplest ones:
- one path
- one client
- one action sequence
- no unrelated clicking around during the recording

---

## Disclaimer

This project is community-built and reverse engineered.
It is not affiliated with Aritech or Tecom.
Use it carefully, test thoroughly, and treat it as an evolving integration rather than a finished commercial product.


## 2.0.70
- Relay switch entities are now grouped under the Tecom device in Home Assistant.
- Relay switch entities now expose basic debug attributes.
- Door lock entities now expose richer debug attributes and prefer explicit lock/secure events over the raw door word when available.
