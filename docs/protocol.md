# Protocol reference

[← Documentation](README.md) · [Events and actions](events-and-actions.md) · [Contributing](contributing.md)

This reference records the protocol behaviour already implemented and documented by the project. It is intended for diagnostics and development; ordinary setup does not require these details.

TecomHA uses the **CTPlus / Management Software binary protocol**, reverse engineered from CTPlus traffic, packet captures, logs and event-table data. It is not an official vendor protocol specification. For implementation details, see [ctplus_protocol.py](../custom_components/tecom_challengerplus/ctplus_protocol.py), [hub.py](../custom_components/tecom_challengerplus/hub.py) and the [changelog](../CHANGELOG.md).

## Event queues and acknowledgements

The panel keeps separate Alarm and Access event queues. If a queue head is not retired correctly, the same event is resent and later events remain blocked behind it. This can eventually appear as communication-path flapping.

Frame integrity is strict: an acknowledgement the panel cannot parse is effectively a missing acknowledgement. The historical multi-hour stalls required packet-level analysis to identify; changing broad polling intervals did not address their cause.

CTPlus uses targeted recalls for doors, inputs, areas and DGP states. The integration follows that approach, with status synchronisation at startup/reconnect and optional runtime polling. Heavy polling can compete with live event handling.

## Frame format

```text
5E <type> <flag1> <flag2> <sequence> <body...> <CRC16 little-endian>
```

CRC is CRC16/Modbus over the bytes from `type` through the end of the body.

`0x5E` is the frame sync marker. Every occurrence after the leading sync byte, including in the header, sequence, body or CRC, is escaped on the wire as `0x5E 0xFF`. Both encoding and parsing must account for the entire post-sync region. Omitting CRC/header escaping caused earlier queue stalls.

The basic message types are `0x40` data/event, `0x41` panel acknowledgement, `0x60` command, `0x64` heartbeat and `0x73` host acknowledgement. The protocol also uses type-offset variants; follow the existing implementation rather than guessing a type from one capture.

## Input status

An input is sealed only when **both bits 5 and 6** are set:

```python
sealed = (raw_status & 0x60) == 0x60
```

Standard inputs can become unsealed by clearing `0x20`; Type 20 inputs clear `0x40` instead. Testing one bit alone gives incorrect results for one group. Home Assistant reports unsealed as `on` and sealed as `off`.

## Area status

Bit `0x0080` of the area status word indicates armed. Lower modifier bits, such as isolation-related flags, must not determine armed state.

The status word cannot distinguish stay from away. Events `0x6C` and `0x0B` supply that distinction. Polls preserve a known stay-arm state and must not clear an active alarm simply because a status reply arrived.

## Door status

DGP door status words are decoded **big-endian**. The project confirmed the following by comparing locked/unlocked and open/closed combinations:

| Bit | Meaning |
| --- | --- |
| `0x0200` | Lock released |
| `0x0080` | Contact open |
| `0x1000` | Co-varies with contact open in the captured combinations |
| `0x0040` | Unsecured: unlocked or open |

A recent live door event briefly takes precedence over a conflicting queued poll response. Current status replies can populate lock/contact state at startup. The word does not express the difference between manual and automatic lock modes.

## Known event mappings

### Doors and access

| Code | Meaning |
|---|---|
| `0x86` | Door unlocked |
| `0x87` | Door locked |
| `0x88` | Door auto unlocked |
| `0x89` | Door auto locked |
| `0x92` | Access granted |
| `0x9D` | Access granted — egress |
| `0xA5` | Door open |
| `0xA6` | Door closed |
| `0xA7` | Door forced |
| `0xA8` | Door forced restored |
| `0xA9` | Door open too long |
| `0xAA` | Door open too long restored |
| `0xAE` | Door unsecured |
| `0xAF` | Door secured |

### Outputs

| Code | Meaning |
|---|---|
| `0x84` | Output active |
| `0x85` | Output normal |

### Inputs

| Code | Meaning |
|---|---|
| `0x96` | Unsealed (HA state: on) |
| `0x97` | Sealed (HA state: off) |

Seal state from polled status is decoded from bits 5 and 6 together — see [Input status](#input-status). Alternative mapping modes are available in the options for panels that behaved differently under earlier 2.x builds.

### Alarms

Alarm events are point-scoped and carry the area in the event body.

| Alarm | Restore | Meaning |
|---|---|---|
| `0x00` | `0x02` | Alarm |
| `0x04` | `0x05` | Secure alarm |
| `0x57` | `0x58` | Multi-break alarm |
| `0x67` | `0x68` | Exit alarm |
| `0xC2` | `0xC3` | Local alarm |

Note that `0x00` collides with "Comms - offline" in the event table; the meaning is context-dependent.

### Areas

| Code | Meaning |
|---|---|
| `0x0B` | Area armed (away) |
| `0x0C` | Area disarmed |
| `0x6C` | Area armed (stay / home) |

### Communications and modules

| Code | Meaning |
|---|---|
| `0x59` | Comms path fail |
| `0x5A` | Comms path restored |
| `0x5B` | Expander communications fault |
| `0x5C` | Expander communications restored |

## Authentication and encryption

User-facing setup is in [Panel setup](panel-setup.md#authentication). The implemented authentication methods are a packed 10-digit security password and fixed-width path user/password credentials.

Encrypted UDP payloads consist of a 16-byte IV, a two-byte big-endian plaintext length and CBC ciphertext through the end of the UDP payload. There is **no four-byte trailer**. The protocol uses zero padding rather than PKCS#7; the configured ASCII key is padded to 16 bytes for AES-128/TwoFish or 32 bytes for AES-256.

This layout was checked against 552 datagrams across 12 CTPlus captures: each cipher with both security/computer-password and path-user/password authentication. All decrypt to CRC-valid frames and re-encrypt byte-identically with their original IV. Authentication and host acknowledgement sends were also reproduced through the hub. These checks cover UDP; encrypted TCP is not implemented.

Both immediate and async acknowledgements use the selected encryption. Wrong-key detection checks padding and frame CRCs, because CBC decryption can return invalid bytes without raising an error.

See [ctplus_crypto.py](../custom_components/tecom_challengerplus/ctplus_crypto.py), [twofish.py](../custom_components/tecom_challengerplus/twofish.py) and the [3.4.2 release notes](../CHANGELOG.md#version-342) for details and capture-validation evidence.

## Development tools

The repository includes tools for decoding captured frames, inspecting debug dumps and comparing replay results:

- [decode_frame.py](../tools/decode_frame.py)
- [replay_debug.py](../tools/replay_debug.py)
- [validate_project.py](../tools/validate_project.py)
- [Protocol tests](../tests/test_protocol.py) and [crypto tests](../tests/test_crypto.py)

The PCAPNG reader supports Ethernet/IPv4 UDP, including VLAN tags and IPv4 options. It honours captured packet and UDP lengths, excludes capture padding/options/footers, and rejects malformed blocks or unsupported interface types. It does not reassemble IP fragments. The incorrect offsets in the older reader caused the false trailer claim corrected in 3.4.2.

Protocol values should be backed by a capture of the corresponding CTPlus action. Preserve distinctions between verified observations and values inferred from tables or incomplete captures.
