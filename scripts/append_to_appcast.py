"""Append a new release entry to ``docs/appcast.xml``.

Called by the release CI workflow after a DMG has been built, signed, and
uploaded to a GitHub Release. Keeps the XML well-formed by parsing with
``xml.etree`` rather than templating strings.

Usage::

    python scripts/append_to_appcast.py \\
        --version 0.1.0 \\
        --dmg dist/discogs_alert-0.1.0.dmg \\
        --signature 'sparkle:edSignature="…" length="…"' \\
        --download-url 'https://github.com/…/releases/download/v0.1.0/foo.dmg' \\
        --notes 'First release.'

The ``--signature`` argument is the full ``sparkle:edSignature="…"
length="…"`` string that ``sign_update`` prints. The script parses it
out and attaches both attributes to the new ``<enclosure>`` element.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

NSMAP = {
    "sparkle": "http://www.andymatuschak.org/xml-namespaces/sparkle",
    "dc": "http://purl.org/dc/elements/1.1/",
}

# We register the namespaces so ElementTree emits the right prefixes.
for prefix, uri in NSMAP.items():
    ET.register_namespace(prefix, uri)


def _parse_signature_line(line: str) -> tuple[str, str]:
    """Pull the ``sparkle:edSignature`` and ``length`` values out of the
    string ``sign_update`` prints. The exact format is::

        sparkle:edSignature="aBcDe…=" length="12345"

    Returns ``(signature, length)``.
    """

    sig_match = re.search(r'sparkle:edSignature="([^"]+)"', line)
    len_match = re.search(r'length="(\d+)"', line)
    if not sig_match or not len_match:
        raise ValueError(
            f"Couldn't parse sign_update output {line!r}; "
            "expected `sparkle:edSignature=\"…\" length=\"…\"`"
        )
    return sig_match.group(1), len_match.group(1)


def _make_item(
    version: str,
    download_url: str,
    signature: str,
    length: str,
    notes: str,
    pub_date: datetime,
) -> ET.Element:
    """Build a single ``<item>`` element matching the schema Sparkle expects."""

    item = ET.Element("item")
    ET.SubElement(item, "title").text = version
    # RFC 822 / RFC 2822 date format — what Sparkle wants.
    ET.SubElement(item, "pubDate").text = pub_date.strftime("%a, %d %b %Y %H:%M:%S +0000")

    sparkle_version = ET.SubElement(item, f"{{{NSMAP['sparkle']}}}version")
    sparkle_version.text = version
    sparkle_short = ET.SubElement(item, f"{{{NSMAP['sparkle']}}}shortVersionString")
    sparkle_short.text = version
    min_macos = ET.SubElement(item, f"{{{NSMAP['sparkle']}}}minimumSystemVersion")
    min_macos.text = "11.0"

    description = ET.SubElement(item, "description")
    # CDATA isn't first-class in ElementTree; the simplest approach is to
    # just put HTML in the text and let the XML parser handle escaping.
    # Sparkle treats <description> contents as HTML regardless.
    description.text = notes

    enclosure = ET.SubElement(item, "enclosure")
    enclosure.set("url", download_url)
    enclosure.set(f"{{{NSMAP['sparkle']}}}edSignature", signature)
    enclosure.set("length", length)
    enclosure.set("type", "application/octet-stream")

    return item


def append_item(
    appcast_path: Path,
    version: str,
    download_url: str,
    signature: str,
    length: str,
    notes: str,
    pub_date: datetime | None = None,
) -> None:
    """Insert a new ``<item>`` at the top of the existing channel."""

    pub_date = pub_date or datetime.now(timezone.utc)

    tree = ET.parse(appcast_path)
    root = tree.getroot()
    channel = root.find("channel")
    if channel is None:
        raise ValueError(f"{appcast_path} has no <channel> element")

    # Refuse to add a duplicate version — protects against re-run safety.
    sparkle_version_tag = f"{{{NSMAP['sparkle']}}}version"
    for existing in channel.findall("item"):
        existing_ver = existing.find(sparkle_version_tag)
        if existing_ver is not None and existing_ver.text == version:
            print(
                f"appcast already contains an item for {version}; not appending again",
                file=sys.stderr,
            )
            return

    item = _make_item(version, download_url, signature, length, notes, pub_date)

    # Insert right after the static channel headers (title/link/description/language)
    # so the newest item is always at the top of the items list. Find the index
    # of the first existing <item>, or append after the last header.
    children = list(channel)
    insert_at = len(children)
    for idx, child in enumerate(children):
        if child.tag == "item":
            insert_at = idx
            break
    channel.insert(insert_at, item)

    # Pretty-print: ET.indent is 3.9+, which we use everywhere.
    ET.indent(tree, space="    ", level=0)
    tree.write(appcast_path, xml_declaration=True, encoding="utf-8")
    # ElementTree adds a trailing newline only sometimes; normalise.
    contents = appcast_path.read_text()
    if not contents.endswith("\n"):
        appcast_path.write_text(contents + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--version", required=True, help="Release version, e.g. 0.1.0")
    parser.add_argument(
        "--signature",
        required=True,
        help='Full sign_update output, e.g. \'sparkle:edSignature="…" length="…"\'',
    )
    parser.add_argument(
        "--download-url",
        required=True,
        help="Public URL of the .dmg in the GitHub Release.",
    )
    parser.add_argument(
        "--notes",
        default="",
        help="Optional HTML release notes to put in <description>.",
    )
    parser.add_argument(
        "--appcast-path",
        type=Path,
        default=Path("docs/appcast.xml"),
        help="Path to the appcast.xml to update.",
    )
    args = parser.parse_args(argv)

    signature, length = _parse_signature_line(args.signature)
    notes = args.notes or f"<h2>{args.version}</h2>"
    append_item(
        appcast_path=args.appcast_path,
        version=args.version,
        download_url=args.download_url,
        signature=signature,
        length=length,
        notes=notes,
    )
    print(f"Appended {args.version} to {args.appcast_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
