from __future__ import annotations

import re
import sys
from pathlib import Path


GROUP_RENAMES = {
    "09 趣味・ライフ": "08 趣味・ライフ",
    "10 地域・文化": "09 地域・文化",
    "11 通販": "10 通販",
    "12 宗教": "11 宗教",
    "13 ABEMA": "12 ABEMA",
    "14 スポーツ配信": "13 スポーツ配信",
    "15 バラエティ配信": "14 バラエティ配信",
    "16 成人・年齢制限": "15 成人・年齢制限",
    "17 台湾・公開配信": "16 台湾・公開配信",
    "18 海外": "17 海外",
    "08 趣味・ライフ": "07 趣味・ライフ",
    "09 地域・文化": "08 地域・文化",
    "10 通販": "09 通販",
    "11 宗教": "10 宗教",
    "12 ABEMA": "11 ABEMA",
    "13 スポーツ配信": "12 スポーツ配信",
    "14 バラエティ配信": "13 バラエティ配信",
    "15 成人・年齢制限": "99 成人・年齢制限",
    "16 台湾・公開配信": "14 台湾・公開配信",
    "17 海外": "15 海外",
}

SPECIALIST_IDS = {
    "fastch_v2_samri",
    "fastch_v2_kids",
    "fastch_v2_goshogi",
    "ShopChannel.jp",
    "GSTV.jp@SD",
    "QVC.jp@SD",
}

NEW_CHANNELS = [
    (
        '#EXTINF:-1 tvg-id="rch_47" tvg-name="日テレNEWS" tvg-chno="CH 104" '
        'tvg-logo="https://channel.rakuten.co.jp/service/img/logo/chlogo-with-number/104_ntvnews.png" '
        'group-title="04 ニュース・天気",日テレNEWS（公開配信）',
        "https://cdn-apne1.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-news1hlscmaf-rakutenjp/playlist.m3u8",
    ),
    (
        '#EXTINF:-1 tvg-id="rch_115" tvg-name="MBSニュース" tvg-chno="CH 106" '
        'tvg-logo="https://channel.rakuten.co.jp/service/img/logo/chlogo-with-number/106_mbs.png" '
        'group-title="04 ニュース・天気",MBSニュース（公開配信）',
        "https://cdn-uw2-prod.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-news5-cmaf-rakutenjp/playlist.m3u8",
    ),
]


def tvg_id(extinf: str) -> str:
    match = re.search(r'tvg-id="([^"]+)"', extinf)
    return match.group(1) if match else ""


def group_name(extinf: str) -> str:
    match = re.search(r'group-title="([^"]+)"', extinf)
    return match.group(1) if match else "99 その他"


def organize(path: Path) -> None:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    header: list[str] = []
    blocks: list[list[str]] = []
    index = 0
    while index < len(lines) and not lines[index].startswith("#EXTINF"):
        header.append(lines[index])
        index += 1
    while index < len(lines):
        if not lines[index].startswith("#EXTINF"):
            raise ValueError(f"Unexpected playlist line {index + 1} in {path}: {lines[index]!r}")
        block = [lines[index]]
        index += 1
        while index < len(lines) and not lines[index].startswith("#EXTINF"):
            block.append(lines[index])
            index += 1
        if not any(line and not line.startswith("#") for line in block[1:]):
            raise ValueError(f"Missing URL for {block[0]!r} in {path}")
        blocks.append(block)

    existing_ids = {tvg_id(block[0]) for block in blocks}
    for extinf, url in NEW_CHANNELS:
        if tvg_id(extinf) not in existing_ids:
            blocks.append([extinf, url])

    for block in blocks:
        extinf = block[0]
        if tvg_id(extinf) in SPECIALIST_IDS:
            extinf = re.sub(r'group-title="[^"]+"', 'group-title="03 CS・専門"', extinf)
        else:
            for old, new in GROUP_RENAMES.items():
                extinf = extinf.replace(f'group-title="{old}"', f'group-title="{new}"')
        block[0] = extinf

    blocks.sort(key=lambda block: (int(group_name(block[0]).split()[0]),))

    channel_count = len(blocks)
    adult_count = sum(group_name(block[0]) == "99 成人・年齢制限" for block in blocks)
    header = [
        re.sub(r"channels=\d+ adult-group=\d+", f"channels={channel_count} adult-group={adult_count}", line)
        for line in header
    ]
    note = (
        "#NOTE:2026-10-25 added verified official public NTV NEWS and MBS NEWS feeds; "
        "created 03 CS-specialist group and sorted all category prefixes numerically."
    )
    if note not in header:
        header.append(note)

    output = header + [line for block in blocks for line in block]
    path.write_text("\n".join(output) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: organize_playlists.py PLAYLIST [PLAYLIST ...]")
    for name in sys.argv[1:]:
        organize(Path(name))
