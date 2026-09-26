from __future__ import annotations

import copy
import csv
import gzip
import json
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
MAPPING = ROOT / "channels.csv"

SOURCES = [
    ("japanterebi", "https://animenosekai.github.io/japanterebi-xmltv/guide.xml"),
    ("karenda", "https://raw.githubusercontent.com/karenda-jp/etc/refs/heads/main/guides.xml"),
    ("epgshare-jp1", "https://epgshare01.online/epgshare01/epg_ripper_JP1.xml.gz"),
    ("epgshare-jp2", "https://epgshare01.online/epgshare01/epg_ripper_JP2.xml.gz"),
]

REFERENCE_IDS = [
    "Pigoo.jp",
    "VParadise.jp",
    "PlayboyChannel.jp",
    "MidnightBlue.jp",
    "ParadiseTV.jp",
    "RedCherry.jp",
]


def download_xml(name: str, url: str) -> ET.Element:
    request = urllib.request.Request(url, headers={"User-Agent": "japan-iptv-epg-builder/1.0"})
    with urllib.request.urlopen(request, timeout=90) as response:
        payload = response.read()
    if url.endswith(".gz"):
        payload = gzip.decompress(payload)
    root = ET.fromstring(payload)
    if root.tag != "tv":
        raise RuntimeError(f"{name}: XMLTV root is {root.tag!r}, expected 'tv'")
    return root


def programme_key(programme: ET.Element) -> tuple[str, str, str, str]:
    return (
        programme.get("channel", ""),
        programme.get("start", ""),
        programme.get("stop", ""),
        programme.findtext("title", default=""),
    )


def main() -> None:
    PUBLIC.mkdir(parents=True, exist_ok=True)
    channels: dict[str, ET.Element] = {}
    programmes: dict[str, list[ET.Element]] = defaultdict(list)
    seen_programmes: set[tuple[str, str, str, str]] = set()
    source_stats: list[dict[str, object]] = []

    for name, url in SOURCES:
        root = download_xml(name, url)
        source_channels = root.findall("channel")
        source_programmes = root.findall("programme")
        source_stats.append(
            {"name": name, "url": url, "channels": len(source_channels), "programmes": len(source_programmes)}
        )
        for channel in source_channels:
            channel_id = channel.get("id", "")
            if channel_id and channel_id not in channels:
                channels[channel_id] = channel
        for programme in source_programmes:
            channel_id = programme.get("channel", "")
            key = programme_key(programme)
            if channel_id and key not in seen_programmes:
                programmes[channel_id].append(programme)
                seen_programmes.add(key)

    requested: dict[str, str] = {}
    with MAPPING.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            playlist_id = row.get("tvg_id", "").strip()
            source_id = row.get("source_id", "").strip()
            if playlist_id and source_id:
                requested.setdefault(playlist_id, source_id)
    for reference_id in REFERENCE_IDS:
        requested.setdefault(reference_id, reference_id)

    output = ET.Element(
        "tv",
        {
            "generator-info-name": "Japan IPTV EPG cloud builder",
            "generator-info-url": "https://github.com/iptv-org/epg",
        },
    )
    missing_source_ids: list[dict[str, str]] = []
    programme_total = 0
    for playlist_id, source_id in requested.items():
        source_channel = channels.get(source_id)
        if source_channel is None:
            missing_source_ids.append({"tvg_id": playlist_id, "source_id": source_id})
            continue
        channel = copy.deepcopy(source_channel)
        channel.set("id", playlist_id)
        output.append(channel)
    for playlist_id, source_id in requested.items():
        if source_id not in channels:
            continue
        for source_programme in programmes.get(source_id, []):
            programme = copy.deepcopy(source_programme)
            programme.set("channel", playlist_id)
            output.append(programme)
            programme_total += 1

    channel_total = len(output.findall("channel"))
    if channel_total < 105 or programme_total < 5000:
        raise RuntimeError(
            f"Refusing to publish incomplete guide: channels={channel_total}, programmes={programme_total}"
        )

    ET.indent(output, space="  ")
    xml_path = PUBLIC / "japan_iptv_epg.xml"
    ET.ElementTree(output).write(xml_path, encoding="utf-8", xml_declaration=True)
    with xml_path.open("rb") as source, gzip.open(PUBLIC / "japan_iptv_epg.xml.gz", "wb", compresslevel=9) as target:
        target.write(source.read())

    generated_at = datetime.now(timezone.utc).isoformat()
    status = {
        "generated_at_utc": generated_at,
        "channels": channel_total,
        "programmes": programme_total,
        "missing_source_ids": missing_source_ids,
        "sources": source_stats,
    }
    (PUBLIC / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
