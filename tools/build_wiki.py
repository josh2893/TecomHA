#!/usr/bin/env python3
"""Build and validate the TecomHA GitHub Wiki from canonical repository docs."""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_BLOB_URL = "https://github.com/josh2893/TecomHA/blob/main"

DOC_PAGES = {
    "README.md": "Documentation.md",
    "configuration.md": "Configuration.md",
    "contributing.md": "Contributing.md",
    "dashboards-and-automations.md": "Dashboards-and-Automations.md",
    "entities.md": "Entities.md",
    "events-and-actions.md": "Events-and-Actions.md",
    "installation.md": "Installation.md",
    "panel-setup.md": "Panel-Setup.md",
    "protocol.md": "Protocol-Reference.md",
    "troubleshooting.md": "Troubleshooting.md",
}

ROOT_LINKS = {
    "CHANGELOG.md": f"{REPOSITORY_BLOB_URL}/CHANGELOG.md",
    "LICENSE": f"{REPOSITORY_BLOB_URL}/LICENSE",
    **{f"docs/{source}": target.removesuffix(".md") for source, target in DOC_PAGES.items()},
}

DOC_LINKS = {
    source: target.removesuffix(".md") for source, target in DOC_PAGES.items()
}

MARKDOWN_LINK = re.compile(r"(?P<prefix>\]\()(?P<target>[^)\s]+)(?P<suffix>\))")
HTML_LINK = re.compile(
    r'(?P<prefix>\bhref=["\'])(?P<target>[^"\']+)(?P<suffix>["\'])', re.IGNORECASE
)
MARKDOWN_IMAGE = re.compile(r'!\[[^\]]*\]\(([^)\s]+)(?:\s+["\'][^)]*["\'])?\)')
HTML_IMAGE = re.compile(r'<img\s+[^>]*src=["\']([^"\']+)["\']', re.IGNORECASE)


def split_fragment(target: str) -> tuple[str, str]:
    path, separator, fragment = target.partition("#")
    return path, f"#{fragment}" if separator else ""


def transform_target(target: str, *, root_document: bool) -> str:
    """Convert repository-relative documentation links into Wiki links."""
    if target.startswith(("http://", "https://", "mailto:", "tel:", "#")):
        return target

    path, fragment = split_fragment(target)
    if root_document:
        return ROOT_LINKS.get(path, path) + fragment

    if path == "../README.md":
        return "README" + fragment
    if path == "../CHANGELOG.md" and fragment == "#version-343":
        return "Release-Notes-3.4.3"
    if path.startswith("../"):
        return f"{REPOSITORY_BLOB_URL}/{path[3:]}{fragment}"
    return DOC_LINKS.get(path, path) + fragment


def transform_document(text: str, *, root_document: bool) -> str:
    def replace(match: re.Match[str]) -> str:
        target = transform_target(match.group("target"), root_document=root_document)
        return f'{match.group("prefix")}{target}{match.group("suffix")}'

    text = MARKDOWN_LINK.sub(replace, text)
    return HTML_LINK.sub(replace, text)


def slugify_heading(heading: str) -> str:
    heading = re.sub(r"<[^>]+>", "", heading)
    heading = re.sub(r"[`*_~]", "", heading).strip().lower()
    heading = re.sub(r"[^\w\- ]", "", heading)
    return re.sub(r" +", "-", heading)


def page_anchors(text: str) -> set[str]:
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    in_fence = False
    fence = ""

    for line in text.splitlines():
        fence_match = re.match(r"^\s*(`{3,}|~{3,})", line)
        if fence_match:
            marker = fence_match.group(1)[0]
            if not in_fence:
                in_fence, fence = True, marker
            elif marker == fence:
                in_fence, fence = False, ""
            continue
        if in_fence:
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if not heading_match:
            continue
        base = slugify_heading(heading_match.group(2))
        count = counts.get(base, 0)
        counts[base] = count + 1
        anchors.add(base if count == 0 else f"{base}-{count}")

    if in_fence:
        raise ValueError("unclosed fenced code block")
    return anchors


def validate_wiki(output: Path) -> None:
    pages = {page.stem: page for page in output.glob("*.md")}
    anchors: dict[str, set[str]] = {}
    errors: list[str] = []

    for name, page in pages.items():
        try:
            anchors[name] = page_anchors(page.read_text(encoding="utf-8"))
        except ValueError as error:
            errors.append(f"{page.name}: {error}")

    link_pattern = re.compile(
        r'(?<!!)\[[^\]]*\]\(([^)]+)\)|<a\s+[^>]*href=["\']([^"\']+)["\']',
        re.IGNORECASE,
    )
    output_root = output.resolve()

    for source_name, source in pages.items():
        in_fence = False
        fence = ""
        for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
            fence_match = re.match(r"^\s*(`{3,}|~{3,})", line)
            if fence_match:
                marker = fence_match.group(1)[0]
                if not in_fence:
                    in_fence, fence = True, marker
                elif marker == fence:
                    in_fence, fence = False, ""
                continue
            if in_fence:
                continue

            for match in link_pattern.finditer(line):
                target = (match.group(1) or match.group(2)).strip()
                if target.startswith(("http://", "https://", "mailto:", "tel:")):
                    continue
                target = unquote(target)
                if target.startswith("#"):
                    page_name, anchor = source_name, target[1:]
                else:
                    page_path, _, anchor = target.partition("#")
                    page_name = Path(page_path.removesuffix(".md")).name
                    if page_name not in pages:
                        errors.append(
                            f"{source.name}:{line_number}: missing Wiki page {target!r}"
                        )
                        continue
                if anchor and anchor not in anchors.get(page_name, set()):
                    errors.append(
                        f"{source.name}:{line_number}: missing anchor #{anchor} on {page_name}"
                    )

            for pattern in (MARKDOWN_IMAGE, HTML_IMAGE):
                for match in pattern.finditer(line):
                    target = unquote(match.group(1).strip())
                    if target.startswith(("http://", "https://", "data:")):
                        continue
                    image_path = target.partition("?")[0].partition("#")[0]
                    candidate = (source.parent / image_path).resolve()
                    try:
                        candidate.relative_to(output_root)
                    except ValueError:
                        errors.append(
                            f"{source.name}:{line_number}: image leaves Wiki output {target!r}"
                        )
                        continue
                    if not candidate.is_file():
                        errors.append(
                            f"{source.name}:{line_number}: missing image {target!r}"
                        )

    if errors:
        raise SystemExit("Wiki validation failed:\n- " + "\n- ".join(errors))

    print(f"Built and validated {len(pages)} Wiki pages in {output}")


def build_wiki(output: Path) -> None:
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    (output / "README.md").write_text(
        transform_document(readme, root_document=True), encoding="utf-8"
    )

    for source_name, target_name in DOC_PAGES.items():
        source = (ROOT / "docs" / source_name).read_text(encoding="utf-8")
        (output / target_name).write_text(
            transform_document(source, root_document=False), encoding="utf-8"
        )

    static_root = ROOT / ".github" / "wiki"
    for source in sorted(static_root.rglob("*")):
        if not source.is_file():
            continue
        target = output / source.relative_to(static_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    validate_wiki(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build_wiki(args.output.resolve())


if __name__ == "__main__":
    main()
