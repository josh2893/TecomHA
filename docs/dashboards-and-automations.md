# Dashboards and automations

[← Documentation](README.md) · [Entities](entities.md) · [Events and actions](events-and-actions.md)

You can use TecomHA entities with Home Assistant's standard cards and automation editor. The companion tiles are optional.

**All entity IDs below are examples.** Replace them with your own IDs from **Settings → Devices & services → Entities**. Confirm the underlying entity works before adding dashboard controls or automations.

## Dashboard tiles

Install **[TecomHA Tiles and Addons](https://github.com/josh2893/TecomHA-Tiles-and-Addons)** separately. In HACS, add that repository with type **Dashboard**; the integration itself uses type **Integration**.

The companion repository contains the installation instructions and full card options. Current tiles expect integration **3.3.0 or later** for force arm, alarm cause reporting and access user display.

| Tile | What it shows |
| --- | --- |
| **Alarm** | Area state, arm/stay/disarm, force arm where supported, refused-arm feedback and alarm inputs |
| **Door** | Momentary release, optional lock/unlock, contact state, last access and an optional schedule indicator |
| **Relay** | Output control/state and an optional schedule indicator |

After installing the cards, open your dashboard's editor and add a **Manual** card:

```yaml
type: grid
columns: 2
square: false
cards:
  - type: custom:tecom-alarm-tile
    entity: alarm_control_panel.house_alarm
    name: House Alarm

  - type: custom:tecom-door-tile
    entity: lock.front_entry
    reed_entity: binary_sensor.front_entry_contact
    access_entity: event.front_entry_access
    name: Front Entry
    confirm_open: true

  - type: custom:tecom-relay-tile
    entity: switch.external_lighting
    name: External Lighting
```

Remove `access_entity` if you do not want the last-access line. Assign `reed_entity` to the physical contact you want displayed: `on` must mean open and `off` closed.

The door tile's default action is momentary **Open**. To expose latched lock/unlock as well, add:

```yaml
show_lock_buttons: true
confirm_unlock: true
```

Unlock remains active until changed by a lock command or panel logic. The [entity guide](entities.md#doors-control-and-contact-state) explains the distinction.

### Schedule indicators

To show a linked schedule on a supported tile, add fields such as:

```yaml
timezone_entity: schedule.external_lighting
timezone_label: Schedule
```

The entity must already exist in Home Assistant. The tiles do **not** download the panel's timezone table, and assigning a Home Assistant schedule does not synchronise or reprogram a Tecom timezone. It is an indicator for the entity you select.

A relay controlled by several panel rules is not necessarily a reliable indication of a particular timezone's state. Choose a source that actually represents the schedule you want to display.

## Add an automation

Create a new automation under **Settings → Automations & scenes**, open its menu and select **Edit in YAML**. Paste one complete example at a time and replace the example entities.

The notifications below appear **inside Home Assistant**. For phone push notifications, replace the notification action with your configured mobile notification action.

### Turn on a light when a door opens

```yaml
alias: Tecom - Entrance light when door opens
triggers:
  - trigger: state
    entity_id: binary_sensor.front_entry_contact
    from: "off"
    to: "on"
actions:
  - action: light.turn_on
    target:
      entity_id: light.entrance
mode: single
```

Use the contact entity so this reacts to the door physically opening. Add a separate condition if you only want it to run after dark.

### Notify when a door stays open

```yaml
alias: Tecom - Front entry left open
triggers:
  - trigger: state
    entity_id: binary_sensor.front_entry_contact
    to: "on"
    for: "00:05:00"
actions:
  - action: persistent_notification.create
    data:
      title: Front entry left open
      message: The front entry has been open for five minutes.
mode: single
```

This uses a five-minute Home Assistant timer, separate from the panel's own open-too-long event. The pending `for` timer resets if Home Assistant restarts or automations are reloaded, as described in the [Home Assistant state trigger documentation](https://www.home-assistant.io/docs/automation/trigger/#state-trigger).

### Run a scene when an area is disarmed

```yaml
alias: Tecom - Welcome home after disarming
triggers:
  - trigger: state
    entity_id: alarm_control_panel.house_alarm
    from: "armed_away"
    to: "disarmed"
actions:
  - action: scene.turn_on
    target:
      entity_id: scene.welcome_home
mode: single
```

Create the scene in Home Assistant first. This example reacts specifically to disarming from away mode; it does not run merely because a previously unknown entity appears as disarmed at startup.

### Include the alarm cause in a notification

```yaml
alias: Tecom - Alarm triggered
triggers:
  - trigger: state
    entity_id: alarm_control_panel.house_alarm
    to: "triggered"
actions:
  - action: persistent_notification.create
    data:
      title: House alarm triggered
      message: >-
        {% set inputs = trigger.to_state.attributes.get('alarm_input_names', []) %}
        {% if inputs %}
          Inputs in alarm: {{ inputs | join(', ') }}.
        {% else %}
          The panel reported an alarm. Check Home Assistant or the keypad for details.
        {% endif %}
mode: single
```

This reports the inputs known when the area first changes to triggered. Further inputs may join an already active alarm without triggering this example again.

For action names, event types and panel-specific controls, see [Events and actions](events-and-actions.md). The examples use Home Assistant's [automation syntax](https://www.home-assistant.io/docs/automation/trigger/) and [persistent notification action](https://www.home-assistant.io/integrations/persistent_notification/).
