# Contributing

[← Documentation](README.md) · [Troubleshooting](troubleshooting.md) · [Protocol reference](protocol.md)

## Report a problem or suggest a feature

Open an [issue](https://github.com/josh2893/TecomHA/issues) and explain what you were trying to do, what happened and what you expected.

For a fault, include:

- Integration and Home Assistant versions.
- Panel model and firmware, where known.
- Relevant object numbers and entity states.
- The action and approximate time of the problem.
- Whether the same action works from the keypad or CTPlus.
- A [debug dump captured during the problem](troubleshooting.md#capture-a-debug-dump), with sensitive information reviewed before sharing.

Do not post passwords, encryption keys, card/PIN data or unreviewed panel exports. Use generic example names such as “Front Entry” where possible.

## Useful packet captures

Record one action per capture, with one client on the path. Note the starting and ending state, and compare CTPlus with Home Assistant under the same conditions.

For door behaviour, record lock mode and physical contact position separately. Captures covering all four locked/unlocked and open/closed combinations are more useful than unrelated logs from different times.

## Development

Read the repository's [development guidance](../CLAUDE.md) before changing protocol behaviour. It covers architecture, state precedence, known traps, privacy and release validation.

The existing validation commands are:

```bash
python3 tools/validate_project.py
python3 -m pytest tests/ -q
```

Use the dependencies declared in [requirements-test.txt](../requirements-test.txt) and the CI environment when validating a release. Protocol changes should include capture-backed tests and a changelog entry explaining their evidence and user impact.

## Keep documentation organised

- **[README.md](../README.md):** a short introduction, user-facing capabilities, examples and links to getting started.
- **`docs/`:** detailed setup, behaviour, examples and technical reference.
- **[CHANGELOG.md](../CHANGELOG.md):** release history, upgrade notes and protocol findings tied to a version.
- **[Tiles repository](https://github.com/josh2893/TecomHA-Tiles-and-Addons):** card installation, options and tile-specific compatibility.

When moving sections, update relative links and cross-references. Use standard GitHub Markdown links; no special Markdown plugins or footnote renderer is required.

### README badges

The header uses [Shields.io](https://shields.io/) badges in the `for-the-badge` style. Release, licence and validation badges obtain their values from GitHub; the HACS badge describes installation as a custom repository.

The validation badge is linked to the real [Validate workflow](https://github.com/josh2893/TecomHA/actions/workflows/validate.yml) on `main`. Its result updates from the workflow status; no passing result is hardcoded. Release and licence values do not need editing for each new version.

The existing GitHub-hosted banner is reused by URL. If replacing it, update the header image in the root README and keep meaningful alternative text.

### Integration icons and logos

Home Assistant uses the PNG files in `custom_components/tecom_challengerplus/brand/`. Standard icons and logos are 256 × 256 pixels; the `@2x` versions are 512 × 512. The `dark_` variants provide the same artwork for dark mode. The supplied design has its own dark background, so its colours and contrast are preserved in both themes.

The eight files are `icon.png`, `icon@2x.png`, `logo.png`, `logo@2x.png` and their `dark_` equivalents. Replace the full set together and retain the square aspect ratio. Local brand images are used from Home Assistant 2026.3 onwards, as described in the [Home Assistant brand image documentation](https://developers.home-assistant.io/docs/core/integration/brand_images/). Older versions may still display the cached remote artwork.
