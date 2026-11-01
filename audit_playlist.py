from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import parse_qsl, unquote


EXTINF_ATTR = re.compile(r'([\w-]+)="([^"]*)"')


@dataclass
class Entry:
    index: int
    name: str
    tvg_id: str
    group: str
    url: str
    user_agent: str
    referrer: str


@dataclass
class Result:
    index: int
    name: str
    tvg_id: str
    group: str
    url: str
    status: str
    video_streams: int
    audio_streams: int
    codecs: str
    resolution: str
    elapsed_seconds: float
    error: str


def parse_playlist(path: Path) -> list[Entry]:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    entries: list[Entry] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line.startswith("#EXTINF"):
            i += 1
            continue
        attrs = dict(EXTINF_ATTR.findall(line))
        name = line.rsplit(",", 1)[-1].strip()
        user_agent = ""
        referrer = ""
        url = ""
        i += 1
        while i < len(lines) and not lines[i].lstrip().startswith("#EXTINF"):
            value = lines[i].strip()
            if value.startswith("#EXTVLCOPT:http-user-agent="):
                user_agent = value.split("=", 1)[1].strip()
            elif value.startswith("#EXTVLCOPT:http-referrer="):
                referrer = value.split("=", 1)[1].strip()
            elif value and not value.startswith("#"):
                url = value
            i += 1
        if not url:
            raise ValueError(f"entry without URL: {name}")
        if "|" in url:
            url, suffix = url.split("|", 1)
            for key, value in parse_qsl(suffix, keep_blank_values=True):
                if key.casefold() == "user-agent":
                    user_agent = unquote(value)
        entries.append(
            Entry(
                index=len(entries) + 1,
                name=name,
                tvg_id=attrs.get("tvg-id", ""),
                group=attrs.get("group-title", ""),
                url=url,
                user_agent=user_agent,
                referrer=referrer,
            )
        )
    return entries


def one_probe(entry: Entry, ffprobe: Path, timeout: int) -> Result:
    command = [
        str(ffprobe),
        "-v",
        "error",
        "-rw_timeout",
        str(max(timeout - 2, 3) * 1_000_000),
        "-analyzeduration",
        "5000000",
        "-probesize",
        "5000000",
            "-allowed_extensions",
            "ALL",
            "-allowed_segment_extensions",
            "ALL",
            "-extension_picky",
            "0",
    ]
    if entry.user_agent:
        command.extend(["-user_agent", entry.user_agent])
    if entry.referrer:
        command.extend(["-headers", f"Referer: {entry.referrer}\r\n"])
    command.extend(
        [
            "-show_entries",
            "stream=codec_type,codec_name,width,height",
            "-of",
            "json",
            entry.url,
        ]
    )
    started = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        elapsed = round(time.monotonic() - started, 2)
    except subprocess.TimeoutExpired as exc:
        error = ((exc.stderr or b"") if isinstance(exc.stderr, bytes) else (exc.stderr or ""))
        return Result(
            entry.index,
            entry.name,
            entry.tvg_id,
            entry.group,
            entry.url,
            "timeout",
            0,
            0,
            "",
            "",
            round(time.monotonic() - started, 2),
            str(error).strip()[-600:],
        )

    streams: list[dict[str, object]] = []
    if proc.stdout.strip():
        try:
            streams = json.loads(proc.stdout).get("streams", [])
        except json.JSONDecodeError:
            streams = []
    video = [item for item in streams if item.get("codec_type") == "video"]
    audio = [item for item in streams if item.get("codec_type") == "audio"]
    if video:
        status = "playable"
    elif streams:
        status = "no-video"
    else:
        status = "dead"
    codecs = ",".join(
        sorted({str(item.get("codec_name", "")) for item in streams if item.get("codec_name")})
    )
    resolution = ",".join(
        sorted(
            {
                f"{item.get('width')}x{item.get('height')}"
                for item in video
                if item.get("width") and item.get("height")
            }
        )
    )
    error = proc.stderr.strip().replace("\r", " ").replace("\n", " | ")[-600:]
    return Result(
        entry.index,
        entry.name,
        entry.tvg_id,
        entry.group,
        entry.url,
        status,
        len(video),
        len(audio),
        codecs,
        resolution,
        elapsed,
        error,
    )


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("playlist", type=Path)
    parser.add_argument("--ffprobe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--timeout", type=int, default=18)
    parser.add_argument(
        "--indices",
        help="Comma-separated one-based playlist indices to probe (default: all)",
    )
    args = parser.parse_args()

    entries = parse_playlist(args.playlist)
    if args.indices:
        wanted = {int(value) for value in args.indices.split(",") if value.strip()}
        entries = [entry for entry in entries if entry.index in wanted]
    args.output.mkdir(parents=True, exist_ok=True)
    results: list[Result] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(one_probe, entry, args.ffprobe, args.timeout): entry
            for entry in entries
        }
        for done, future in enumerate(as_completed(futures), 1):
            result = future.result()
            results.append(result)
            print(
                f"[{done:03d}/{len(entries):03d}] {result.status:9s} "
                f"v={result.video_streams} a={result.audio_streams} {result.name}",
                flush=True,
            )

    results.sort(key=lambda item: item.index)
    payload = {
        "playlist": str(args.playlist.resolve()),
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "total": len(results),
        "status_counts": {
            status: sum(result.status == status for result in results)
            for status in sorted({result.status for result in results})
        },
        "results": [asdict(result) for result in results],
    }
    (args.output / "audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (args.output / "audit.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(results[0]).keys()))
        writer.writeheader()
        writer.writerows(asdict(result) for result in results)
    print(json.dumps(payload["status_counts"], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
