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

CID_CHANNELS = [
    ("WOWOWCinema.jp", "WOWOWシネマ", "bs07", "02 BS", False),
    ("StarBS10.jp", "BS10プレミアム", "bs08", "02 BS", False),
    ("WOWOWPrime.jp", "WOWOWプライム", "bs12", "02 BS", False),
    ("GreenChannel.jp", "グリーンチャンネル", "bs14", "02 BS", False),
    ("Animax.in", "アニマックス", "bs15", "02 BS", False),
    ("JSPORTS1.jp", "J SPORTS 1", "bs18", "02 BS", False),
    ("JSPORTS2.jp", "J SPORTS 2", "bs19", "02 BS", False),
    ("WOWOWLive.jp", "WOWOWライブ", "bs20", "02 BS", False),
    ("JSPORTS3.jp", "J SPORTS 3", "bs21", "02 BS", False),
    ("JSPORTS4.jp", "J SPORTS 4", "bs22", "02 BS", False),
    ("NihonEigaSenmonChannel.jp", "日本映画専門チャンネル", "bs23", "02 BS", False),
    ("DisneyChannel.jp", "ディズニー・チャンネル", "bs24", "02 BS", False),
    ("FishingVision.jp", "釣りビジョン", "bs25", "02 BS", False),
    ("SpaceShowerTV.jp", "スペースシャワーTV", "bs26", "02 BS", False),
    ("BSShochikuTokyu.jp", "J:COM BS", "bs31", "02 BS", False),
    ("SkyA.jp", "スカイA", "cs01", "03 CS・専門", False),
    ("NitteleGPlus.jp", "日テレジータス", "cs02", "03 CS・専門", False),
    ("GolfNetwork.jp", "ゴルフネットワーク", "cs03", "03 CS・専門", False),
    ("JidaigekiSenmonChannel.jp", "時代劇専門チャンネル", "cs04", "03 CS・専門", False),
    ("HomeDramaChannel.jp", "ホームドラマチャンネル", "cs05", "03 CS・専門", False),
    ("MusicJapanTV.jp", "ミュージック・ジャパンTV", "cs06", "03 CS・専門", False),
    ("KidsStation.jp", "キッズステーション", "cs07", "03 CS・専門", False),
    ("DiscoveryChannelSoutheastAsia.sg@Japan", "ディスカバリーチャンネル", "cs08", "03 CS・専門", False),
    ("History.jp", "ヒストリーチャンネル", "cs09", "03 CS・専門", False),
    ("NationalGeographic.jp", "ナショナル ジオグラフィック", "cs10", "03 CS・専門", False),
    ("TBSNewsCS.jp", "TBS NEWS", "cs11", "03 CS・専門", False),
    ("TABIChannel.jp", "旅チャンネル", "cs12", "03 CS・専門", False),
    ("KayoPops.jp", "歌謡ポップスチャンネル", "cs13", "03 CS・専門", False),
    ("MoviePlus.jp", "ムービープラス", "cs14", "03 CS・専門", False),
    ("BBCNews.uk@AsiaPacific", "BBCニュース", "cs15", "03 CS・専門", False),
    ("CNNj.jp", "CNNj", "cs16", "03 CS・専門", False),
    ("GAORASPORTS.jp", "GAORA SPORTS", "cs17", "03 CS・専門", False),
    ("MTV.jp", "MTV", "cs18", "03 CS・専門", False),
    ("LaLaTV.jp", "女性チャンネル♪LaLa TV", "cs19", "03 CS・専門", False),
    ("FamilyGekijyo.jp", "ファミリー劇場", "cs20", "03 CS・専門", False),
    ("MONDOTV.jp", "MONDO TV", "cs21", "03 CS・専門", False),
    ("EiseiGekijo.jp", "衛星劇場", "cs22", "03 CS・専門", False),
    ("DisneyJunior.jp", "ディズニージュニア", "cs23", "03 CS・専門", False),
    ("AnimalPlanet.jp", "アニマルプラネット", "cs24", "03 CS・専門", False),
    ("CartoonNetwork.jp", "カートゥーン ネットワーク", "cs25", "03 CS・専門", False),
    ("FujiTVNEXT.jp", "フジテレビNEXT", "cs26", "03 CS・専門", False),
    ("ToeiChannel.jp", "東映チャンネル", "cs27", "03 CS・専門", False),
    ("TAKARAZUKASKYSTAGE.jp", "TAKARAZUKA SKY STAGE", "cs28", "03 CS・専門", False),
    ("ChannelGinga.jp", "チャンネル銀河", "cs29", "03 CS・専門", False),
    ("rch_86", "ワンニャンチャンネル", "rch_86", "07 趣味・ライフ", False),
    ("rch_100", "囲碁・将棋ライト (Rチャンネル)", "rch_100", "03 CS・専門", False),
    ("rch_98", "セクシーエンタメチャンネル", "rch_98", "99 成人・年齢制限", True),
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

    tv_safe = "safe" in path.name.casefold() or path.name == "kodi_playlist.m3u"
    existing_ids = {tvg_id(block[0]) for block in blocks}
    for playlist_id, name, cid, group, adult_only in CID_CHANNELS:
        if adult_only and tv_safe:
            continue
        if playlist_id in existing_ids:
            continue
        extinf = (
            f'#EXTINF:-1 tvg-id="{playlist_id}" tvg-name="{name}" '
            f'group-title="{group}",{name}'
        )
        blocks.append([extinf, f"https://ri.shinori.my.id/pxx.php?shk_cid={cid}"])
        existing_ids.add(playlist_id)

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
    notes = [
        (
            "#NOTE:2026-10-25 added verified official public NTV NEWS and MBS NEWS feeds; "
            "created 03 CS-specialist group and sorted all category prefixes numerically."
        ),
        (
            "#NOTE:2026-10-25 added 44 BS/CS subscription channels after sequential A/V decode; "
            "no free/paid filter was applied."
        ),
        (
            "#NOTE:2026-10-25 added distinct live R-channel feeds for pets, igo/shogi and adult entertainment; "
            "the adult feed remains full-playlist-only."
        ),
    ]
    for note in notes:
        if note not in header:
            header.append(note)

    output = header + [line for block in blocks for line in block]
    path.write_text("\n".join(output) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: organize_playlists.py PLAYLIST [PLAYLIST ...]")
    for name in sys.argv[1:]:
        organize(Path(name))
