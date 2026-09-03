# Installation

[← Documentation](README.md) · [Next: panel setup →](panel-setup.md)

## Before you start

You need:

- A **Tecom ChallengerPlus or Discovery** panel with an IP communication path available for Home Assistant.
- Home Assistant with network access to the panel.
- Access to the panel's programming, or someone who can configure a dedicated path for you.
- The panel's IP address, ports, authentication details and any encryption key.

Configure the path using the [panel setup guide](panel-setup.md) before completing Home Assistant setup. The recommended mode is **CTPlus / Management Software**.

## Install with HACS

If HACS is not installed, follow its [getting started guide](https://www.hacs.xyz/docs/use/).

1. Open **HACS** in Home Assistant.
2. Open the three-dot menu and select **Custom repositories**.
3. Enter `https://github.com/josh2893/TecomHA` and select **Integration** as the category/type.
4. Find **Tecom ChallengerPlus** and download it.
5. Restart Home Assistant.

The repository is added as a HACS custom repository. See the [HACS custom repository instructions](https://www.hacs.xyz/docs/faq/custom_repositories/) if the menu differs in your version.

## Install manually

1. Download the integration archive from the [Releases page](https://github.com/josh2893/TecomHA/releases).
2. Extract the archive and copy the `tecom_challengerplus` folder into `/config/custom_components/`.
3. Check that this file exists: `/config/custom_components/tecom_challengerplus/manifest.json`.
4. Restart Home Assistant.

If you downloaded the whole repository instead, copy its `custom_components/tecom_challengerplus` folder to the same destination. Avoid nesting one `tecom_challengerplus` folder inside another.

## Add the integration

1. Go to **Settings → Devices & services → Add integration**.
2. Search for **Tecom ChallengerPlus**. This is the integration's name in Home Assistant, including when connecting a Discovery panel.
3. In **Connection**, select CTPlus mode and enter the panel's IP address and matching transport/ports.
4. In **Authentication and encryption**, enter the settings used by the panel path.
5. In **Panel objects**, select the inputs, areas, doors and relays you want to expose. Prefer ranges when object numbers have gaps.
6. Save and allow the initial status synchronisation to finish.

The setup and options screens use the same grouped sections. The [configuration guide](configuration.md) explains each group.

## Check the connection

Open the integration's entities and compare a known area, input and door with the panel. Change a contact or use the keypad and check that Home Assistant follows it. For a motion detector that does not send seal events, enable [input polling](configuration.md#polling).

Once states and controls behave as expected, [add your dashboard and automations](dashboards-and-automations.md).

## Update an existing installation

Use **Update** in HACS, or replace the integration folder with the newer release, then restart Home Assistant. Read the [changelog](../CHANGELOG.md) for any migration or setup changes affecting your version.

Existing configuration is migrated where supported. In particular, version 3.4.0 made the authentication and encryption options functional; its changelog explains how earlier settings are preserved and when you should update them.

The [companion dashboard tiles](https://github.com/josh2893/TecomHA-Tiles-and-Addons) are installed and updated separately.
