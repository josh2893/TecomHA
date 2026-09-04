# TecomHA 3.4.3 — Stable release

This is the first stable release of the 3.4 series. It brings together the
authentication, encryption, setup and artwork changes from the 3.4.0–3.4.2
pre-releases, and adds named door Activity entries and confirmed access-denial
handling. These notes describe the combined build, including corrections to
the earlier encryption notes.

### Named access activity

Door Activity entries now show the action and, where the panel supplies a user
number and name sync has resolved it, the cardholder's name. Home Assistant
supplies the door's entity label; the message does not repeat the door name.

For an entity labelled **Front Entry Access**, the message will look like this:

| Situation | Activity message |
| --- | --- |
| Access granted to a known user | `Access granted - J. Smith` |
| Access granted, name not synced | `Access granted - User 1041` |
| Panel-generated release with no user | `Access granted - System` |
| Exit-button release with no user | `Access granted (exit button)` |
| Explicit void denial, known user | `Access denied - J. Smith (void)` |
| Explicit void denial, name not synced | `Access denied - User 1041 (void)` |
| Card rejection without an identified user | `Access denied - Card rejected` |
| Door forced | `Door forced` |
| Door held open too long | `Door open too long` |

The old Activity formatter resolved the entity only when describing an event.
Home Assistant had already filtered by entity/device before that point, so
named entries could disappear when viewing a particular door. The new dedicated
Activity event carries both identifiers when it is recorded. Door entities
also check the configuration entry ID, keeping matching door numbers on
different panels separate.

The message records the name available at the time. Later name changes or an
integration unload do not change that historical message. A rejected card,
anonymous release or exit-button event is never attributed to the previous
successful cardholder. Denials leave the last-successful-user attributes intact.
Retransmitted copies of a panel event do not create extra access records or
advance the last-access timestamp; a new swipe remains a separate event.

Home Assistant may also show its native event-type row. **Event detected** is a
frontend fallback when an event type is absent; it is not evidence on its own
that the integration reloaded. History retains the event entity's timestamp
state; the detailed wording belongs in Activity. Existing historical entries
are not rewritten. Do not exclude the access entity from Logbook to hide the
native row: that can hide the named entry as well.

### Confirmed access-denial events

Two denial layouts are supported, correlated with the supplied Home Assistant
debug frames and CTPlus screenshots at the matching timestamps:

| Code | Confirmed behaviour |
| --- | --- |
| `0x4B` | Card rejection. The door is the final byte of the 14-byte event body; the six preceding bytes are card data, not an object or user number. |
| `0x8B` | Explicit void denial. The event carries a door number and a full two-byte user number. |

The `0x4B` layout was confirmed on two different doors. Both an unregistered
card and a voided registered card produced that code, so it is described as
**Card rejected**, not automatically **Unknown card**. The registered-card
example still reported **void** in CTPlus and used `0x8B`; it does not establish
a separate “not in access group” mapping. Other denial layouts remain unverified.

The existing door event entity adds `access_denied` and `access_denied_void`.
No additional entities are created. The general decoded event includes
`denial_reason` (`card_rejected` or `void`) and `entry_id`. Automations that mean
“someone gained access” should filter for the granted event types rather than
triggering indiscriminately on every access-entity update.

### Path authentication

The configured computer/security password is now sent. Before the 3.4 series,
the field was ignored and the integration always sent the panel's documented
default, `0000000000`.

Both authentication methods are available:

| Method | Frame |
| --- | --- |
| Security / computer password | `01 06 0B` + five bytes packed BCD, with digits swapped within each byte |
| Path user name and password | `01 31 0A 1E` + 30-byte user name + `10` + 16-byte password, ASCII null padded |

Select the same **Authentication type** on the dedicated panel path and in Home
Assistant. Path credentials are supported by ChallengerPlus, Discovery, NACs
and Challenger from firmware V10-06.19251. The documented default security
password cannot be used by a client connecting over DHCP.

The panel can acknowledge the session hello and then stop responding when
authentication is rejected. Setup validates credential formats so a typo is
less likely to appear as an unexplained offline panel. Silence is a diagnostic
clue, not proof of a particular credential failure.

### Encrypted UDP connections

All three ciphers work through the same transport wrapper with either
computer/security password or path user name/password authentication:

| Panel setting | Key limit |
| --- | --- |
| AES CBC (128 bit) | Up to 16 ASCII alphanumeric characters |
| AES CBC (256 bit) | Up to 32 ASCII alphanumeric characters |
| TwoFish (128 bit) | Up to 16 ASCII alphanumeric characters |

A 10-character alphanumeric key is valid with AES-256. It does not need to be
exactly 32 characters. The encryption key and security password are separate
settings; using the default security password does not change the key limit.

Keys are raw ASCII padded with zeros to the cipher's key length. A long mixed
key provides more key entropy than a short numeric one at the same cipher
setting. Padding the key does not make a short key equivalent to a random
256-bit key.

The correct UDP wrapper is a **16-byte IV**, a **two-byte big-endian plaintext
length**, and **CBC ciphertext zero-padded to a block boundary**. The ciphertext
ends at the UDP payload boundary. **There is no four-byte trailer.**

The 3.4.0/3.4.1 reader accidentally included the repeated PCAPNG block length as
packet data. This led to extra outgoing bytes and rejected replies. The reader
now respects capture, IPv4 and UDP lengths, excluding file padding, options and
block footers. The old 292-datagram compatibility claim is superseded by the
corrected validation below.

Immediate host acknowledgements now use encryption too, and the asynchronous
fallback encrypts exactly once. The transport verifies decrypted frame CRCs,
wrapper lengths and zero padding. Repeated decryption failures are counted and
logged with a useful explanation; valid traffic resets the consecutive count.

TwoFish is implemented within the integration and checked against published
test vectors. It is slower than AES but adds no runtime dependency. The
integration's manifest still declares no additional dependencies.

**Encryption support and capture validation cover UDP. Encrypted TCP is not
implemented.**

### Setup and options screens

The former 51-field form is grouped into collapsible sections: Connection,
Authentication and encryption, Panel objects, Naming, Object polling, Door
polling detail, User name sync, and Advanced. Only Connection opens initially.
Each field has an explanation, including:

- DGP door and relay ranges support gaps and avoid creating unused entities.
- Input polling is useful for motion detectors that do not send seal events;
  other polling toggles explain when they are needed.
- CTPlus is the confirmed input mapping; alternatives are for older setups.
- Diagnostic controls are grouped in Advanced.

The same sections appear in setup and Options. Errors now appear above the
affected section, which expands for correction. Submitted values are retained.
Previously, errors returned under nested field names could be invisible, making
Submit appear to reopen Connection without saving. Non-ASCII credentials are
also rejected before reaching the ASCII wire encoder.

Options already requests an integration reload after a successful save. The
reported AES-256/security-password installation connected after a reload;
there is no new session-timing workaround in this build. If the panel path is
changed after Home Assistant has already reloaded, reload the integration once
both ends have matching settings.

### User name order

The **User name order** setting can present two-word names given-name first.
For example, `Smith John` becomes `John Smith`. It defaults to leaving names as
the panel stores them. Only names of exactly two words are swapped; descriptive
entries such as `Card 3 Lock Box` and single-word names remain unchanged.

Names are cached in their panel order and formatted when read. Changing the
setting takes effect without downloading the user database again. New Activity
entries use the newly formatted name; previously recorded messages keep their
original wording.

### New TecomHA artwork

The supplied design replaces the old integration logo. All eight local brand
assets are included: icon and logo, normal and dark variants, each at standard
and high-density size. Standard files are **256 × 256**; `@2x` files are
**512 × 512**. The supplied design's own background is retained in both themes,
preserving its colours and proportions. Local brand assets require Home
Assistant 2026.3 or later; refresh the frontend if old artwork remains cached.

### Diagnostics and privacy

Debug dumps include authentication method, cipher and decryption-failure count,
without passwords or keys. Authentication and user-record raw hex is redacted,
including structured copies and acknowledgement references.

This build also redacts the confirmed `0x4B` card-bearing bodies from debug
frames, ACK references, last-event/retry diagnostics and the raw event bus.
Malformed bodies recognisable as that code are redacted too. The decoded event
retains the door and rejection reason, with `raw_redacted: true`, without
publishing the card bytes. These protections do not claim to identify every
unverified protocol variant. Existing dump files are not rewritten.

Access diagnostics count denials separately and do not mistake card bytes for
a user number. User names are omitted from dump output; site/network details
can still be present.

### Validation

- **226 automated tests passed** in a fresh Python 3.12 virtual environment
  using only the declared test dependencies. This includes 30 new Activity,
  denial, panel-isolation, retry and redaction checks.
- **785 structured received data frames** from the four supplied denial dumps
  were compared with 3.4.2: 757 decodes were unchanged; all 28 differences were
  the intended denial-field corrections. Overlapping dumps contain repeated
  observations of the same event.
- **16 distinct denial events**—13 card rejections and three explicit void
  denials—were replayed through the real hub, event entity and Activity
  formatter with Home Assistant service doubles. The events retain entity and
  device identifiers, preserve last successful access and redact card data.
- The unchanged encryption implementation retains the earlier validation of
  **552 encrypted UDP datagrams across 12 CTPlus captures**, covering all three
  ciphers with both authentication methods. Those packets passed CRC checks
  and byte-identical re-encryption; authentication and ACK sends matched each
  capture. The current crypto and transport regression tests also pass.
- Structural validation, dependency consistency and whitespace checks pass.

The user has confirmed a live AES-256 connection with computer/security
password authentication after reloading. The new Activity presentation has
been tested with production Python modules and HA service doubles; it has not
been visually verified on the user's live Home Assistant installation.

### Upgrading

Replace `custom_components/tecom_challengerplus` with this build and **restart
Home Assistant**. Do not remove and re-add the integration. Existing entity IDs
and last-successful-user attributes are retained. Custom cards should use those
last-successful-user attributes when displaying who last gained access.

Settings saved by the 3.4.0–3.4.2 pre-releases are preserved, with no additional
config-entry migration. Check that Home Assistant and the dedicated panel path
have matching authentication method, credentials, cipher and key.

Installations from before 3.4.0 migrate to config-entry version 2. Their method
is explicitly set to security password and the password is pinned to
`0000000000`, the value every working older installation actually sent,
regardless of the ignored field. If the panel uses a different password, or you
want path credentials or encryption, configure those settings in Options.
Legacy encryption names are mapped to the current names.

After restarting, swipe a card and check the door's Activity. Enable or run user
name sync if it shows a user number. Rich entries begin with new events; old
Activity is not backfilled.
