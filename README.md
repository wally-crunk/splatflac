![splatflac icon](splatflac-icon-180.png)

# splatflac

**Split audio tracks to FLAC — ideal for vinyl "image + CUE"**

Many vinyl rips are stored as Side A / Side B FLACs with a CUE.
You can easily split them with XLD (Mac), but CueTools (Windows) can fail when audio doesn't match Red Book CD format.

Here is a small utility to do one thing correctly.

**splatflac.py** splits FLAC files using a CUE sheet without re-encoding your FLACs (but it will re-encode WAV to FLAC Level 8).

## Design goals

- Work with vinyl-generated CUE sheets
- No requirement that audio conforms to Red Book CD-DA
- No change to audio bits (ffmpeg stream copy)
- Small, focused, and intentionally limited.

## What it does

- Parses standard CUE sheets
- Splits FLACs into per-track files next to the CUE
- Handles track numbers that reset per side: (files get prefixed, like `01-01 - Track One.flac`.)
- Writes basic tags by default (`TRACKNUMBER`, `TITLE`, album-level fields when present)
- Converts WAV to FLAC (level 8) only when given a WAV file

## What it does not do

- No guessing or inference
- No audio processing when FLACs are the input

## Tagging behavior

- By default, splat transcribes explicit metadata from the CUE into FLAC tags
- Use `--notagging` to disable all tag writing and preserve the original files exactly

## Why this exists

Vinyl rips are continuous PCM captures, not CD images.
Tools that reject them as "not Red Book compliant" are technically correct, but annoying.

## Requirements

- Python 3.x
- ffmpeg in PATH

## Known issues

- Leaves STREAMINFO untouched on split FLACs (md5, total samples, length are incorrect)

**That's it.**
