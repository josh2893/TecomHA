# Configuration

[← Documentation](README.md) · [Panel setup](panel-setup.md) · [Entities](entities.md)

Open **Settings → Devices & services → Tecom ChallengerPlus → Configure** to edit the integration. Setup and options use the same grouped sections. Save your changes to reload the integration.

## Connection, authentication and encryption

These fields must match the panel's dedicated communication path. See [Panel setup](panel-setup.md) for ports, credentials, encryption and event filters.

**Security / computer password** and **Encryption key** are separate settings. If the panel still uses its default security password, enter `0000000000` in the security password field. Enter the communication path's encryption key in **Encryption key**, and choose the matching **Encryption type**.

A 10-character key containing letters and digits is valid for **AES CBC (256 bit)**; it does not need to be 32 characters long. It must still match the panel exactly. Accepted key characters are `A-Z`, `a-z` and `0-9`.

If a value cannot be saved, the affected section opens with an explanation above it. Correct the indicated setting and submit again; your other entries are retained. Saving checks the format of these values, not whether the panel accepts them. Check the connection afterwards.

## Choose your panel objects

Configure only the objects you actually want loaded into Home Assistant. Ranges support comma-separated numbers and inclusive spans, such as `1-16,25,31`.

| Setting | Behaviour |
| --- | --- |
| **Number of inputs** | Loads inputs 1 through N when no input ranges are supplied |
| **Input ranges** | Loads only the listed inputs; overrides the input count |
| **Number of areas** | Loads areas 1 through N |
| **DGP door ranges** | Loads the listed expander doors, numbered 17 and above; overrides first/last door numbers |
| **RAS door numbers** | Loads the listed RAS/keypad objects, numbered 1–16, as read-only objects |
| **First / last door number** | Fallback contiguous door block when DGP door ranges are empty; a last door number of 0 disables that fallback block |
| **Relay ranges** | Loads only the listed relays; overrides the relay count |
| **Number of relays** | Loads relays 1 through N when relay ranges are empty |

For example, `17-20,33-36` includes two DGP door blocks without creating doors 21–32. `21-23` loads three relays without creating relays 1–20.

## Import names from CTPlus

TecomHA can read a CTPlus `export.panel` file and apply friendly names to **entities already loaded in Home Assistant**.

1. Export your panel configuration from CTPlus.
2. Copy the `export.panel` file somewhere under Home Assistant's `/config` directory.
3. In **Naming**, enter its full path, for example `/config/export.panel`.
4. Enable the rename options you want for areas, inputs, doors, relays and RAS objects.
5. Save the options.

This imports names only. It does not create additional entities, change entity IDs or unique IDs, remap door logic, or write configuration back to the panel. Objects outside the configured ranges are not imported for naming.

| Before | Example after import |
| --- | --- |
| Door 17 | Door 17 - Front Entry |
| Input 19 | Input 19 - Front Entry Egress |
| Area 2 | Area 2 - Workshop |

Object numbers remain at the start of the name. If names change in CTPlus, replace the export and reload the integration to apply them.

## Polling

Normal operation is event-driven. A status synchronisation runs at startup and after reconnect; optional runtime polling covers objects whose changes are not delivered as events.

Set **Polling interval**, then enable the required groups in **Object polling**. Changing the interval alone does not turn the groups on.

| Group | When to use it |
| --- | --- |
| **Poll inputs** | Useful for motion detectors and other inputs that do not send seal/unseal events |
| **Poll areas** | Usually unnecessary when arm, disarm and alarm events arrive correctly |
| **Poll relays** | Usually unnecessary when output events are enabled on the panel path |
| **Poll doors** | Usually unnecessary when door events arrive correctly; there is also a startup door sweep |
| **Poll RAS objects** | Enable only when periodic RAS status is needed |

For example, to request input polling every five seconds, set **Polling interval** to `5` and enable **Poll inputs**. This is the requested polling cadence; panel pacing, the number of objects and busy event handling can affect when each reply arrives. A short-lived change entirely between polls can still be missed.

Leave unrelated groups disabled. More frequent polling adds panel traffic and does not repair missing event filters or incorrect path settings.

### Door polling detail

When runtime door polling is enabled, **Round-robin** spreads requests over successive cycles. **Doors polled per cycle** controls the number requested each time. The alternative **All each cycle** requests all configured doors.

The default is round-robin with one door per cycle. These options do not need adjusting for ordinary event-driven operation.

## User name sync

Enable **Sync user names from panel** to show names alongside credential-based access events. Automatic syncing is off by default.

| Option | Behaviour |
| --- | --- |
| **Sync on startup** | Refreshes names at startup when user syncing is enabled |
| **Re-sync periodically** | Enables scheduled refreshes |
| **Re-sync interval** | Refresh interval in hours; default 24 |
| **User name order** | Keeps names as stored, or swaps names containing exactly two words into given-name-first order |

The **Sync Users Now** button performs a manual download for its panel, even when automatic syncing is disabled. Names are cached, so a download is not required for every access event. Without a matching name, access events can display the user number instead.

Only user numbers and names are extracted and stored by this feature. It does not provide card/PIN management or edit the panel's user database.

Name imports and user sync serve different purposes: `export.panel` supplies **object names**; user sync supplies **people's names for access events**.

## Defaults and advanced options

These are the defaults in the current source. Existing installations may retain earlier choices.

| Setting | Default |
| --- | --- |
| Polling interval | 1,800 seconds / 30 minutes |
| Runtime polling groups | All disabled |
| Broad door polling | Startup only |
| Heartbeat interval | 60 seconds |
| Minimum delay between sent frames | 250 ms |
| Acknowledgement delay | 25 ms |
| Send acknowledgements | Enabled |
| Send heartbeats | Enabled |
| Quiet-mode retry backoff | Enabled |
| Periodic session refresh | Disabled; 12-hour interval when enabled |
| Input mapping | CTPlus |
| Automatic user name sync | Disabled |
| User sync on startup | Enabled when automatic user syncing is enabled |
| Periodic user sync | Disabled; 24-hour interval when enabled |

Acknowledgements retire events from the panel queue; heartbeats keep the connection alive. Quiet mode reduces recall traffic while the panel retries an event. Keep these defaults unless troubleshooting has identified a specific reason to change them.

Periodic session refresh can help when control commands stop working after a long uptime while events continue to arrive. It is not required for normal operation.

The alternative input mapping modes, `legacy_inverted` and `status_only`, exist for older setups. **CTPlus** is the current mapping; changing it can make input states incorrect.
