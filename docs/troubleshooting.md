# Troubleshooting

[← Documentation](README.md) · [Panel setup](panel-setup.md) · [Configuration](configuration.md)

Start with the dedicated panel path, the matching connection settings and the affected entity's state in **Developer Tools → States**. If the underlying entity is wrong, changing a dashboard tile will not fix it.

## Capture a debug dump

Take a dump **while the problem is happening**, preferably before reloading or resetting the integration. It includes configuration/state information and a ring buffer of recent transmitted and received frames.

1. Open **Developer Tools → Actions**.
2. Run:

```yaml
action: tecom_challengerplus.dump_debug
data: {}
```

3. Retrieve `/config/tecom_challengerplus_debug_<timestamp>.json` from the Home Assistant configuration folder.

With multiple panels, the action dumps all loaded hubs unless you supply an `entry_id`.

Review diagnostic files before posting them publicly. They contain site/network information and traffic. Version 3.4.3 redacts authentication, user-record and recognised `0x4B` card-rejection hex, including structured copies and acknowledgement references. Older dumps and packet captures can still contain credentials; the redaction does not remove general site/network information.

## Common symptoms

| Symptom | What to check |
| --- | --- |
| Entities remain unknown after startup | CTPlus path type, destination IP, transport, ports, authentication method/password and encryption type/key |
| Some objects never appear | Configured counts and ranges; an export file renames loaded objects only |
| Relay state updates only after reload/poll | Enable output events on the panel communication path |
| A motion detector does not update | Enable **Poll inputs** and set a suitable interval; the detector may not send seal events |
| Changing the polling interval has no effect | Enable the relevant runtime polling group as well |
| Door tile disagrees with physical position | Check the contact/reed entity separately from the lock entity; confirm panel wiring and programming |
| Stay-arm initially appears as away | Startup status cannot distinguish stay/away; the next relevant arm event supplies that distinction |
| Last access has a number instead of a name | Run **Sync Users Now**, or enable automatic user name sync |
| Last access says System | The event was a panel-generated release rather than an identified credential presentation |
| A tile's schedule always appears inactive | Check the linked schedule entity and its actual active state; schedules are not imported automatically |
| RAS/keypad door control is unavailable | Objects 1–16 are read-only; full controls apply to DGP doors 17+ |

### Submit returns to the connection form

In version 3.4.0, a validation error inside a collapsed section could be hidden. Update to 3.4.1 or later for an explanation above the affected section and retained setup values when retrying.

For authentication changes, check both **Security / computer password** and **Encryption key**. The panel's default security password is `0000000000`; an empty field is not the same value. A 10-character alphanumeric encryption key is accepted for AES-256. See [Configuration](configuration.md#connection-authentication-and-encryption).

### The panel responds initially, then goes silent

An authentication mismatch can look like a connection failure. The panel may acknowledge the hello before refusing the credentials silently. Confirm the authentication type and credentials at both ends. If encrypted, also check the exact cipher and key.

If encryption stops the connection on 3.4.0 or 3.4.1, update to **3.4.2 or later**. Those versions added four incorrect bytes to encrypted datagrams, rejected genuine replies and sent immediate acknowledgements without encryption. The fix applies to both authentication methods and all three ciphers over UDP. See the [stable release notes](../CHANGELOG.md#version-343).

Take a fresh dump with encryption enabled while the failure is occurring. Its `config` section reports `auth_method`, `encryption_type` and consecutive `decrypt_failures`, without the passwords or key. A repeated `decrypt_failed` note or a nonzero failure count means the receiver could not recover valid frames; check the selected cipher/key and packet integrity. A zero count by itself does not prove a connection, because the panel may have sent nothing.

Recent-frame hex is recorded before transmission encryption or after receive decryption. Seeing plaintext frames in a dump does not establish that encryption was disabled on the wire. Use the reported cipher and, if needed, a packet capture. Encrypted TCP is not supported by this build; use a matching UDP path.

### The same event keeps repeating

The panel may still consider that event to be the head of its queue. Previously identified protocol causes were fixed in the 3.2.x series. If this happens on a current build, capture a debug dump rather than assuming an older timing workaround is needed.

A last-event value beginning with `RAW` can indicate an unparsed frame. The dump's repeated-event details and recent frames help identify whether acknowledgement or parsing is involved. See [Protocol reference](protocol.md).

### Comms path fail / restored

These are real panel events. Historically, a blocked event queue could cause the path to fail and recover repeatedly. Also check basic connectivity and whether another client is using Home Assistant's path.

Do not routinely clear the event buffer to hide the symptom. Capture the failure first so the underlying cause can be diagnosed.

### No traffic for several minutes, then recovery

The receive watchdog can restart the transport after a sustained absence of frames. In a debug dump, look for `rx_watchdog_restart` notes and `seconds_since_last_rx`. With the default 60-second heartbeat, the watchdog timeout is normally four minutes.

A watchdog restart explains the recovery; it does not by itself explain why traffic stopped.

### An input stays off even when active

Check the actual contact state, the configured input type and **Input mapping mode**. The normal mapping is CTPlus.

Versions before 3.2.8 had a Type 20 input issue: those inputs can retain bit `0x20` while unsealed. Raw values such as `0x23` or `0x21` while the contact is open are useful evidence. Current decoding checks both seal bits. See the [input status reference](protocol.md#input-status) and [changelog](../CHANGELOG.md).

## Enable debug logging

Add or merge this into `configuration.yaml`, then apply the logging configuration:

```yaml
logger:
  default: info
  logs:
    custom_components.tecom_challengerplus: debug
```

Keep the relevant timestamp and the action that triggered the problem with your report.

## Packet captures

If a dump is insufficient, capture one simple action with CTPlus and the equivalent action with Home Assistant separately. Keep only one client on a path, record the starting state and use the same panel conditions when comparing behaviour.

Example Wireshark display filters; substitute the port or address used at your site:

```text
udp.port == 3001
udp.port == 3006
ip.addr == 192.168.1.50 && udp
```

For lock/contact problems, identify both the lock mode and physical door position. An unlocked-but-closed door is a different case from an unlocked-and-open door.

See [Contributing](contributing.md) for what to include in an issue. For tile resource/cache problems, use the [companion repository's troubleshooting guide](https://github.com/josh2893/TecomHA-Tiles-and-Addons#troubleshooting).

## Activity shows only an event type

Update to 3.4.3 and restart Home Assistant. Named entries include the door entity/device identifiers needed for Activity filtering. New entries use the name known when recorded; old entries are not backfilled. Run user name sync if an identified user appears only as a number.

A native `access_granted` row may coexist with the named entry. “Event detected” is Home Assistant's fallback when no event type is available, not proof of a reload. Keep the access entity included in Recorder/Logbook; excluding it may hide both rows. See [named Activity](events-and-actions.md#named-activity-entries).

After saving Options, the integration already requests a reload. If you subsequently change the panel's authentication or encryption, reload once both configurations match. The new code does not change session timing or add a different reload mechanism.
