"""Tests for the appcast appender script.

The script lives in ``scripts/`` (outside the package) so we import it
the slightly-awkward way: by adding ``scripts/`` to sys.path and
importing the module directly.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

# Make the script importable.
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import append_to_appcast as appender  # noqa: E402,I001


SKELETON = """<?xml version="1.0" standalone="yes"?>
<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle" xmlns:dc="http://purl.org/dc/elements/1.1/">
    <channel>
        <title>discogs_alert</title>
        <link>https://github.com/michaelhball/discogs_alert</link>
        <description>Most recent macOS releases.</description>
        <language>en</language>
    </channel>
</rss>
"""


@pytest.fixture
def appcast(tmp_path: Path) -> Path:
    path = tmp_path / "appcast.xml"
    path.write_text(SKELETON)
    return path


def _items(path: Path) -> list[ET.Element]:
    tree = ET.parse(path)
    return tree.findall(".//item")


# -- _parse_signature_line --------------------------------------------------


def test_parse_signature_line_extracts_both():
    sig, length = appender._parse_signature_line(
        'sparkle:edSignature="ABC=" length="12345"'
    )
    assert sig == "ABC="
    assert length == "12345"


def test_parse_signature_line_handles_extra_whitespace():
    sig, length = appender._parse_signature_line(
        '    sparkle:edSignature="ABC=" length="12345"\n'
    )
    assert sig == "ABC="
    assert length == "12345"


def test_parse_signature_line_rejects_unparseable():
    with pytest.raises(ValueError):
        appender._parse_signature_line("not the right shape")


# -- append_item ------------------------------------------------------------


def test_append_inserts_new_item(appcast: Path):
    appender.append_item(
        appcast_path=appcast,
        version="0.1.0",
        download_url="https://example.com/foo.dmg",
        signature="SIG=",
        length="123",
        notes="<h2>0.1.0</h2>",
        pub_date=datetime(2026, 5, 9, 18, 30, 0, tzinfo=timezone.utc),
    )
    items = _items(appcast)
    assert len(items) == 1
    item = items[0]
    assert item.find("title").text == "0.1.0"
    assert item.find(
        "{http://www.andymatuschak.org/xml-namespaces/sparkle}version"
    ).text == "0.1.0"
    enclosure = item.find("enclosure")
    assert enclosure.get("url") == "https://example.com/foo.dmg"
    assert enclosure.get(
        "{http://www.andymatuschak.org/xml-namespaces/sparkle}edSignature"
    ) == "SIG="
    assert enclosure.get("length") == "123"


def test_append_pubdate_is_rfc822(appcast: Path):
    appender.append_item(
        appcast_path=appcast,
        version="0.1.0",
        download_url="x",
        signature="x",
        length="0",
        notes="",
        pub_date=datetime(2026, 5, 9, 18, 30, 0, tzinfo=timezone.utc),
    )
    pub_date = _items(appcast)[0].find("pubDate").text
    assert pub_date == "Sat, 09 May 2026 18:30:00 +0000"


def test_append_is_idempotent_per_version(appcast: Path):
    """Running with the same version twice must not double-insert."""

    for _ in range(2):
        appender.append_item(
            appcast_path=appcast,
            version="0.1.0",
            download_url="x",
            signature="x",
            length="0",
            notes="",
        )
    assert len(_items(appcast)) == 1


def test_append_keeps_newest_at_top(appcast: Path):
    """A second release should land *before* the first."""

    appender.append_item(
        appcast_path=appcast,
        version="0.1.0",
        download_url="x",
        signature="x",
        length="0",
        notes="",
    )
    appender.append_item(
        appcast_path=appcast,
        version="0.1.1",
        download_url="x",
        signature="x",
        length="0",
        notes="",
    )
    items = _items(appcast)
    assert len(items) == 2
    assert items[0].find("title").text == "0.1.1"
    assert items[1].find("title").text == "0.1.0"


def test_append_rejects_appcast_without_channel(tmp_path: Path):
    path = tmp_path / "broken.xml"
    path.write_text('<?xml version="1.0"?><rss version="2.0"></rss>')
    with pytest.raises(ValueError, match="no <channel>"):
        appender.append_item(
            appcast_path=path,
            version="0.1.0",
            download_url="x",
            signature="x",
            length="0",
            notes="",
        )


# -- main (smoke) -----------------------------------------------------------


def test_main_smoke(appcast: Path, capsys: pytest.CaptureFixture):
    appender.main(
        [
            "--version", "0.1.0",
            "--signature", 'sparkle:edSignature="SIG=" length="42"',
            "--download-url", "https://example.com/x.dmg",
            "--appcast-path", str(appcast),
        ]
    )
    captured = capsys.readouterr()
    assert "Appended 0.1.0" in captured.out

    items = _items(appcast)
    assert len(items) == 1
    assert items[0].find("enclosure").get("length") == "42"
