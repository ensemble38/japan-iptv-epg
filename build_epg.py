from __future__ import annotations

import copy
import csv
import gzip
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    (
        "xumo-us",
        "https://raw.githubusercontent.com/BuddyChewChew/xumo-playlist-generator/refs/heads/main/playlists/xumo_epg.xml.gz",
    ),
    (
        "lg-channels-us",
        "https://raw.githubusercontent.com/JulioCesarXY/EPG-LG-Channels/refs/heads/main/lg_epg_us.xml",
    ),
    # The former Taiwan aggregate mirror kept returning a large but expired
    # January/February 2026 guide.  Pull the live per-channel XMLTV endpoints
    # instead so a high programme count cannot hide stale data.
    ("epgpw-tw-456834", "https://epg.pw/api/epg.xml?channel_id=456834"),
    ("epgpw-tw-456835", "https://epg.pw/api/epg.xml?channel_id=456835"),
    ("epgpw-tw-456836", "https://epg.pw/api/epg.xml?channel_id=456836"),
    ("epgpw-tw-456838", "https://epg.pw/api/epg.xml?channel_id=456838"),
    ("epgpw-tw-456841", "https://epg.pw/api/epg.xml?channel_id=456841"),
    ("epgpw-tw-456842", "https://epg.pw/api/epg.xml?channel_id=456842"),
]

REFERENCE_IDS = [
    "Pigoo.jp",
    "VParadise.jp",
    "PlayboyChannel.jp",
    "MidnightBlue.jp",
    "ParadiseTV.jp",
    "RedCherry.jp",
]

FRESHNESS_REQUIRED_SOURCE_IDS = {
    "456834",
    "456835",
    "456836",
    "456838",
    "456841",
    "456842",
}

TAIWAN_PERFORMER_SOURCE_IDS = {"456834", "456835", "456836", "456841", "456842"}
TAIWAN_SOURCE_IDS = FRESHNESS_REQUIRED_SOURCE_IDS
TRANSLATION_CACHE = Path(
    os.environ.get("EPG_TRANSLATION_CACHE", ROOT / ".translation-cache" / "title_zh_ja.json")
)


def load_translation_cache() -> dict[str, str]:
    try:
        data = json.loads(TRANSLATION_CACHE.read_text(encoding="utf-8"))
        return {str(key): str(value) for key, value in data.items() if key and value}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


TITLE_TRANSLATIONS = load_translation_cache()


def translation_key(source_id: str, title: str) -> str:
    return f"{source_id}\t{title.strip()}"


def fetch_japanese_translation(title: str) -> str | None:
    """Translate one Traditional-Chinese title; failure must never drop EPG."""
    query = urllib.parse.urlencode(
        {
            "q": title,
            "langpair": "zh-TW|ja",
        }
    )
    request = urllib.request.Request(
        f"https://api.mymemory.translated.net/get?{query}",
        headers={"User-Agent": "japan-iptv-epg-builder/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if int(payload.get("responseStatus", 0)) != 200:
            return None
        translated = str(payload.get("responseData", {}).get("translatedText", "")).strip()
        return translated if translated and translated != title else None
    except (OSError, ValueError, TypeError, KeyError, IndexError, json.JSONDecodeError):
        return None


def populate_translation_cache(programmes: dict[str, list[ET.Element]]) -> int:
    """Translate only unseen Taiwan titles, concurrently, then persist the cache."""
    pending: dict[str, str] = {}
    for source_id in TAIWAN_SOURCE_IDS:
        for programme in programmes.get(source_id, []):
            title = programme.findtext("title", default="").strip()
            key = translation_key(source_id, title)
            if title and key not in TITLE_TRANSLATIONS:
                pending[key] = title

    if pending:
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(fetch_japanese_translation, title): key for key, title in pending.items()}
            for future in as_completed(futures):
                translated = future.result()
                if translated:
                    TITLE_TRANSLATIONS[futures[future]] = translated

        TRANSLATION_CACHE.parent.mkdir(parents=True, exist_ok=True)
        TRANSLATION_CACHE.write_text(
            json.dumps(TITLE_TRANSLATIONS, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return len(pending)


def clean_performer_name(value: str) -> str | None:
    """Return a conservative performer name, or None for labels/garbled text."""
    name = value.strip(" \t\r\n-－—:：;；,，、/。.")
    name = re.sub(r"\s+", " ", name)
    if not name or "?" in name or "�" in name:
        return None
    if name in {"素人", "素人太太"}:
        return None
    if any(marker in name for marker in ("潘朵啦", "歡迎來到", "成人娛樂", "AV女優")):
        return None
    if re.fullmatch(r"[A-Za-z]", name):
        return None
    if not (re.search(r"[\u3400-\u9fff々ぁ-んァ-ヶ]", name) or re.search(r"[A-Za-z]{2}", name)):
        return None
    return name if len(name) <= 80 else None


def split_performer_names(value: str) -> list[str]:
    names: list[str] = []
    for part in re.split(r"[,，、/]", value):
        name = clean_performer_name(part)
        if name and name not in names:
            names.append(name)
    return names


def first_match(desc: str, patterns: tuple[str, ...]) -> list[str]:
    for pattern in patterns:
        match = re.search(pattern, desc)
        if match:
            name = clean_performer_name(match.group("name"))
            if name:
                return [name]
    return []


def extract_performers(source_id: str, programme: ET.Element) -> tuple[list[str], str | None]:
    """Extract only performer names exposed by the Taiwan guide itself."""
    desc = programme.findtext("desc", default="").strip()
    title = programme.findtext("title", default="").strip()
    if not desc or source_id not in TAIWAN_PERFORMER_SOURCE_IDS:
        return [], None

    if source_id in {"456834", "456836"}:
        leading = re.split(r"[。.]", desc, maxsplit=1)[0].strip()
        actors = split_performer_names(leading)
        return actors, leading if actors else None

    if source_id == "456835":
        leading = desc.split("......", 1)[0].strip(" .")
        # A comma is the only reliable person boundary in this source. Keep
        # space-only cast strings visible without inventing actor boundaries.
        actors = split_performer_names(leading) if re.search(r"[,，]", leading) else []
        return actors, leading or None

    if source_id == "456841":
        actors = first_match(
            desc,
            (
                r"(?:獨家|新人)?女優(?P<name>[\u3400-\u9fff々]{2,8})",
                r"^(?P<name>[\u3400-\u9fff々]{2,8})在丈夫",
                r"^(?P<name>[\u3400-\u9fff々]{2,8})是(?:名|某名)",
                r"^(?P<name>[\u3400-\u9fff々]{2,8})決定與",
                r"一下(?P<name>[\u3400-\u9fff々]{2,8})的親密私語",
                r"更加狂野的(?P<name>[\u3400-\u9fff々]{2,8})[，,]在絕頂",
                r"暗戀對象(?P<name>[\u3400-\u9fff々]{2,8})坐在",
                r"人妻(?P<name>[\u3400-\u9fff々]{2,8})竟淪為",
                r"美容師(?P<name>[\u3400-\u9fff々]{2,8})是一位",
                r"風俗妹(?P<name>[\u3400-\u9fff々]{2,8})在",
            ),
        )
        return actors, "、".join(actors) if actors else None

    # Banana descriptions use a handful of recurring editorial templates.
    actors = first_match(
        desc,
        (
            r"情色偶像\s*[-－—]\s*(?P<name>[\u3400-\u9fff々]{2,8})(?=[。！!，,])",
            r"淫亂少女\s*[-－—]\s*(?P<name>[\u3400-\u9fff々]{2,8})(?=非常)",
            r"超人氣熟女偶像\s*[-－—]\s*(?P<name>[\u3400-\u9fff々]{2,8})(?=終於)",
            r"美爆乳\s*[-－—]\s*(?P<name>[\u3400-\u9fff々]{2,8})(?=自從)",
            r"素人辣妹\s*[-－—]\s*(?P<name>[\u3400-\u9fff々]{2,8})(?=與您)",
            r"美女模特兒\s*[-－—]\s*(?P<name>[\u3400-\u9fff々]{2,8})(?=終於)",
            r"模特兒美少女\s*[-－—]\s*(?P<name>[\u3400-\u9fff々]{2,8})(?=在無碼)",
            r"\](?P<name>[\u3400-\u9fff々]{2,10})所演出",
            r"新婚妻子(?P<name>[\u3400-\u9fff々]{2,8})與丈夫",
            r"擔任服務生的(?P<name>[\u3400-\u9fff々]{2,8})",
            r"女人[，,]她是(?P<name>[\u3400-\u9fff々]{2,8})",
        ),
    )
    if not actors:
        title_match = re.search(r"[-－—](?P<name>[\u3400-\u9fff々]{2,10})(?:\(|$)", title)
        if title_match:
            name = clean_performer_name(title_match.group("name"))
            actors = [name] if name else []
    return actors, "、".join(actors) if actors else None


def add_performer_metadata(programme: ET.Element, source_id: str) -> tuple[int, str | None]:
    actors, display_names = extract_performers(source_id, programme)
    if not display_names:
        return 0, None

    if programme.find("sub-title") is None:
        subtitle = ET.Element("sub-title", {"lang": "zh"})
        subtitle.text = f"出演：{display_names}"
        children = list(programme)
        title_positions = [index for index, child in enumerate(children) if child.tag == "title"]
        programme.insert((title_positions[-1] + 1) if title_positions else 0, subtitle)

    if actors:
        credits = programme.find("credits")
        if credits is None:
            credits = ET.Element("credits")
            children = list(programme)
            desc_positions = [index for index, child in enumerate(children) if child.tag == "desc"]
            programme.insert((desc_positions[-1] + 1) if desc_positions else len(children), credits)
        existing = {node.text for node in credits.findall("actor") if node.text}
        for actor_name in actors:
            if actor_name not in existing:
                ET.SubElement(credits, "actor").text = actor_name
                existing.add(actor_name)
    return len(actors), display_names


def localize_taiwan_title(programme: ET.Element, source_id: str, performers: str | None) -> bool:
    """Make one title that both Lume and Lumen render; retain the Chinese original."""
    if source_id not in TAIWAN_SOURCE_IDS:
        return False
    title_nodes = programme.findall("title")
    if not title_nodes:
        return False

    original = (title_nodes[0].text or "").strip()
    if not original:
        return False
    translated = TITLE_TRANSLATIONS.get(translation_key(source_id, original), original).strip() or original
    visible_title = translated
    if performers:
        visible_title = f"{visible_title}｜出演：{performers}"

    # Both clients reliably render the first/only title. Lume concatenates
    # multiple language variants, so keep exactly one title in this feed.
    title_nodes[0].text = visible_title
    title_nodes[0].set("lang", "ja")
    for extra in title_nodes[1:]:
        programme.remove(extra)

    if translated != original:
        desc = programme.find("desc")
        if desc is None:
            desc = ET.Element("desc", {"lang": "ja"})
            children = list(programme)
            title_index = children.index(title_nodes[0])
            programme.insert(title_index + 1, desc)
        existing = (desc.text or "").strip()
        desc.text = f"原題：{original}" + (f"\n{existing}" if existing else "")
    return translated != original


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


def xmltv_timestamp(value: str) -> datetime:
    """Parse the timestamp forms used by the configured XMLTV sources."""
    compact = value.strip()
    for pattern in ("%Y%m%d%H%M%S %z", "%Y%m%d%H%M %z"):
        try:
            return datetime.strptime(compact, pattern)
        except ValueError:
            pass
    raise ValueError(f"Unsupported XMLTV timestamp: {value!r}")


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

    now = datetime.now(timezone.utc)
    stale_source_ids: list[dict[str, str]] = []
    for source_id in sorted(FRESHNESS_REQUIRED_SOURCE_IDS):
        source_programmes = programmes.get(source_id, [])
        latest_stop = max(
            (xmltv_timestamp(item.get("stop", "")) for item in source_programmes if item.get("stop")),
            default=None,
        )
        if latest_stop is None or latest_stop <= now:
            stale_source_ids.append(
                {
                    "source_id": source_id,
                    "latest_stop": latest_stop.isoformat() if latest_stop else "missing",
                }
            )
    if stale_source_ids:
        raise RuntimeError(f"Refusing to publish stale Taiwan guide: {stale_source_ids}")

    translation_requests = populate_translation_cache(programmes)

    output = ET.Element(
        "tv",
        {
            "generator-info-name": "Japan IPTV EPG cloud builder",
            "generator-info-url": "https://github.com/iptv-org/epg",
        },
    )
    missing_source_ids: list[dict[str, str]] = []
    programme_total = 0
    performer_programmes = 0
    performer_credits = 0
    translated_programmes = 0
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
            added_actors, display_names = add_performer_metadata(programme, source_id)
            if localize_taiwan_title(programme, source_id, display_names):
                translated_programmes += 1
            if programme.find("sub-title") is not None and source_id in TAIWAN_PERFORMER_SOURCE_IDS:
                performer_programmes += 1
            performer_credits += added_actors
            output.append(programme)
            programme_total += 1

    channel_total = len(output.findall("channel"))
    if channel_total < 105 or programme_total < 5000:
        raise RuntimeError(
            f"Refusing to publish incomplete guide: channels={channel_total}, programmes={programme_total}"
        )

    # GitHub Actions uses Python 3.12.  Keep local verification compatible
    # with older Python runtimes where ElementTree.indent is unavailable.
    if hasattr(ET, "indent"):
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
        "performer_programmes": performer_programmes,
        "performer_credits": performer_credits,
        "translated_programmes": translated_programmes,
        "translation_requests": translation_requests,
        "missing_source_ids": missing_source_ids,
        "freshness_checked_source_ids": sorted(FRESHNESS_REQUIRED_SOURCE_IDS),
        "sources": source_stats,
    }
    (PUBLIC / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
