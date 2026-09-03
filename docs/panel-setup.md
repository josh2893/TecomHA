# Panel setup

[← Documentation](README.md) · [Installation](installation.md) · [Next: configuration →](configuration.md)

## Choose the connection mode

| Mode | What it provides |
| --- | --- |
| **CTPlus / Management Software** | Inputs, areas, relays, doors, structured events and control functions. Use this for normal installations. |
| **Printer / Computer Event Driven** | A text-event stream for basic monitoring. It does not provide the same structured state or controls. |

The instructions below describe CTPlus mode. Panel menu labels can vary with model and firmware.

## Give Home Assistant its own communication path

Create a dedicated computer / Management Software path for Home Assistant. Do not use the path and port currently assigned to the CTPlus desktop application: competing clients can take each other's traffic and interrupt the session.

| Item | Configuration |
| --- | --- |
| Path type | Computer / Management Software / CTPlus-style path |
| Transport | UDP/IP for the usual setup; TCP only when the path is configured for it |
| Destination | The Home Assistant host's reachable IP address |
| Ports | Match the panel and Home Assistant endpoints as described below |
| Authentication | Match the method and credentials in Home Assistant |
| Encryption | Match the selected cipher and key in Home Assistant; `None` is also supported |

Keep Home Assistant's destination IP stable so the panel continues to send traffic to the correct host.

## Match the network endpoints

In the Home Assistant configuration:

| Field | Meaning |
| --- | --- |
| **Panel IP address** | The panel's address on your network |
| **Panel port** | The port Home Assistant sends commands to on the panel |
| **Home Assistant listen port** | The local port where Home Assistant receives the panel's traffic |
| **Bind address** | The Home Assistant interface to listen on; normally leave it at `0.0.0.0` |

The default for both ports is `3001`. A dedicated path can use another suitable port; the endpoints must agree. If you use different send and receive ports, match each direction rather than assuming the numbers must be identical.

Ensure the selected traffic can pass between the panel and the Home Assistant host. For a host with multiple interfaces, set a specific bind address only when necessary. For TCP, the default role is **Client**, meaning Home Assistant connects to the panel.

## Enable the required event categories

The path's event filter determines which live changes Home Assistant receives. Include the relevant:

- Alarm and area events.
- Access and door events.
- System and communication events.
- **Output events**, so relay changes update live.

Filtered events will not reach Home Assistant. Status polling may still work, which can make a missing event category look like a delayed-update problem.

Some inputs, particularly motion detectors, may not send seal/unseal events even with the path configured correctly. Use [optional input polling](configuration.md#polling) for those inputs.

## Authentication

The panel path's **Authentication type** must match the method selected in Home Assistant.

| Method | Required details |
| --- | --- |
| **Security / computer password** | Exactly 10 digits from the communication path |
| **Path user name and password** | An ASCII user name of up to 30 characters and an ASCII password of up to 16 characters |

The panel's default security password is `0000000000`. The project's existing panel guidance notes that this default cannot be used when the client connects over DHCP; configure a non-default password in that situation.

Path user name/password support depends on panel firmware. The project's recorded compatibility note lists ChallengerPlus, Discovery, NACs and Challenger from firmware **V10-06.19251**. This is an authentication capability note, not a claim that every listed device is fully supported as an integration target.

A rejected credential may produce no explicit error: the panel can acknowledge the initial hello and then stop responding. Check authentication if the network looks reachable but setup does not complete.

## Encryption

Version 3.4.2 corrects encrypted UDP communication for both authentication methods. The available settings are:

| Panel setting | Encryption key |
| --- | --- |
| None | No key |
| AES CBC, 128 bit | Up to 16 alphanumeric characters |
| AES CBC, 256 bit | Up to 32 alphanumeric characters |
| TwoFish, 128 bit | Up to 16 alphanumeric characters |

Select the same cipher and enter the exact same key at both ends. Use UDP for encrypted paths; encrypted TCP is not supported. Both security/computer-password and path-user/password authentication have been verified with each cipher against CTPlus captures. A successful capture replay does not replace checking the connection from your Home Assistant installation.

AES is the preferred option where the panel offers a choice. TwoFish is supported for existing configurations but uses a slower Python implementation. The panel uses key text directly, so a longer mixed key is preferable to a short numeric key.

A wrong key can look like an offline panel. Check the encryption settings alongside authentication when diagnosing a silent connection.

For implementation details and the evidence behind authentication/encryption support, see the [3.4.2 changelog entry](../CHANGELOG.md#version-342) and [protocol reference](protocol.md).
