#!/usr/bin/env python3
"""
Split FLAC or WAV audio tracks into files, using a CUE sheet.
WAV inputs are re-encoded to FLAC with compression level 8.
FLAC inputs are re-encoded by default to fix STREAMINFO; use --streamcopy
to keep original FLAC frames.
This script does not adjust for zero-crossings or apply fades.
"""

from __future__ import annotations

import argparse
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP, getcontext
from fractions import Fraction
from pathlib import Path
from typing import List, Optional

getcontext().prec = 18

__version__ = "0.0.1"
BANNER = f"splat v{__version__}"

class Style:
    """Simple styling helper that falls back to plain text if color is unavailable."""

    def __init__(self) -> None:
        self.use_color = False
        self._init_colorama()

        if self.use_color:
            self.info = "\033[1m\033[38;5;10m\033[48;5;28m INFO \033[0m"
            self.warn = "\033[1m\033[38;5;203m\033[48;5;124m WARN \033[0m"
        else:
            self.info = "INFO"
            self.warn = "WARN"

    def _init_colorama(self) -> None:
        # Prefer colorama when available; otherwise fall back to plain output.
        try:
            import colorama  # type: ignore
        except Exception:
            return

        if sys.stdout.isatty():
            colorama.just_fix_windows_console()
            self.use_color = True


STYLE = Style()


@dataclass
class Track:
    number: int
    title: Optional[str] = None
    performer: Optional[str] = None
    start: Optional[Fraction] = None


@dataclass
class FileEntry:
    path: Path
    tracks: List[Track] = field(default_factory=list)


@dataclass
class CueSheet:
    entries: List[FileEntry]
    album_title: Optional[str] = None
    album_performer: Optional[str] = None


TIME_RE = re.compile(r"^(\d+):(\d{2}):(\d{2})$")
FILE_RE = re.compile(r'^\s*FILE\s+(?:"([^"]+)"|(\S+))\s+\S+', re.IGNORECASE)
WINDOWS_RESERVED_RE = re.compile(r'[<>:"/\\\\|?*]')


def sanitize_filename(value: str) -> str:
    """Replace path separators and reserved characters with underscores."""
    cleaned = WINDOWS_RESERVED_RE.sub("_", value)
    cleaned = cleaned.replace("..", "__").strip()
    return cleaned or "untitled"


def parse_file_line(line: str, line_num: int) -> str:
    """Extract the FILE path without interpreting backslash escapes."""
    match = FILE_RE.match(line)
    if not match:
        raise ValueError(f"Line {line_num}: malformed FILE entry")
    return match.group(1) or match.group(2) or ""


def parse_timecode(value: str, line_num: int) -> Fraction:
    """Convert mm:ss:ff (75 fps) into fractional seconds."""
    # Validate and convert mm:ss:ff (75 frames/second) into fractional seconds.
    match = TIME_RE.match(value)
    if not match:
        raise ValueError(f"Line {line_num}: invalid timecode '{value}'")
    minutes = int(match.group(1))
    seconds = int(match.group(2))
    frames = int(match.group(3))
    if seconds >= 60:
        raise ValueError(f"Line {line_num}: seconds out of range in '{value}'")
    if frames >= 75:
        raise ValueError(f"Line {line_num}: frames out of range in '{value}'")
    return Fraction(minutes * 60 + seconds, 1) + Fraction(frames, 75)


def fraction_to_timestamp(value: Fraction) -> str:
    """Format fractional seconds for ffmpeg timestamps with microsecond precision."""
    # Format fractional seconds as a fixed-precision string for ffmpeg.
    seconds = Decimal(value.numerator) / Decimal(value.denominator)
    return str(seconds.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def read_cue_text(cue_path: Path) -> str:
    """Read CUE text, preferring UTF-8 with a cp1252 fallback."""
    # Try UTF-8 first, then fall back to Windows-1252 for common CUE exports.
    try:
        return cue_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return cue_path.read_text(encoding="cp1252")


def parse_cue(cue_path: Path) -> CueSheet:
    """Parse the CUE into ordered file/track entries with INDEX 01 boundaries."""
    # Parse the CUE, grouping tracks under their referenced FILE entries.
    file_entries: List[FileEntry] = []
    current_file: Optional[FileEntry] = None
    current_track: Optional[Track] = None
    album_title: Optional[str] = None
    album_performer: Optional[str] = None

    for line_num, raw_line in enumerate(read_cue_text(cue_path).splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("REM"):
            continue

        if line.upper().startswith("FILE "):
            # Each FILE starts a new input and resets the current track context.
            file_name = parse_file_line(raw_line, line_num)
            file_path = cue_path.parent / file_name
            if not file_path.exists():
                raise FileNotFoundError(f"Line {line_num}: missing file '{file_path}'")
            current_file = FileEntry(path=file_path)
            file_entries.append(current_file)
            current_track = None
            continue

        if line.upper().startswith("TRACK "):
            # Track definitions belong to the most recent FILE entry.
            if current_file is None:
                raise ValueError(f"Line {line_num}: TRACK before FILE")
            tokens = shlex.split(line, posix=True)
            if len(tokens) < 2:
                raise ValueError(f"Line {line_num}: malformed TRACK entry")
            try:
                track_number = int(tokens[1])
            except ValueError as exc:
                raise ValueError(f"Line {line_num}: invalid TRACK number") from exc
            current_track = Track(number=track_number)
            current_file.tracks.append(current_track)
            continue

        if line.upper().startswith("TITLE "):
            # Only track-level TITLE entries are needed for output naming.
            tokens = shlex.split(line, posix=True)
            if len(tokens) < 2:
                raise ValueError(f"Line {line_num}: malformed TITLE entry")
            if current_track is None:
                if album_title is None:
                    album_title = tokens[1]
            else:
                current_track.title = tokens[1]
            continue

        if line.upper().startswith("PERFORMER "):
            tokens = shlex.split(line, posix=True)
            if len(tokens) < 2:
                raise ValueError(f"Line {line_num}: malformed PERFORMER entry")
            if current_track is None:
                if album_performer is None:
                    album_performer = tokens[1]
            else:
                current_track.performer = tokens[1]
            continue

        if line.upper().startswith("INDEX "):
            # Only INDEX 01 defines track boundaries.
            if current_track is None:
                raise ValueError(f"Line {line_num}: INDEX before TRACK")
            tokens = shlex.split(line, posix=True)
            if len(tokens) < 3:
                raise ValueError(f"Line {line_num}: malformed INDEX entry")
            if tokens[1] != "01":
                continue
            if current_track.start is not None:
                raise ValueError(f"Line {line_num}: duplicate INDEX 01")
            current_track.start = parse_timecode(tokens[2], line_num)
            continue

    if not file_entries:
        # The CUE must define at least one FILE entry.
        raise ValueError("No FILE entries found in CUE sheet")

    for entry in file_entries:
        if not entry.tracks:
            raise ValueError(f"No TRACK entries found for file '{entry.path}'")
        for track in entry.tracks:
            if track.title is None:
                raise ValueError(f"Missing TITLE for track {track.number}")
            if track.start is None:
                raise ValueError(f"Missing INDEX 01 for track {track.number}")

    return CueSheet(
        entries=file_entries,
        album_title=album_title,
        album_performer=album_performer,
    )


def run_ffmpeg(
    input_path: Path,
    output_path: Path,
    start: Fraction,
    end: Optional[Fraction],
    metadata: dict[str, str],
    fix_streaminfo: bool,
) -> None:
    """Invoke ffmpeg to split a segment, optionally re-encoding FLAC for STREAMINFO."""
    # Use stream copy for FLAC inputs unless STREAMINFO fixes are enabled.
    if output_path.exists():
        raise FileExistsError(f"Output file already exists: '{output_path}'")

    suffix = input_path.suffix.lower()
    if suffix in (".wav", ".wave"):
        codec_args = ["-c:a", "flac", "-compression_level", "8"]
    elif suffix == ".flac":
        if fix_streaminfo:
            codec_args = ["-c:a", "flac", "-compression_level", "8"]
        else:
            codec_args = ["-c", "copy"]
    else:
        raise RuntimeError(f"Unsupported input format: '{input_path.suffix}'")

    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_path),
        "-ss",
        fraction_to_timestamp(start),
    ]

    if end is not None:
        cmd.extend(["-to", fraction_to_timestamp(end)])

    cmd.extend(codec_args)

    for key, value in metadata.items():
        cmd.extend(["-metadata", f"{key}={value}"])

    cmd.append(str(output_path))

    subprocess.run(cmd, check=True)


def split_files(
    cue_path: Path,
    tag_output: bool,
    fix_streaminfo: bool,
) -> tuple[int, set[str]]:
    """Split all FILE entries referenced by the CUE into track files."""
    # Iterate in CUE order and split each file at INDEX 01 boundaries.
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found in PATH")

    cue = parse_cue(cue_path)
    print(f"{STYLE.info} Parsed CUE successfully.")
    print(f"{STYLE.info} Found {len(cue.entries)} input file(s).")
    print(f"{STYLE.info} Ready to split audio tracks...")
    output_dir = cue_path.parent
    total_tracks = sum(len(entry.tracks) for entry in cue.entries)
    written = 0
    track_numbers = [track.number for entry in cue.entries for track in entry.tracks]
    monotonic = all(a < b for a, b in zip(track_numbers, track_numbers[1:]))

    tags_used: set[str] = set()

    for file_index, entry in enumerate(cue.entries, start=1):
        for index, track in enumerate(entry.tracks):
            next_track = entry.tracks[index + 1] if index + 1 < len(entry.tracks) else None
            end_time = next_track.start if next_track is not None else None
            if monotonic:
                track_label = f"{track.number:02d}"
            else:
                track_label = f"{file_index:02d}-{track.number:02d}"
            safe_title = sanitize_filename(track.title or "")
            output_name = f"{track_label} - {safe_title}.flac"
            output_path = output_dir / output_name
            print(f"{STYLE.info} Task {written + 1} of {total_tracks}: {output_name}")
            metadata: dict[str, str] = {}
            if tag_output:
                metadata["TRACKNUMBER"] = str(track.number)
                metadata["TITLE"] = track.title or ""
                if cue.album_title:
                    metadata["ALBUM"] = cue.album_title
                performer = track.performer or cue.album_performer
                if performer:
                    metadata["ARTIST"] = performer
                    metadata["ALBUMARTIST"] = performer
                tags_used.update(metadata.keys())
            run_ffmpeg(
                entry.path,
                output_path,
                track.start,
                end_time,
                metadata,
                fix_streaminfo=fix_streaminfo,
            )
            written += 1

    return written, tags_used

def main() -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description=(
            "Split FLAC files using a CUE sheet. "
            "By default, FLAC outputs are re-encoded to fix STREAMINFO; "
            "use --streamcopy to keep original FLAC frames (STREAMINFO may be wrong). "
            "WAV inputs are re-encoded to FLAC."
        ),
        epilog=(
            "Output files are written next to the CUE as:\n"
            "  NN - Track Title.flac\n"
            "Only INDEX 01 entries are used as boundaries."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("cue", type=Path, help="Path to the .cue file")
    parser.add_argument(
        "--notagging",
        action="store_true",
        help="Disable writing tags derived from the CUE sheet",
    )
    parser.add_argument(
        "--streamcopy",
        action="store_true",
        help="Keep original FLAC frames (STREAMINFO may be wrong)",
    )
    args = parser.parse_args()

    print()
    print(BANNER)
    print(f"Split audio tracks.")
    print()

    cue_path = args.cue
    if not cue_path.exists():
        raise FileNotFoundError(f"CUE file not found: '{cue_path}'")

    start_time = time.monotonic()

    try:
        written, tags_used = split_files(
            cue_path,
            tag_output=not args.notagging,
            fix_streaminfo=not args.streamcopy,
        )
    except subprocess.CalledProcessError as exc:
        print(
            f"{STYLE.warn} ffmpeg failed with exit code {exc.returncode}",
            file=sys.stderr,
        )
        return 1
    except ValueError as exc:
        print(f"{STYLE.warn} CUE parse failed: {exc}", file=sys.stderr)
        return 1
    except (FileNotFoundError, RuntimeError, FileExistsError) as exc:
        print(f"{STYLE.warn} {exc}", file=sys.stderr)
        return 1

    elapsed = int(round(time.monotonic() - start_time))
    print(f"{STYLE.info} Wrote {written} files.")
    print(f"{STYLE.info} Time elapsed: {elapsed} seconds")
    if tags_used:
        tags_list = ", ".join(sorted(tags_used))
        print(
            f"{STYLE.info} Tags {tags_list} (present in CUE) added to output FLAC files."
        )
    else:
        print(f"{STYLE.info} No tags added to the output files.")
    print(f"{STYLE.info} Suggestion: Next, verify tags on these files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
