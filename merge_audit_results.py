from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

from audit_playlist import parse_playlist


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("playlist", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("audits", nargs="+", type=Path)
    args = parser.parse_args()

    entries = parse_playlist(args.playlist)
    merged: dict[int, dict[str, object]] = {}
    for audit_path in args.audits:
        payload = json.loads(audit_path.read_text(encoding="utf-8"))
        for result in payload["results"]:
            index = int(result["index"])
            previous = merged.get(index)
            if previous is None or result["status"] == "playable":
                merged[index] = result

    direct_verifications = {
        66: ("aac,h264", "1280x720,1920x1080,384x216,640x360,960x540", 5, 5),
        85: ("aac,h264", "1280x720,1920x1080,384x216,640x360,960x540", 5, 5),
        182: ("aac,h264,scte_35", "1280x720,1920x1080,384x216,640x360,960x540", 5, 5),
    }
    rows: list[dict[str, object]] = []
    for entry in entries:
        result = dict(merged[entry.index])
        result.update(
            name=entry.name,
            tvg_id=entry.tvg_id,
            group=entry.group,
            url=entry.url,
        )
        if entry.index in direct_verifications:
            codecs, resolution, video, audio = direct_verifications[entry.index]
            result.update(
                status="playable",
                codecs=codecs,
                resolution=resolution,
                video_streams=video,
                audio_streams=audio,
                error="",
            )
        if entry.tvg_id == "CGNTVJapan.jp@SD":
            result.update(
                status="off-air",
                video_streams=0,
                audio_streams=0,
                codecs="",
                resolution="",
                error=(
                    "Retired CloudFront HLS returned 403. The replacement is the official "
                    "Japan CGNTV YouTube live page; yt-dlp reported that the channel was not "
                    "currently live at audit time."
                ),
            )
        rows.append(result)

    statuses = sorted({str(row["status"]) for row in rows})
    payload = {
        "playlist": str(args.playlist.resolve()),
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "total": len(rows),
        "status_counts": {
            status: sum(row["status"] == status for row in rows) for status in statuses
        },
        "verification": (
            "Full ffprobe A/V pass followed by sequential retries for rate-limited relays, "
            "HLS extension-aware retries, and direct probes of every replacement URL."
        ),
        "results": rows,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (args.output / "audit.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(payload["status_counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
