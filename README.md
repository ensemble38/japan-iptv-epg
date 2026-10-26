# japan-iptv-epg

Hourly XMLTV guide for the Japan IPTV playlist (EPG data only; no stream URLs).

Two outputs are published: `japan_iptv_epg.xml.gz` preserves the complete
playlist guide, while `japan_iptv_kodi_epg.xml.gz` is generated from
`kodi_channels.csv` and excludes every adult-group channel for living-room TV use.
The matching TV-safe playlist is published as `japan_iptv_kodi_tv_safe.m3u`;
the complete playlist remains available at its existing Google Drive location.

Playlist groups are stored in numeric display order. The TV-safe playlist uses
the contiguous `01` through `15` groups; the complete playlist additionally
keeps adult channels isolated at the end as `99 成人・年齢制限`. The
`02 BS` and `03 CS・専門` groups include every currently decoded feed found in
the maintained sources, regardless of whether the named service is normally free
or subscription-based. FAST variants remain labelled separately from their
similarly named satellite services. The complete playlist also retains its adult
group; only the living-room Kodi output omits that group.

The builder merges Japanese sources with the current Xumo US, LG Channels US,
and Taiwan Traditional Chinese guides. Playlist IDs are normalized through
`channels.csv`; this includes UFC FAST, F1 Channel, the live Taiwan adult
feeds, and ten verified public Taiwan channels.

Taiwan ports 117 and 1009 are intentionally separate. Concurrent live-frame
verification on 2026-10-26 identified port 117 as Banana HD and port 1009 as
Model Media (`麻豆傳媒映畫`). Only port 117 uses the Banana schedule. No verified
schedule source is currently available for Model Media, so it receives explicit
name-only fallback blocks instead of an incorrect Banana schedule.

The complete guide also maps current schedules for Brazzers TV Europe, Extasy
TV, EroXXX HD, Dorcel TV, Leo TV, Reality Kings TV, and Private TV. Other adult
stations receive name-only fallback blocks when their source guide is empty or
unverified. The matching streams and their verified backup routes exist only in
the complete playlist; neither the Kodi playlist nor Kodi EPG contains them.

Taiwan programme titles are translated to Japanese and formatted as
`【出演者】日本語タイトル` so clients that only render XMLTV `<title>`
(including Lume and Lumen) show both fields without silent clipping. Full and
original titles are retained in `<desc>`, and `<credits><actor>` remains
available to clients that support structured cast metadata. Translation
failures fall back to the source title without dropping the programme.

The mapping is synchronized with the current production playlist. Every
playlist `tvg-id` receives both a `<channel>` definition and at least one
`<programme>` entry. Channels for which no detailed schedule is currently
available receive two-hour name-only guide blocks, so they remain visible in
both clients instead of disappearing from the guide.
