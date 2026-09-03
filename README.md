<p align="center">
  <img src="https://github.com/user-attachments/assets/70a1029a-d436-4150-a26b-f96b78bcbb4b" alt="TecomHA — Tecom Challenger integration for Home Assistant" width="720" />
</p>

<h1 align="center">TecomHA</h1>

<p align="center">
  <strong>Your Tecom alarm. Part of your smart home.</strong><br />
  Bring ChallengerPlus and Discovery alarms, doors and sensors into Home Assistant.
</p>

<p align="center">
  <a href="https://github.com/josh2893/TecomHA/releases"><img src="https://img.shields.io/github/v/release/josh2893/TecomHA?style=for-the-badge&amp;label=Release&amp;labelColor=282a36&amp;color=ff79c6" alt="Latest release" /></a>
  <a href="docs/installation.md"><img src="https://img.shields.io/badge/HACS-Custom-41bdf5?style=for-the-badge&amp;labelColor=282a36" alt="Install through HACS as a custom repository" /></a>
  <a href="https://github.com/josh2893/TecomHA/actions/workflows/validate.yml"><img src="https://img.shields.io/github/actions/workflow/status/josh2893/TecomHA/validate.yml?branch=main&amp;style=for-the-badge&amp;label=Checks&amp;labelColor=282a36" alt="Validation workflow status on main" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/josh2893/TecomHA?style=for-the-badge&amp;labelColor=282a36&amp;color=bd93f9" alt="Project licence" /></a>
</p>

<p align="center">
  <a href="docs/installation.md"><strong>Get started</strong></a> ·
  <a href="docs/README.md">Documentation</a> ·
  <a href="https://github.com/josh2893/TecomHA-Tiles-and-Addons">Dashboard tiles</a> ·
  <a href="https://github.com/josh2893/TecomHA/releases">Releases</a> ·
  <a href="https://github.com/josh2893/TecomHA/issues">Get help</a>
</p>

---

TecomHA connects your existing **Tecom ChallengerPlus or Discovery** panel to Home Assistant over your local network. Use the alarm, door contacts, motion detectors and relays you already have alongside the rest of your home.

The panel connection runs locally, with no cloud service required. Your panel continues to handle its own alarm and access logic; Home Assistant gives you another way to view, control and automate it.

## What can you do?

- **Control your alarm** — arm away, stay arm or disarm individual areas. See changes made at the keypad and which inputs triggered an alarm.
- **Manage your doors** — momentarily release a supported door, lock it, or leave it unlocked. Show its physical open/closed state separately using a door contact.
- **Use your existing sensors** — bring wired contacts and motion detectors into dashboards and automations. Optional polling covers inputs that do not send live changes.
- **Switch connected equipment** — control panel relays and see their state in Home Assistant.
- **See access activity** — view door access events and, with optional user name sync, who last presented a credential.
- **Keep familiar names** — import area, input, door and relay names from a CTPlus export so your dashboard makes sense at a glance.

Full door control is available for **DGP doors numbered 17 and above**. RAS/keypad objects numbered 1–16 are read-only. See the [entity guide](docs/entities.md) for supported behaviour and limitations.

## Make it part of your home

Once your panel is connected, its entities work with Home Assistant automations. For example:

- Turn on an entrance light when a door opens.
- Get a notification if a door is left open.
- Run a welcome-home scene when an alarm area is disarmed.
- Include the input that triggered an alarm in a notification.

**[Explore dashboards and automation examples →](docs/dashboards-and-automations.md)**

## Put it on your dashboard

Use Home Assistant's built-in cards, or add the optional **[TecomHA Tiles and Addons](https://github.com/josh2893/TecomHA-Tiles-and-Addons)** for compact alarm, door and relay controls.

The companion tiles can show alarm causes, physical door contact state and last access. You can also link a schedule entity to display when a schedule is active.

**[Set up your dashboard →](docs/dashboards-and-automations.md#dashboard-tiles)**

## Get started

You'll need a ChallengerPlus or Discovery panel reachable from Home Assistant, and access to configure a dedicated communication path on the panel.

1. **Install TecomHA** through HACS as a custom integration, or install manually.
2. **Prepare the panel connection** using the [panel setup guide](docs/panel-setup.md).
3. **Add “Tecom ChallengerPlus”** in Home Assistant and select the areas, inputs, doors and relays you want to use.
4. **Add your entities to a dashboard** and try your first automation.

**[Follow the installation guide →](docs/installation.md)**

## Guides and reference

| Looking for… | Start here |
| --- | --- |
| Installation or an update | [Installation](docs/installation.md) |
| Panel path, ports or encryption | [Panel setup](docs/panel-setup.md) |
| Entity ranges, names or polling | [Configuration](docs/configuration.md) |
| What each entity does | [Entities and supported behaviour](docs/entities.md) |
| Dashboard layouts and automation YAML | [Dashboards and automations](docs/dashboards-and-automations.md) |
| Event data or service calls | [Events and actions](docs/events-and-actions.md) |
| A connection or state problem | [Troubleshooting](docs/troubleshooting.md) |

[All documentation](docs/README.md) · [Protocol reference](docs/protocol.md) · [Changelog](CHANGELOG.md) · [Contributing](docs/contributing.md)

## Community project

TecomHA is an independent, community-built integration, developed by reverse engineering CTPlus communications. It is not affiliated with or endorsed by Aritech or Tecom.

Found a problem or have an idea? [Open an issue](https://github.com/josh2893/TecomHA/issues). A clear description and a [debug dump captured during the problem](docs/troubleshooting.md#capture-a-debug-dump) are especially helpful.

Test the controls and reported states against your own panel before relying on automations. Released under the [MIT licence](LICENSE).
