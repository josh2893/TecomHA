# Events and actions

[← Documentation](README.md) · [Automation examples](dashboards-and-automations.md) · [Protocol reference](protocol.md)

## Standard Home Assistant controls

Prefer entity-targeted actions for normal controls. Replace the example IDs with your own.

| Action | TecomHA behaviour |
| --- | --- |
| `alarm_control_panel.alarm_arm_away` | Validated area arming |
| `alarm_control_panel.alarm_arm_home` | Stay arm |
| `alarm_control_panel.alarm_arm_custom_bypass` | Force arm; does not isolate unsealed inputs |
| `alarm_control_panel.alarm_disarm` | Disarm |
| `lock.open` | Momentary DGP door release |
| `lock.unlock` | Latched DGP door unlock |
| `lock.lock` | DGP door lock |
| `switch.turn_on` / `switch.turn_off` | Relay control |
| `button.press` on **Sync Users Now** | User name download for that button's panel |

Example action blocks for **Developer Tools → Actions** or an automation:

```yaml
action: alarm_control_panel.alarm_arm_away
target:
  entity_id: alarm_control_panel.house_alarm
data: {}
```

```yaml
action: lock.open
target:
  entity_id: lock.front_entry
data: {}
```

See the [alarm control panel](https://www.home-assistant.io/integrations/alarm_control_panel/) and [lock](https://www.home-assistant.io/integrations/lock/) documentation for Home Assistant's standard actions. The [entity guide](entities.md) explains Tecom-specific behaviour.

## Listen for panel events

In **Developer Tools → Events**, listen to either:

- `tecom_challengerplus_ctplus_event`
- `tecom_challengerplus_event`

The same decoded panel event is fired under both names for compatibility. Use one in an automation to avoid handling the same event twice.

Illustrative door-open payload:

```yaml
event_type: tecom_challengerplus_ctplus_event
data:
  entry_id: "your_config_entry_id"
  code: 165
  code_hex: "0xA5"
  object: 17
  object_hex: "0x0011"
  raw: "0f0c68c8389fa511000000000000"
  text: "Door 17 Open"
  message: "Door 17 Open"
```

The `entry_id` identifies the panel configuration entry. Additional fields depend on the event. They can include `area`, `user`, `user_name`, `last_user` and `last_user_name`. A system-generated release can have no user. Do not interpret the absence of a name as proof that a credential was not used; name sync may simply be unavailable.

Where available, CTPlus event-table metadata is included:

- `eventtable_description`
- `eventtable_response_required`
- `eventtable_required_2nd_response`
- `eventtable_send_reset_to_panel`
- `eventtable_restore_event_code`
- `eventtable_update_status`
- `eventtable_status_options`

The [protocol reference](protocol.md#known-event-mappings) lists known codes. Prefer ordinary entity state triggers for simple open/closed, relay or alarm automations.

## Per-door event entities

Door event entities expose access granted, egress, confirmed card/void denials, forced and open-too-long activity. The entity state is the time of the event; `event_type` is an attribute. Triggering only on a change of the `event_type` attribute can miss repeated events of the same type. Use the event entity's timestamp state when building an event-entity automation.

**Multiple panels:** events include `entry_id`, and each door entity checks both the panel entry and door number. Event-bus automations should also filter by `entry_id` when several panels share object numbers.

## Named Activity entries

The integration records `tecom_challengerplus_access_activity` for supported events on loaded door access entities. It includes `entry_id`, `entity_id`, `device_id` when registered, `name`, `message`, `icon`, `code`, `event_type` and `door`. Entity/device identifiers are present before Home Assistant filters Activity. The message is a snapshot of the name available at the time; it does not repeat the door's entity label.

| Event | Example message |
| --- | --- |
| Credentialed grant | `Access granted - J. Smith` |
| System release | `Access granted - System` |
| Exit button | `Access granted (exit button)` |
| Explicit void denial | `Access denied - J. Smith (void)` |
| Card rejection | `Access denied - Card rejected` |

Without a synced name, an identified user is shown as `User 1041`. Card rejection `0x4B` does not identify a user or distinguish unknown from voided cards. The decoded general event has `denial_reason: card_rejected`, an empty `raw` and `raw_redacted: true`. Explicit `0x8B` has `denial_reason: void`. See [confirmed denial layouts](protocol.md#access-denial-layouts).

Denials and anonymous releases do not overwrite the last successful credentialed access. Automations that mean a successful access should filter `access_granted` or `access_granted_egress`; a timestamp change can now also represent a denial. Entity IDs remain unchanged.

Home Assistant can show its native event-type row alongside the named entry. History remains a timestamp timeline, and old Activity is not rewritten. Do not exclude the access entity to hide the native row, as that can hide both. The generic “Event detected” label alone does not establish that the integration reloaded.

## Integration actions

All names below use the `tecom_challengerplus.` prefix.

| Action | Purpose and scope |
| --- | --- |
| `dump_debug` | Writes a debug JSON file. Optional `entry_id`; omitting it dumps all loaded panels. |
| `download_users` | Downloads user names for all loaded panels. Use the per-panel button for a targeted download. |
| `force_arm_area` | Takes `area` and force-arms that number on every loaded panel. Prefer the entity-targeted custom-bypass action when selecting one panel. |
| `request_full_sync` | Requests a full status refresh for the selected panel. |
| `reinitialize_session` | Re-sends the CTPlus session initialisation for the selected panel. |
| `reset_comms_path_event_buffer` | Maintenance-only reset/clear of the selected communication path's event buffer. |
| `retrieve_events` | **Legacy alias for the buffer reset above. It clears/resets the buffer; it is not a normal event download.** |
| `send_raw_hex` | Sends a raw payload for protocol testing. Takes `hex` and optional `entry_id`. |
| `test_event` | Fires the internal `tecom_challengerplus_test` event with an optional `note`. |

`request_full_sync`, `reinitialize_session`, both buffer-reset names and `send_raw_hex` accept `entry_id`. It is required for these actions when multiple panels are loaded. Use the configuration entry identifier, not an entity ID; the action raises an error rather than guessing which panel to use.

Do not put buffer resets into routine startup or recovery automations: they discard queued event information. Sending raw commands also requires a known, verified payload.

For a single-panel installation, a manual status refresh is:

```yaml
action: tecom_challengerplus.request_full_sync
data: {}
```

To capture diagnostic data without changing the event queue:

```yaml
action: tecom_challengerplus.dump_debug
data: {}
```

See [Troubleshooting](troubleshooting.md#capture-a-debug-dump) for locating and reviewing the resulting file.
