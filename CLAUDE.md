# CLAUDE.md

Guidance for Claude Code working in this repository.

---

## 1. What this is

A Home Assistant custom integration for **Aritech / Tecom ChallengerPlus** security panels, speaking the CTPlus / Management Software binary protocol over UDP (usually) or TCP.

The protocol is undocumented and proprietary. Every byte in this codebase was derived by capturing traffic from the official CTPlus software and decoding it by hand. That single fact shapes most of the rules below.

This is a **security system**. A wrong state shown in Home Assistant can mean someone believes a door is locked when it is not. Prefer reporting `unknown` over guessing.

---

## 2. Commands

```bash
# Full structural validation. Run before every release.
python3 tools/validate_project.py

# Ground-truth protocol tests.
python3 -m pytest tests/ -q

# Decode frames while working on the protocol.
python3 tools/decode_frame.py 5e408000106903120240
python3 tools/decode_frame.py --pcap captures/door18_locked.pcapng
python3 tools/decode_frame.py --debug dumps/tecom_challengerplus_debug_123.json

# Replay debug dumps and compare against a saved baseline.
python3 tools/replay_debug.py --save baseline.json dumps/*.json
python3 tools/replay_debug.py --baseline baseline.json dumps/*.json
```

Requirements for tooling only: `pytest`, `pyyaml`. The integration itself has no runtime dependencies — `manifest.json` `requirements` is empty and should stay that way, since Home Assistant users should not be made to install packages for this.

**Before a release, all of these must pass and the results reported.** Do not claim validation was performed without running it.

Run them in an environment matching CI, not a convenient one. Test dependencies
are declared in `requirements-test.txt`; a development machine with extra
packages installed will pass things CI fails. The workflow has no Home Assistant
and only what that file lists.

```bash
python3 -m venv /tmp/civenv
/tmp/civenv/bin/pip install -r requirements-test.txt
/tmp/civenv/bin/python -m pytest tests/ -q
```

Two CI failures have been caused by validating in a more forgiving environment
than the one that matters: once by having Home Assistant importable, once by
having `cryptography` installed.

---

## 3. The rule that matters most

**Never guess a protocol value.**

Every command byte, event code and status bit must be confirmed against a packet capture before it ships. This is not a style preference. The project has been bitten repeatedly, and each case took far longer to find than a capture would have taken to request:

| Assumption | Reality | Consequence |
|---|---|---|
| Arm-home is `0x09` | It is `0x0A` | Arming home silently did nothing for several releases |
| Door status word is little endian | Big endian | Open doors reported closed; the word was written off as "unreliable" for months |
| Input seal is bit `0x20` | Type 20 inputs use `0x40` | Those inputs reported permanently sealed and could never turn on |
| User number is one byte | Two bytes, little endian | A four-digit user was attributed to a different user entirely |
| Any `0x02` response is a refused arm | Only arm actions | Disarming raised a false warning on every area card |

If a value is unverified, either do not implement it, or implement it and state plainly in both the code comment and the changelog that it is unconfirmed.

**When a capture is needed, ask for it.** A capture of one action is usually two packets and settles the question in minutes.

Ask for captures like this: one action per capture, filter `host <panel_ip> and udp`, start, perform the single action, stop. Separate files matter more than filtering — CTPlus polls constantly, and three actions in one file means hunting for which frames belong to which.

---

## 4. Analysis before implementation

When given captures or debug dumps:

1. **Decode and report findings first.** Do not write code in the same step.
2. **Show the evidence** — the actual bytes and the state they correspond to.
3. **State what is confirmed and what is inferred.**
4. **Build only once the finding is agreed.**

### Correlate only contemporaneous data

A real mistake made in this project: comparing `door_words` (refreshed by polling) against `door_lock` (possibly hours stale from an old event) from the same debug dump, concluding the word was ambiguous, and writing that into the code as fact. It was not ambiguous — the comparison was invalid.

When correlating a raw value against a state, both must have been captured at the same moment. The reliable pattern is: change one thing physically, poll immediately, record the pair.

### Isolate one variable at a time

The door status word only became decodable once all four combinations existed:

```
locked   + closed    unlocked + closed
locked   + open      unlocked + open
```

With three of the four, several bits co-varied and could not be separated. If a bit map has ambiguity, the missing combination is what to ask for.

---

## 5. Domain glossary

Terms from the Tecom world that appear throughout the code:

| Term | Meaning |
|---|---|
| **Area** | A group of inputs armed and disarmed together. What HA calls a partition. |
| **Point / input / zone** | A detection circuit — PIR, reed switch, glass break |
| **Sealed / unsealed** | Input at rest / activated. Unsealed maps to HA `on`. |
| **Secured / unsecured** | Door state: secure means locked and closed |
| **Isolated** | An input excluded from the area, so it cannot cause an alarm |
| **DGP** | Data Gathering Panel — an expander. DGP doors are 17+ and support full control. |
| **RAS** | Remote Arming Station — a keypad or reader. RAS doors are 1–16 and are read-only here, since a RAS may be a keypad rather than a door controller. |
| **Comms path** | A configured route from panel to a client. Home Assistant should have its own, not shared with CTPlus. |
| **Egress / REX** | Request to exit — a button releasing a door from inside, with no credential |
| **EOL** | End-of-line resistor. Wrong values produce fault states that look like odd status bytes. |
| **Type 20** | An input programmed to activate an event flag, 24 hour. Reports seal state on a different bit from a standard input. |
| **Force arm** | Arm despite unsealed inputs. Does **not** isolate them, so open zones alarm immediately. |
| **Shunt** | The period a door may stay open after a valid access without alarming |

---

## 6. Architecture

### Frame lifecycle

```
transport.py          UDP datagram or TCP stream arrives
   |
hub._on_ctplus_datagram / _on_ctplus_bytes
   |                  records rx time for the watchdog
   |                  appends to the debug ring buffer (user records redacted)
   |
hub._scan_ctplus_frames -> ctplus_protocol.parse_frame
   |                  unstuffs 0x5E 0xFF, validates CRC
   |
hub._handle_ctplus_frame
   |                  ACKs unsolicited frames
   |                  tries each response parser in order, then event decode
   |                  updates hub.state, fires HA bus events
   |
hub._notify -> entity listeners -> async_write_ha_state
```

### Where state lives

`ChallengerState` in `hub.py` is the single source of truth. Entities are thin views over it and hold no state of their own.

| Field | Populated by |
|---|---|
| `inputs` | seal events `0x96`/`0x97`, and input status polls |
| `areas` | area events `0x0B`/`0x0C`/`0x6C`, alarm events, area status polls |
| `area_words` | area status polls |
| `doors` | door open/close events `0xA5`/`0xA6`, door status polls |
| `door_words` | door status polls only |
| `door_lock`, `door_secure` | lock/secure events, and derived from the door word |
| `relays` | output events `0x84`/`0x85`, relay status polls |
| `input_alarms`, `area_alarms` | alarm and restore events |
| `user_names` | user database download, cached to HA storage |
| `last_access` | access events that carried a credential |

### Precedence rules

These exist because polls and events race, and getting the order wrong produces flapping state:

- **Events beat polls briefly.** After a door event, `_door_event_prefer_until` suppresses contradicting poll replies for 15 seconds, so a queued stale poll cannot undo a live change.
- **Polls beat stale events for lock state.** A door status word is current; an event may be hours old. But an existing `auto_locked` is kept when the word agrees, because the word cannot express the auto- distinction.
- **Nothing beats an alarm.** A status poll must not clear a `TRIGGERED` area — only an alarm restore or an arm/disarm does.
- **`home` survives polling.** The area armed bit does not distinguish stay from away, so a poll must not downgrade a known stay-arm.
- **Optimistic updates** on arm/disarm/lock set state immediately, then get corrected by the confirming event. `_area_override_until` protects them from polls in the meantime.

### Recovery mechanisms

- **Rx watchdog** — if no frame arrives for 4× the heartbeat interval (min 120 s), the transport restarts and the session reinitialises. Covers silent dropouts, not wedged queues.
- **Byte stuffing** — covered below; two multi-hour stalls came from getting this wrong.
- **Startup door sweep** — polls every DGP door once, paced one at a time so the panel's queue can keep up.

---

## 7. Protocol reference

### Framing

```
5E <type> <flag1> <flag2> <seq> <body...> <crc16 LE>
```

CRC is CRC16/Modbus over everything from `type` to the end of body.

**Byte stuffing:** `0x5E` is the sync marker. Every `0x5E` after the leading sync byte — in the header, sequence, body or CRC — is escaped as `0x5E 0xFF`. Both `to_bytes()` and `parse_frame()` apply this across the whole post-sync region.

Getting this wrong caused two separate failures where the panel's event queue stalled for hours and could only be cleared by disabling the comms path. Only two sequence values out of 256 trigger it, which is why it took so long to find.

### Message types

`0x40` data/event · `0x41` panel ack · `0x60` command · `0x64` heartbeat · `0x73` host ack.

Add `0x40` for the panel variant (`0xA0` command, `0xB3` host ack). CTPlus uses the `+0x40` form; the integration follows whatever the panel indicates.

### Commands

| Purpose | Bytes |
|---|---|
| Door lock / unlock / momentary open | `04 02 <01\|02\|04> <door>` |
| Area disarm / force arm / arm / arm stay | `02 02 <05\|06\|09\|0A> <area>` |
| Door status | `7e 07 80 7c 04 00 68 01 <door>` |
| Input status | `09 04 <start:2> <count:2>` |
| User database page | `25 05 1D <start:2 LE> FF FF` |

Force arm (`0x06`) arms regardless of unsealed inputs. Plain arm (`0x09`) validates and the panel refuses with a structured reason naming the offending input.

### Events

```
0F 0C <timestamp:4> <code> <object:2 LE> <area> <user:2 LE>
```

- The anchored `0F 0C` form must be checked **before** any loose byte scan. Timestamps contain bytes that look like markers, and a scan-first order mis-decoded well-formed events and invented phantom area numbers.
- `area` is a single byte at offset 9. Byte 10 is a separate field.
- `user` at bytes 10–11 applies **only** to access codes `0x92`/`0x9D`. Other codes reuse those bytes.
- Area-scoped codes (`0x0B`, `0x0C`, `0x6C`) report the area; object is zero.

### Path authentication

The `0x01` command carries a method byte followed by credentials. The panel's
Authentication type must match, and a mismatch is silent -- see below.

```
Security password   01 06 0B <5 bytes>
                             packed BCD, digits swapped within each byte,
                             so "1234567890" is 21 43 65 87 09

Path credentials    01 31 0A 1E <username, 30 bytes> 10 <password, 16 bytes>
                             ASCII, null padded to the field widths
```

The security password is 10 digits and defaults to `0000000000` on the panel.
That default cannot be used when the client connects over DHCP.

**A rejected credential produces no error.** The panel answers the session hello
normally and then simply stops responding. Since the hello is acknowledged
before authentication is attempted, silence after the auth frame is a reliable
signal that the credentials were refused rather than the panel being offline.

### Path encryption

All three ciphers share one datagram wrapper:

```
IV          16 bytes   plaintext, prepended
length       2 bytes   big endian, plaintext length before padding
ciphertext   n x 16    CBC, zero padded
trailer      4 bytes   [0x5C + len(ciphertext), 0x00, 0x00, 0x00]
```

The key is the configured text as raw ASCII, null padded to the cipher's key
length: 16 bytes for AES 128 and TwoFish, 32 for AES 256. There is no hashing
or derivation, so a short key leaves the remainder zeroed and is far weaker than
the nominal key size suggests.

Padding is zero bytes, not PKCS#7; the explicit length field disambiguates.

Encryption wraps whole datagrams and is applied in `hub.async_send_bytes` and
`hub._decrypt_datagram`, so everything above that layer works in plaintext
frames. A wrong key is not reported by the panel either -- traffic simply
arrives undecryptable, which is why repeated decrypt failures are logged once
as a probable key mismatch.

TwoFish is implemented in `twofish.py` because no maintained package provides it
and this integration ships no runtime dependencies. It is validated against the
published test vectors. Being pure Python it is far slower than AES, which is
irrelevant at CTPlus frame rates but is why AES should be preferred.

### Door status word (big endian)

| Bit | Meaning |
|---|---|
| `0x0200` | Lock released |
| `0x0080` | Contact open |
| `0x1000` | Contact open (co-varies with `0x0080`) |
| `0x0040` | Not secure — set when unlocked **or** open |

### Input status byte

Sealed when bits 5 **and** 6 are both set: `(raw & 0x60) == 0x60`. Which bit clears on unseal depends on the input's programmed type, so never test one alone.

### Area status word

Bit `0x0080` is armed. Lower bits are modifiers such as isolated inputs, and do not affect armed state. The word cannot distinguish stay from away — only events can.

---

## 8. Privacy

This repository is public, and debug dumps get attached to issue reports.

- **Never commit site data**: user names, card numbers, door or area names, panel IP addresses. Use `J. Smith`, `Front Entry`, `192.168.1.50`.
- **User records contain card and PIN material.** `parse_user_records()` reads only bytes 0–1 (number) and 19–34 (name). Do not extend it.
- **Debug dumps redact user-record frames.** `_redact_debug_hex()` strips them from the ring buffer. Without it, any dump taken shortly after a user sync contains names and credential bytes in raw hex. If you add another frame class carrying sensitive data, redact it there too.
- **Dumps carry user numbers and counts, never names.**
- `tools/validate_project.py` scans for committed site addresses; extend its patterns rather than relying on memory.

---

## 9. Repository layout

```
custom_components/tecom_challengerplus/
├── __init__.py                platform and service registration
├── hub.py                     transport, session, state, event dispatch (large)
├── ctplus_protocol.py         frame encode/decode, commands, parsers
├── transport.py               UDP/TCP plumbing
├── config_flow.py             setup wizard and options (shared schema)
├── const.py                   config keys and defaults
├── logbook.py                 Activity feed descriptions
├── event.py                   door access event entities
├── button.py                  user sync button
├── alarm_control_panel.py     areas
├── binary_sensor.py           inputs, door contacts
├── lock.py                    doors
├── switch.py                  relays
├── sensor.py                  diagnostics
├── ctplus_event_decoder.py    event code -> description
├── ctplus_eventtable_data.py  GENERATED — do not hand-edit
├── panel_export.py            friendly names from export.panel
├── services.yaml
└── translations/en.json
tools/                         decode, validate, replay
tests/                         ground-truth protocol tests
CHANGELOG.md                   all version history
```

A companion Lovelace repo, **TecomHA-Tiles-and-Addons**, tracks integration features. Changes to entity attributes or services usually need a matching tiles change and a compatibility note in both repos.

---

## 10. Codebase traps

Things that have already caused bugs and are not obvious from reading:

- **`ctplus_eventtable_data.py` is generated.** Do not hand-edit.
- **Event code `0x00` is context-dependent.** It is a zone alarm, but the event table lists `(0, 0)` as "Comms - offline".
- **Debug dumps double-count frames.** One entry is written for the datagram and another for the parsed frame. Two identical entries at the same timestamp are one frame, not two.
- **There are two door-status code paths.** One handles state, one only builds debug summaries. Changing state handling means editing the first.
- **Entity restore is self-perpetuating.** A door lock entity restores from its own previous attributes; once `unknown`, it stays `unknown` across restarts until a real event. Do not rely on restore to recover state that was never known.
- **HA's Activity feed does not read entity attributes.** It renders an event entity's `event_type` only. Anything richer needs `logbook.py`.
- **`supported_features` gates the tiles.** Force arm renders only when `ARM_CUSTOM_BYPASS` is advertised.
- **Config flow sections nest their data.** Home Assistant returns each section as a dictionary under the section key, but the hub reads a flat mapping and every entry created before sections existed is stored flat. `flatten_sections()` collapses them before saving; storage must stay flat.
- **Never add an entity where an attribute will do.** A per-input alarm entity was added in one release and removed in the next after it doubled a user's entity list.

---

## 11. Code conventions

- Comments explain **why**, not what. Where a value came from a capture, say so — future readers need to know what is verified and what is not.
- Protocol constants live in `ctplus_protocol.py` and are referenced by name from `hub.py`. Avoid bare hex literals in handler dispatch.
- Parsers return `None` on no-match so callers can chain them; they must not raise on unexpected input.
- Prefer widening an existing parser over adding a near-duplicate.
- Match the surrounding style. No linter is enforced; consistency matters more than any particular rule.

---

## 12. Documentation

### Purpose

Keep TecomHA's documentation welcoming, accurate and easy to navigate. The root README introduces what people can do with their Tecom panel in Home Assistant. Detailed instructions and technical reference belong in `docs/`.

Preserve the redesigned structure during routine updates. Improve the relevant sections without turning the README back into a technical manual. Follow explicit maintainer requests when they call for a different structure.

### File ownership

Use this map to decide where a change belongs. Paths are relative to the repository root.

| File | Responsibility |
| --- | --- |
| `README.md` | Project introduction, user-facing capabilities, practical use cases, dashboard overview, short getting-started steps and links to further help |
| `docs/README.md` | Documentation index, with a short description and link for each guide |
| `docs/installation.md` | Prerequisites, HACS and manual installation, adding the integration, first checks and the general update process |
| `docs/panel-setup.md` | Panel communication paths, connection modes, IP addresses, ports, event filters, authentication and encryption |
| `docs/configuration.md` | Home Assistant configuration/options fields, object ranges, naming imports, polling, user name sync and advanced defaults |
| `docs/entities.md` | Available entity types, supported controls, state meanings, useful attributes and current limitations |
| `docs/dashboards-and-automations.md` | Dashboard examples, an introduction to the companion tiles, contact/schedule indicators and usable automation examples |
| `docs/events-and-actions.md` | Event names and payloads, standard Home Assistant actions, custom integration services, parameters and targeting behaviour |
| `docs/troubleshooting.md` | Symptoms, diagnostic steps, debug dumps, logging and packet-capture guidance |
| `docs/protocol.md` | Framing, acknowledgements, event queues, status bits, event-code mappings and implementation references |
| `docs/contributing.md` | Issue-report requirements, useful captures, development references and contributor-facing documentation guidance |
| `CHANGELOG.md` | Version history, release-specific changes, upgrade notes and evidence for protocol changes |
| `CLAUDE.md` | Repository instructions for development and documentation work; keep the full agent instructions here |

Prefer an existing guide over creating a new file. Add a guide only when a distinct topic needs its own page. If adding or renaming a guide, update `docs/README.md` and all affected references. Keep the root README's navigation selective rather than listing every subsection.

### Root README structure

Preserve this order unless the maintainer requests a redesign:

1. Existing project banner.
2. Centred TecomHA title and short tagline.
3. Badge row and primary navigation links.
4. Brief explanation of the integration and its local panel connection.
5. **What can you do?** — capabilities expressed as user outcomes.
6. **Make it part of your home** — a few practical automation ideas.
7. **Put it on your dashboard** — built-in cards and the optional companion tiles.
8. **Get started** — a short outline linking to the complete guides.
9. **Guides and reference** — a compact navigation table.
10. **Community project** — affiliation statement, support link and licence.

Keep the README close to its current size: approximately 500–700 words of visible content is a useful target, not a rigid requirement. When adding a feature, first consider whether an existing bullet can describe it.

Explain benefits before implementation. For example, write “See which input triggered an alarm” in the README; document `alarm_inputs` and `alarm_input_names` in the entity guide.

Keep important capability limits visible where they affect a reader's decision, such as the distinction between controllable DGP doors and read-only RAS objects. Link to the detailed explanation.

Do not add full configuration tables, lengthy YAML examples, raw packets, hexadecimal mappings, diagnostic logs, release-by-release notes or troubleshooting histories to the README. Put those in their assigned guides and add a short link when useful.

### Header, banner and badges

- Preserve the current banner, title, tagline, alignment and header links during ordinary documentation maintenance.
- Keep the existing `for-the-badge` style and colour scheme. The current badge labels use dark `282a36`, with pink `ff79c6`, blue `41bdf5` and purple `bd93f9` accents.
- Retain the Release, HACS, Checks and Licence badges. Additional badges should have a clear user purpose and should not crowd the header.
- Keep release, licence and check results dynamic. Never hardcode “passing”, invent a workflow, or update a release badge by typing a version into it.
- Describe HACS as a **custom repository** unless the project's distribution status has actually changed and been verified.
- Link the Checks badge to the actual validation workflow and use its intended branch. Check paths if workflows are renamed.
- Preserve meaningful image alternative text and the banner's aspect ratio. Do not stretch, crop or replace the artwork as a side effect of a text update.
- Keep external badge/image URLs valid. Use `&amp;` between query parameters inside HTML attributes.

### Writing style

Write for someone who uses Home Assistant but may not know the Tecom protocol or programming terminology.

- Use plain English, short paragraphs and direct instructions.
- Use Australian English in prose: “behaviour”, “colour”, “licence” and “synchronisation”. Preserve exact spelling in code, identifiers and interface labels.
- Explain unfamiliar terms on first use where readers need them, such as an input being “sealed” or “unsealed”.
- Use the current interface labels for settings and actions. Do not invent a menu path or assume an older screen is still current.
- Distinguish what the integration provides, what the companion tiles display, and what users must configure themselves.
- Avoid marketing claims such as “perfectly reliable”, “fully supported” or “works with every panel”. State the actual supported behaviour.
- Keep historical faults and their version-specific fixes in the changelog. Include a brief troubleshooting reference only where it still helps affected users.
- Put a practical limitation beside the feature or example it affects. Avoid repeating the same disclaimer throughout the documentation.

### Markdown formatting

Use GitHub-flavoured Markdown that renders directly on GitHub.

- Each normal guide starts with one `# Page title`. Use `##` for main sections and `###` for subsections. Avoid deeper nesting unless necessary.
- Keep the existing HTML `<h1>` in the root README; do not add a second Markdown H1.
- Use sentence case for headings. Do not wrap headings in extra bold formatting.
- Leave blank lines around headings, paragraphs, lists, tables and fenced code blocks.
- Use numbered lists for procedures and bullets for parallel options or features.
- Use tables for exact mappings, settings, defaults and comparisons. Keep cells concise; move long explanations below the table.
- Use **bold** for interface labels and important distinctions. Use `inline code` for filenames, paths, entity IDs, service names, attribute names and literal values.
- Use fenced blocks with a language label such as `yaml`, `json`, `python`, `bash` or `text`.
- Use ordinary Markdown for guide content. Reserve HTML for the existing centred README header or another clear rendering need; do not introduce HTML page layouts, scripts or custom CSS.
- Do not add YAML front matter, Obsidian wikilinks, embedded base64 images, plugin-specific callouts or footnote syntax such as `[^1]`.
- Cite external documentation with ordinary descriptive Markdown links beside the relevant explanation. Never leave chat citation tokens or placeholder references in a committed file.
- Escape literal pipe characters in table cells where needed, including pipes inside inline code.

### Navigation, filenames and links

Each guide in `docs/` should have a short navigation line below its title, normally beginning:

```markdown
[← Documentation](README.md)
```

The documentation index links back to the project front page:

```markdown
[← Back to TecomHA](../README.md)
```

Use relative links for repository files:

| Link location | Example |
| --- | --- |
| Root README to a guide | `[Configuration](docs/configuration.md)` |
| One guide to another | `[Entities](entities.md)` |
| A guide to the root changelog | `[Changelog](../CHANGELOG.md)` |
| A guide to a section | `[Polling](configuration.md#polling)` |

Use full HTTPS links for other repositories and external documentation. Never commit `sandbox:` links, local workspace paths or temporary download links.

Preserve existing filenames and case. New guide names should use lowercase words separated by hyphens, such as `panel-setup.md`. `README.md`, `CHANGELOG.md` and `CLAUDE.md` retain their established names.

Changing a heading may change its GitHub anchor. Update incoming links and verify the resulting anchor, especially when punctuation is involved.

### Examples and technical accuracy

Read the relevant current implementation before documenting behaviour. Useful sources include `const.py`, `config_flow.py`, translations, entity platforms, `services.yaml`, service handlers, the manifest, workflows and the companion tiles repository. Comments and older documentation can be stale; check what the code actually does.

Do not infer hardware support from a generic protocol capability. Keep capture-confirmed behaviour, code behaviour and unverified assumptions distinct. If evidence conflicts, explain the discrepancy rather than silently choosing a convenient claim.

For YAML and action examples:

- Use consistent two-space YAML indentation and quote literal state strings such as `"on"` and `"off"`.
- Say whether the block is a complete automation, a card, an action or a fragment to add to another example.
- Use generic entities such as `lock.front_entry` and explain that readers must replace them with their actual IDs.
- State required cards, helpers, schedules, scenes or notification services. Do not present an example-only entity as something TecomHA automatically creates.
- Give complete examples for the scope described; avoid ellipses in copyable code.
- Verify service parameters, entity targeting and behaviour when several panels are loaded. Never assume an action affects only one panel.
- Check trigger behaviour around startup, unavailable states, repeated events and timer resets where relevant to the example.
- Keep credentials, card/PIN information and real site/user data out of examples and screenshots.

Preserve these distinctions unless verified implementation changes require an update:

- Door **lock state** and physical **contact state** are separate.
- Momentary **Open** and latched **Unlock** are different actions.
- **Force arm** does not mean unsealed inputs are isolated.
- CTPlus name imports apply to configured, loaded objects; they do not create additional entities.
- Object-name imports and access user-name downloads are separate features.
- A tile's linked schedule indicator is not an automatic import of Tecom timezones.
- A configured polling interval does not imply that runtime polling is enabled for every object group.
- A maintenance buffer reset is not a routine event retrieval operation.

### Changelog entries

A changelog entry should record what changed, **the evidence it rests on**, and anything a user must do on upgrade. Behaviour changes to existing service calls must be called out explicitly — several releases have altered what an existing call does.

### Update workflow

1. Read the current README, documentation index, affected guides and relevant implementation. Review the change being documented.
2. Identify which guide owns the detailed explanation. Update that guide first, including defaults, limitations and examples that the change affects.
3. Update related guides where necessary, using links instead of duplicating entire explanations.
4. Update the root README only when a user-facing capability, prerequisite, key limitation or navigation link has changed. Routine fixes do not automatically need another README bullet.
5. Record release-specific changes in `CHANGELOG.md` under the appropriate `## Version X.Y.Z` heading. Preserve the format required by the release workflow. Do not invent a release or bump the integration version solely for a documentation tidy-up.
6. Review all links, headings, examples and screenshots affected by the edit. If information moves, ensure its useful content remains available in the new location.
7. Report the files changed, the practical documentation changes and the checks actually performed. Identify any unresolved accuracy questions.

Keep documentation edits focused. Do not modify integration code, workflows, branding or unrelated repository instructions merely to make documentation statements true.

### Checks before finishing

- Preview changed Markdown and confirm headings, lists, tables, HTML header elements and code fences render properly.
- Check relative file links and section anchors, including links in the documentation index and root README.
- Parse changed YAML/JSON examples where practical. Syntax validation alone does not establish that an automation works on a live panel.
- Confirm documented service names, fields, defaults and supported features against the current source.
- Check that moved information has not been lost, and that duplicate explanations do not disagree.
- Check for real credentials/site data, placeholder text, broken image references and leftover chat formatting.
- Run `git diff --check` and review the final diff for unintended changes.

For documentation-only work, validate the documentation; there is no need to claim or perform panel/protocol testing unless a specific change requires it. Code changes and releases remain subject to the repository's existing validation requirements. Report any checks you could not perform accurately.

---

## 13. Release process

1. Run `tools/validate_project.py` and `pytest tests/`. Report results.
2. Replay debug dumps against a baseline and confirm no unintended decode changes.
3. Bump `version` in `manifest.json`.
4. Add a `## Version X.Y.Z` section to `CHANGELOG.md`.
5. Commit, tag `vX.Y.Z`, push with tags.
6. `.github/workflows/release.yml` verifies the tag matches the manifest, extracts the changelog section, builds the archive and publishes the release.

When a change alters what is sent to the panel based on stored configuration,
consider whether existing entries were relying on the old behaviour. Path
authentication is the worked example: the computer password field was ignored
for years, so every working install is using the panel default whatever the
field contains. The migration pins them to that value rather than trusting what
is stored, because trusting it would break them.

Version numbers are cheap but should not be invented casually. A run of releases was once created in a single session without being published, leaving gaps that had to be unwound. Prefer one release per coherent set of changes.

Commits: short imperative subject, and where a protocol value changed, name the evidence.

```
Fix door status word byte order

Captured door 18 in all four lock/contact combinations. The word is big
endian; little endian put the contact bit in the wrong half, so open doors
reported as closed.
```

---

## 14. Working style

- **Read a file before editing it.** Do not assume its current state matches an earlier conversation. A stale assumption once produced an incorrect claim that a feature was unimplemented when it was already wired up.
- **Correct previous conclusions out loud.** If an earlier finding was wrong, say so plainly rather than quietly changing course. Two conclusions in this project's history were wrong and needed retracting.
- **Prefer one targeted capture over a plausible guess.**
- **Report problems found in the user's setup**, even when unrelated to the task. A faulty EOL resistor, an unconfigured input and a credential leak in debug dumps were all found this way.
- **Do not overstate confidence.** "Confirmed from capture" and "inferred from the event table" are different claims and should read differently.
