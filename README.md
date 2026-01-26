![splatflac icon](splatflac-icon-180.png)

# splatflac
**Split audio tracks to FLAC — ideal for vinyl "image + CUE"**

Many vinyl rips are stored as Side A / Side B FLACs with a CUE.
You can easily split them with XLD (Mac), but CueTools (Windows) can fail when audio doesn't match Red Book CD format.

Here is a small utility to do one thing correctly.

**splatflac.py** splits FLAC files using a CUE sheet. By default it re-encodes FLAC outputs to fix STREAMINFO; use `--streamcopy` to keep original FLAC frames. WAV inputs are re-encoded to FLAC level 8.

## Design goals

- Work with vinyl-generated CUE sheets
- No requirement that audio conforms to Red Book CD-DA
- No DSP changes (fades, normalization, or zero-crossing edits)
- Optional stream-copy mode preserves original FLAC frames
- Small, focused, and intentionally limited

## What it does

- Parses standard CUE sheets
- Splits each referenced file into per-track FLACs next to the CUE
- Handles per-side track number resets (prefixes like `01-01 - Track One.flac`)
- Writes basic tags by default (`TRACKNUMBER`, `TITLE`, album-level fields when present)
- Re-encodes WAV to FLAC (level 8) when given a WAV file
- Re-encodes FLAC outputs by default to fix STREAMINFO (MD5/length/samples)

## What it does not do

- No guessing or inference
- No DSP or audio editing

## Tagging behavior

- By default, splat transcribes explicit metadata from the CUE into FLAC tags
- Use `--notagging` to disable all tag writing and preserve audio data exactly
- Use `--streamcopy` to keep original FLAC frames (STREAMINFO may be wrong)

## Why this exists

Vinyl rips are continuous PCM captures, not CD images.
Tools that reject them as "not Red Book compliant" are technically correct, but unhelpful for vinyl rips.

## Requirements

- Python 3.x
- ffmpeg in PATH

## Version History

- v0.0.2 – fixes CUE parsing for quotes/apostrophes on Windows; adds CI tests.
- v0.0.1 – re-encodes FLACs to ensure STREAMINFO/MD5 is correct.
- v0.0.0 – initial release.

**That's it.**

