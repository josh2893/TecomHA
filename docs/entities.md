# Entities and supported behaviour

[← Documentation](README.md) · [Configuration](configuration.md) · [Events and actions](events-and-actions.md)

These features describe **CTPlus / Management Software mode**. Which entities appear depends on the configured object counts and ranges.

| Panel object | Home Assistant entity | Purpose |
| --- | --- | --- |
| Area | `alarm_control_panel` | Arm, stay arm, force arm, disarm and alarm status |
| Input / zone | `binary_sensor` | Sealed or active state, with alarm information in attributes |
| DGP door | `lock` | Lock, unlock and momentary release |
| Door contact | `binary_sensor` | Physical open/closed state reported by the panel |
| RAS / keypad | Read-only lock/contact entities | Limited status; no door control |
| Relay / output | `switch` | On/off control and status |
| Door activity | `event` | Access grants, egress, forced and open-too-long events |
| Last event | `sensor` | Latest panel event and diagnostic attributes |
| Sync Users Now | `button` | Download user names for the associated panel |

## Alarm areas

Each configured area has its own alarm control panel entity.

| Action | Behaviour |
| --- | --- |
| **Arm away** | Validated arming; the panel can refuse if inputs are unsealed |
| **Arm home / stay** | Stay-arms the area using the panel's programmed behaviour |
| **Force arm** | Arms regardless of unsealed inputs |
| **Disarm** | Disarms the area |

**Force arm does not isolate unsealed inputs.** An open input may immediately trigger an alarm. Home Assistant exposes this as `alarm_arm_custom_bypass`, but its behaviour here is the panel's force-arm command.

Changes made from a keypad, CTPlus or another panel client are reflected in Home Assistant when the corresponding events arrive. An area in alarm reports `triggered`; its `alarm_inputs` and `alarm_input_names` attributes identify the inputs reported in alarm.

Stay-armed areas report `armed_home`. The polled status word cannot distinguish stay from away, so an area already stay-armed before Home Assistant starts can initially show `armed_away` until an appropriate arm/disarm event is received. A known stay-arm state is preserved across subsequent polling.

## Inputs and zones

- **On** means unsealed / active.
- **Off** means sealed / normal.

Inputs update from event traffic and status recalls. Motion detectors that do not send seal events need [runtime input polling](configuration.md#polling); a sensor's response speed then depends on the polling interval.

Alarm state is separate from seal state. The `in_alarm` attribute reports whether the input is in alarm; when applicable, `alarm_area` and `alarm_area_name` identify its area. Raw status attributes are available for troubleshooting. The status-bit interpretation is documented in the [protocol reference](protocol.md#input-status).

## Doors: control and contact state

A door's **lock state** and **physical position** are different. An unlocked door can still be closed, and a locked output does not prove the door has closed.

Use the `lock` entity for control and the **Door Contact** binary sensor for open/closed status. The contact indication depends on the panel's contact wiring and programming. The companion door tile can also use a separately selected reed/input sensor.

| Action | Result |
| --- | --- |
| **Open Door** / `lock.open` | Momentary access grant using the panel's programmed release behaviour; does not change the latched lock mode |
| **Unlock** / `lock.unlock` | Leaves the door unlocked until a later lock command or panel logic changes it |
| **Lock** / `lock.lock` | Requests the locked mode |

**DGP doors (17+)** support these controls. **RAS doors/keypads (1–16)** are read-only because a RAS may be an arming station rather than a door controller. RAS status is a limited interpretation, not a substitute for a confirmed physical contact.

DGP lock attributes include `door_state`, `lock_state`, `secure_state` and raw/decoded door status values. Startup status polling now populates DGP lock and contact information; live events keep it updated. Where no usable state is known, the entity can remain unknown.

The panel also distinguishes automatic lock modes, secure/unsecure, access grants, forced doors and doors open too long. Home Assistant exposes a practical subset; site-specific programming can affect how these states relate.

## Relays

Relays appear as standard switches. Use them for equipment already connected to, and appropriately controlled by, the panel's outputs.

Live relay updates require **output events** on the dedicated communication path. If the state only changes after a reload or poll, check that filter first.

## Door access events

Each configured door has an access event entity. Its `event_type` can be:

- `access_granted`
- `access_granted_egress`
- `door_forced`
- `door_open_too_long`

The entity's state is a timestamp for the most recent event. Read the attributes for the event type, door and user details. Access activity appears in Home Assistant's Activity feed.

Optional [user name sync](configuration.md#user-name-sync) adds names to credential-based events. A panel-generated release may have no user, and an exit-button event does not necessarily identify a person. Last credentialed user information is retained so a following system release does not erase who badged.

## Scope and limitations

- Object names are imported from `export.panel`, rather than downloaded directly from the panel. User names have their own download feature.
- Timezone/schedule entities are not automatically imported from Tecom. A tile's schedule display uses an entity you supply.
- Door modelling, especially forced/open-too-long presentation and site-specific logic, continues to be refined.
- Direct area, input and door name downloads remain an area for future investigation.
- Printer mode does not offer the structured state and control features listed above.
