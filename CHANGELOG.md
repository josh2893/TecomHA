# Changelog

All notable changes to the Tecom ChallengerPlus Home Assistant integration.

Every protocol change in this project is confirmed against a packet capture of the
official CTPlus software before release. Where a value has not been verified that
way, the notes say so.

---

## Version 3.4.0

Path authentication and encryption now work, and the setup screen has been
reorganised. Everything in this release was confirmed against packet captures of
the official software.

### Path authentication

The computer password field was never sent. Earlier builds hardcoded the panel's
documented default of `0000000000`, so the integration could only ever connect
to a panel using that password — including the case the panel documentation
calls out, where a client connecting over DHCP cannot use the default at all.

Both authentication methods the panel supports are now implemented:

| Method | Frame |
|---|---|
| Security / computer password | `01 06 0B` + 5 bytes packed BCD, digits swapped within each byte |
| Path user name and password | `01 31 0A 1E` + 30-byte user name + `10` + 16-byte password, ASCII null padded |

Path credentials are supported by ChallengerPlus, Discovery, NACs and Challenger
from firmware V10-06.19251. The **Authentication type** on the panel's path must
match what is selected here.

A rejected credential is not reported by the panel — it answers the session
hello and then stops responding. Because the hello is acknowledged first,
silence after the authentication frame is a usable signal, and the integration
now validates credential formats during setup rather than letting a typo look
like an offline panel.

### Path encryption

Encryption previously prevented the integration from starting at all. All three
of the panel's ciphers are now supported:

| Panel setting | Key |
|---|---|
| AES CBC (128 bit) | up to 16 characters |
| AES CBC (256 bit) | up to 32 characters |
| TwoFish (128 bit) | up to 16 characters |

The datagram wrapper is identical for all three: a 16-byte IV in clear, a
two-byte plaintext length, CBC ciphertext zero-padded to a block boundary, and a
four-byte trailer derived from the ciphertext length.

The key is used as raw ASCII padded with zeros, so a long mixed key is
substantially stronger than a short numeric one even at the same setting. This
is noted in the configuration screen.

TwoFish is implemented in the integration because no maintained Python package
provides it and this project ships no runtime dependencies. It is validated
against the published test vectors. AES is recommended where the panel allows a
choice, as pure-Python TwoFish is considerably slower — irrelevant at normal
frame rates, but there is no reason to choose it otherwise.

A wrong key is also unreported by the panel, so repeated decryption failures are
logged once with an explanation rather than silently discarded.

**Validation:** 292 encrypted datagrams across six captures, covering all three
ciphers. Every one decrypts to a CRC-valid frame and re-encrypts byte-identical
to the original, so the integration can both read the panel and produce
datagrams it will accept.

### User name order

Panels are often loaded with names surname first, so the panel's own user list
sorts usefully. That reads oddly in Home Assistant, where an access event showed
`Smith John` rather than `John Smith`.

A **User name order** setting in the user sync section can present names given
name first. It defaults to leaving them exactly as the panel holds them, because
the ordering is a site convention rather than anything the protocol defines.

Only names of exactly two words are swapped. Entries such as `Card 3 Lock Box`
or a single `Master` are descriptive rather than personal, and reordering them
would produce nonsense.

Names are stored as the panel holds them and formatted when read, so changing
the setting takes effect immediately without another user sync.

### Setup and options screens reorganised

The single 51-field form is now grouped into collapsible sections — Connection,
Authentication and encryption, Panel objects, Naming, Object polling, Door
polling detail, User name sync, and Advanced. Only Connection is open initially.

Every field now has an explanation, including guidance that was previously
missing:

- **DGP door ranges** are recommended over the first/last door numbers, because
  ranges support gaps and avoid creating unused door entities
- **Relay ranges** likewise, so the entity list is not filled with relays the
  panel does not have
- Polling toggles say which are genuinely useful — input polling for motion
  detectors, which do not send seal events — and which are rarely needed
- The input mapping mode carries a warning; the CTPlus mapping is the confirmed
  correct one and the alternatives exist only for older setups

Diagnostic settings from earlier troubleshooting have moved into Advanced. The
same sections appear in both the setup wizard and the options screen.

### Upgrading

**Existing installations are migrated automatically and their behaviour does not
change.** The config entry version moves to 2, the authentication method is set
explicitly to security password, and the password is pinned to `0000000000` —
the value every working installation is currently sending, whatever the field
happened to contain.

If your panel uses a different security password, or you want to use path
credentials or encryption, set them in Options. They will now take effect.

Legacy encryption option values are mapped to the new names. Any entry with
encryption configured previously could not start at all, so there is no working
behaviour to preserve there.

---

## Version 3.3.5

### Door status word decoded, and its byte order corrected

Door lock and secure state previously came only from events, so a door nobody physically used stayed `unknown` indefinitely after a restart. The status word was available but treated as unreliable and largely ignored.

Driving one door through every combination of locked/unlocked and open/closed, polling status after each change, gives an unambiguous map:

| State | Word |
|---|---|
| Locked, closed | `0x0000` |
| Unlocked, closed | `0x0240` |
| Unlocked, open | `0x12C0` |
| Locked, open | `0x10C0` |

Each bit isolates cleanly:

| Bit | Meaning |
|---|---|
| `0x0200` | Lock released |
| `0x0080` | Door contact open |
| `0x1000` | Door contact open (co-varies with `0x0080`) |
| `0x0040` | Not secure — set when unlocked **or** open |

`0x0040` corresponds to the panel's own secured/unsecured concept, which is why unlocking emits both `0x86` (unlocked) and `0xAE` (unsecured).

**The word is big endian.** It was being read little endian, which swapped the bytes and put the contact bit in the wrong half — so a physically open door reported as closed, and a closed door was correct only by coincidence. That byte swap is almost certainly why the word appeared unreliable in the first place.

With the word decoded, a status poll now populates lock and secure state directly. A door no longer has to be opened before its entity leaves `unknown`, and the startup sweep bootstraps every door.

Event-derived values distinguish `auto_locked` from a manual `locked`, which the word cannot, so an existing value is kept when it agrees with the word and replaced only when the word contradicts it.

### Door open/close events no longer discard the status word

The `0xA5` and `0xA6` handlers overwrote the stored word with a synthetic `1` or `0`. Under the corrected decode those values read as locked and secured, so a door-open event destroyed the lock and secure state it had just been given. The handlers now set contact state only and leave the word intact.

### Door entity attributes

`bit_0x0002_set`, `bit_0x0010_set` and `bit_0x0080_set` are replaced with the decoded equivalents:

```yaml
word_contact_open: true
word_unlocked: true
word_unsecured: true
```

---

## Version 3.3.4

### Disarming an alarmed area raised a false "arm refused" warning

The control-failure handler treated any `0x02` response naming an object as a refused arm, without checking which action had failed. Disarming an area that was in alarm returns such a frame naming the inputs involved, which surfaced as an arm refusal on every area card.

Refusals are now raised only for arm actions (`0x06` force arm, `0x09` arm, `0x0A` arm stay) and only while an arm is actually outstanding. Other `0x02` responses are recorded in the debug frame log as `unhandled_0x02_response` rather than acted on, so they can be identified from a dump instead of being silently discarded.

The event also carries `action_name` and a composed `message`, so the wording matches the action attempted — `Force arm refused`, `Arm home refused` — rather than always saying `Arm refused`.

---

## Version 3.3.3

### Refused arm no longer appears on every area

A refused arm is area-scoped, but the alarm entity did not expose which area it represented, so a dashboard card had no way to tell whether a `tecom_challengerplus_control_failed` event applied to it. Every alarm card showed the refusal regardless of which area was being armed.

The alarm entity now exposes its area number as an `area` attribute, and the event already carried the area, so cards can match the two. Tile pack v3.0.1 or later filters on it.

Internally, pending arm commands are also tracked as a queue rather than a single slot, so two arms issued close together cannot attribute a refusal to the wrong area. A confirming arm event clears its own entry.

---

## Version 3.3.2

Fixes the issues reported against 3.3.0.

### Access events now name the user in Activity

Home Assistant's Activity feed renders an event entity's `event_type` and nothing else, so a card swipe showed only `access_granted` even though the user was present in the entity's attributes. A logbook platform lets the integration write its own lines:

| Situation | Activity line |
|---|---|
| Card, name synced | `Access granted - J. Smith` |
| Card, sync off | `Access granted - user 1041` |
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
  "user": 1041, "name_known": true, "raw_user_bytes": "1104" }
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

---

## Earlier releases


### 3.3.5
Decoded the door status word and corrected its byte order, so lock and secure state come from polling rather than waiting for a door to be used.

### 3.3.4
Fixed a false "arm refused" warning when disarming an area that was in alarm.

### 3.3.3
Alarm entities expose their area number so area-scoped events such as a refused arm can be matched to the right card.

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
