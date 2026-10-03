from __future__ import annotations

import argparse
import csv
import gzip
import re
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MAPPING = ROOT / "channels.csv"

SOURCE_ALIASES = {
    "CH.635": "VParadise.jp",
    "CNNInternational.us": "76797",
    "JimJam.uk": "7218",
    "fastch_v2_asdrm": "FastTV_asdrm",
    "fastch_v2_bgolf": "FastTV_bgolf",
    "fastch_v2_busns": "FastTV_busns",
    "fastch_v2_camng": "FastTV_camng",
    "fastch_v2_comdy": "FastTV_comdy",
    "fastch_v2_entns": "FastTV_entns",
    "fastch_v2_goshogi": "FastTV_goshogi",
    "fastch_v2_hokkaido": "FastTV_hokkaido",
    "fastch_v2_jpthp": "FastTV_jpthp",
    "fastch_v2_kids": "FastTV_kids",
    "fastch_v2_krdrm": "FastTV_krdrm",
    "fastch_v2_news1": "FastTV_news1",
    "fastch_v2_pett1": "FastTV_pett1",
    "fastch_v2_recip": "FastTV_recip",
    "fastch_v2_samri": "FastTV_samri",
    "fastch_v2_snyon": "FastTV_snyon",
    "fastch_v2_tokai": "FastTV_tokai",
    "fastch_v2_travl": "FastTV_travl",
}

BLANK_ID_BY_CHANNEL_NUMBER = {
    "CH 108": "tokyomx1.jp",
    "AD907": "AdultIPTVLiveCams.int",
    "AD908": "AdultIPTVMILF.int",
    "AD909": "AdultIPTVPornstar.int",
    "AD910": "AdultIPTVPOV.int",
    "AD920": "AoShi2.tw",
    "AD922": "SexGirl.tw",
    "AD923": "JennyLive.int",
    "AD924": "MiamiTVMexico.mx",
    "AD925": "AdultIPTVAsian.int",
    "AD926": "AdultIPTVBlonde.int",
    "AD927": "Eropuls.de",
    "AD928": "CentoXCento.it",
}


def read_xml(path: Path) -> ET.Element:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rb") as handle:
        return ET.parse(handle).getroot()


def source_ids(paths: list[Path]) -> set[str]:
    result: set[str] = set()
    for path in paths:
        for channel in read_xml(path).findall("channel"):
            channel_id = channel.get("id", "").strip()
            if channel_id:
                result.add(channel_id)
    return result


def parse_playlist(path: Path) -> tuple[list[str], list[tuple[str, str]]]:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    channels: list[tuple[str, str]] = []
    for index, line in enumerate(lines):
        if not line.startswith("#EXTINF:"):
            continue
        name = line.split(",", 1)[1].strip() if "," in line else ""
        id_match = re.search(r'tvg-id="([^"]*)"', line)
        playlist_id = id_match.group(1).strip() if id_match else ""
        if not playlist_id:
            number_match = re.search(r'tvg-chno="([^"]+)"', line)
            number = number_match.group(1).strip() if number_match else ""
            playlist_id = BLANK_ID_BY_CHANNEL_NUMBER.get(number, "")
            if not playlist_id:
                raise RuntimeError(f"No stable tvg-id for playlist line {index + 1}: {line}")
            if id_match:
                start, stop = id_match.span(1)
                line = line[:start] + playlist_id + line[stop:]
            else:
                line = line.replace("#EXTINF:-1", f'#EXTINF:-1 tvg-id="{playlist_id}"', 1)
            lines[index] = line
        channels.append((playlist_id, name))
    return lines, channels


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("playlist", type=Path)
    parser.add_argument("catalog", nargs="*", type=Path)
    args = parser.parse_args()

    known_sources = source_ids(args.catalog)
    playlist_lines, playlist_channels = parse_playlist(args.playlist)
    names: dict[str, str] = {}
    for playlist_id, name in playlist_channels:
        names.setdefault(playlist_id, name)

    with MAPPING.open(encoding="utf-8-sig", newline="") as handle:
        existing = list(csv.DictReader(handle))

    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in existing:
        playlist_id = row.get("tvg_id", "").strip()
        if not playlist_id or playlist_id in seen:
            continue
        source_id = SOURCE_ALIASES.get(playlist_id, row.get("source_id", "").strip())
        display_name = names.get(playlist_id, row.get("display_name", "").strip())
        fallback_title = row.get("fallback_title", "").strip()
        if not source_id and not fallback_title:
            fallback_title = display_name or playlist_id
        rows.append(
            {
                "tvg_id": playlist_id,
                "source_id": source_id,
                "display_name": display_name,
                "fallback_title": fallback_title,
            }
        )
        seen.add(playlist_id)

    for playlist_id, display_name in playlist_channels:
        if playlist_id in seen:
            continue
        source_id = playlist_id if playlist_id in known_sources else SOURCE_ALIASES.get(playlist_id, "")
        rows.append(
            {
                "tvg_id": playlist_id,
                "source_id": source_id,
                "display_name": display_name,
                "fallback_title": "" if source_id else display_name,
            }
        )
        seen.add(playlist_id)

    with MAPPING.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("tvg_id", "source_id", "display_name", "fallback_title"),
            lineterminator="\n",
            quoting=csv.QUOTE_ALL,
        )
        writer.writeheader()
        writer.writerows(rows)

    args.playlist.write_text("\n".join(playlist_lines) + "\n", encoding="utf-8")
    print(
        f"playlist_channels={len(playlist_channels)} unique_ids={len(names)} "
        f"mapping_rows={len(rows)} fallback_rows={sum(not row['source_id'] for row in rows)}"
    )


if __name__ == "__main__":
    main()
