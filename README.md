# japan-iptv-epg

Hourly XMLTV guide for the Japan IPTV playlist (EPG data only; no stream URLs).

The builder merges Japanese sources with the current Xumo US, LG Channels US,
and Taiwan Traditional Chinese guides. Playlist IDs are normalized through
`channels.csv`; this includes UFC FAST, F1 Channel, and the live Taiwan
`驚豔成人電影台` feed.

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
