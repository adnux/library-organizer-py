#!/usr/bin/env python3
"""
organize.py — Reorganize ~/Music/Electronic into a configurable folder structure.

Usage:
    python3 organize.py                                        # dry-run, default structure
    python3 organize.py --execute                              # move files for real
    python3 organize.py --structure "Genre|Year|Artist|Month" # custom folder order
    python3 organize.py --fixYears                            # preview DATE tag fixes
    python3 organize.py --fixYears --execute                  # apply DATE tag fixes
    python3 organize.py --flatten                             # preview flattening to root
    python3 organize.py --flatten --execute                   # move all files to root
    python3 organize.py --only-root                            # only files in root (no subfolders)

Valid --structure tokens (case-insensitive, pipe-separated): Year, Month, Genre, Artist
Default structure: Year|Genre|Artist|Month
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path


DEFAULT_STRUCTURE = "Year|Genre|Artist|Month"
VALID_TOKENS      = {"year", "month", "genre", "artist"}


def _load_env_root() -> Path:
    for env_path in (Path(__file__).parent / ".env", Path.cwd() / ".env"):
        if env_path.is_file():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                if key.strip() == "MUSIC_ROOT":
                    val = val.strip().strip('"').strip("'")
                    return Path(val).expanduser().resolve()
    return Path.cwd()


DEFAULT_ROOT = _load_env_root()

MUSIC_EXTS = {".flac", ".mp3", ".aiff", ".aif", ".wav", ".m4a"}

MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Ordered most-specific first — first match wins
GENRE_PATTERNS = [
    (r"melodic.h.?&.?t|melodic.house.and.techno|melodic.house.&.techno"
     r"|melodic.*house.*techno|techno.*melodic",   "Melodic House & Techno"),
    (r"indie.dance",                                "Indie Dance"),
    (r"techno.peak.time|peak.time.*driv|driving.*techno|techno.*driving", "Techno"),
    (r"\btechno\b",                                 "Techno"),
    (r"drum.&.bass|dnb",                            "Drum & Bass"),
    (r"\btrance\b",                                 "Trance"),
    (r"\bhouse\b",                                  "House"),
    (r"\belectronic\b",                             "Electronic"),
    (r"\bedm\b",                                    "Electronic"),
    (r"electronica",                                "Electronic"),
    (r"\bdance\b",                                  "Dance"),
    (r"electro",                                    "Electro"),
    (r"\bpop\b",                                    "Pop"),
]


def get_tags(filepath: Path) -> dict:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", str(filepath)],
            capture_output=True, text=True, timeout=5,
        )
        data = json.loads(result.stdout)
        return {k.lower(): v for k, v in data.get("format", {}).get("tags", {}).items()}
    except Exception:
        return {}


def normalize_genre(raw: str | None) -> str | None:
    if not raw:
        return None
    segments = re.split(r"[;:,]", raw)
    for pat, norm in GENRE_PATTERNS:
        for seg in segments:
            if re.search(pat, seg.strip(), re.I):
                return norm
    return raw.strip()


def normalize_artist(raw: str | None) -> str:
    if not raw:
        return "Various Artists"
    s = raw.strip()
    if re.match(r"^va$", s, re.I):
        return "Various Artists"
    if re.match(r"^various", s, re.I):
        return "Various Artists"
    # Multiple artists separated by commas → treat as compilation
    if s.count(",") >= 1:
        return "Various Artists"
    return s


def week_to_month(year: int, week: int) -> int | None:
    try:
        return date.fromisocalendar(year, week, 1).month
    except Exception:
        return None


def parse_date_tag(tags: dict) -> tuple[int | None, int | None]:
    for key in ("tdor", "trda", "date", "year"):
        val = tags.get(key, "")
        m = re.search(r"(\d{4})(?:-(\d{2}))?", val)
        if m:
            year = int(m.group(1))
            month = int(m.group(2)) if m.group(2) else None
            return year, month
    return None, None


def parse_folder_name(name: str) -> tuple:
    year, month, genre, artist = None, None, None, None

    wk = re.search(r"\bw(?:ee)?k\s*0*(\d{1,2})\b", name, re.I)
    if wk:
        yr_m = re.search(r"\b(20\d{2})\b", name)
        if yr_m:
            year = int(yr_m.group(1))
            month = week_to_month(year, int(wk.group(1)))

    if not month:
        dm = re.search(r"(20\d{2})[-.](\d{2})", name)
        if dm:
            year = int(dm.group(1))
            month = int(dm.group(2))

    if not month:
        for mn, mv in sorted(MONTH_NAMES.items(), key=lambda x: -len(x[0])):
            if re.search(r"\b" + mn + r"\b", name, re.I):
                month = mv
                ym = re.search(r"\b(20\d{2})\b", name)
                if ym and not year:
                    year = int(ym.group(1))
                break

    if not year:
        for pat in [r"[\[\(](20\d{2}|19\d{2})[\]\)]", r"\b(20\d{2}|19\d{2})\b"]:
            ym = re.search(pat, name)
            if ym:
                year = int(ym.group(1))
                break

    for pat, norm in GENRE_PATTERNS:
        if re.search(pat, name, re.I):
            genre = norm
            break

    a = re.match(r"^\[\d{4}\]\s*(.+?)\s*-\s*.+", name)
    if a:
        artist = a.group(1).strip()
    if not artist:
        a = re.match(r"^(.+?)\s*-\s*20\d{2}\s*-\s*.+", name)
        if a and not re.search(r"^(VA|Various)", a.group(1), re.I):
            artist = a.group(1).strip()
    if not artist:
        a = re.match(r"^20\d{2}\s*-\s*(.+?)\s*-\s*.+", name)
        if a and not re.search(
            r"^(beatport|va|various|serious|global|state|defected"
            r"|drumcode|armada|nervous|above|group)",
            a.group(1), re.I,
        ):
            artist = a.group(1).strip()

    return year, month, genre, artist



def parse_structure(structure_str: str) -> list[str]:
    tokens = [t.strip().lower() for t in structure_str.split("|") if t.strip()]
    invalid = [t for t in tokens if t not in VALID_TOKENS]
    if invalid:
        raise ValueError(
            f"Unknown structure token(s): {invalid}. "
            f"Valid tokens: {sorted(VALID_TOKENS)}"
        )
    return tokens


def build_target_path(root: Path, meta: dict, structure: list[str], filename: str) -> Path:
    parts = [meta[token] for token in structure]
    return root.joinpath(*parts, filename)


def resolve_metadata(filepath: Path) -> tuple[str, str, str, str]:
    tags = get_tags(filepath)
    year, month = parse_date_tag(tags)
    artist = normalize_artist(tags.get("album_artist") or tags.get("artist"))
    genre = normalize_genre(tags.get("genre"))

    for folder in reversed(filepath.parts[:-1]):
        if year and month and genre and artist != "Various Artists":
            break
        fy, fm, fg, fa = parse_folder_name(folder)
        if not year and fy:
            year = fy
        if not month and fm:
            month = fm
        if not genre and fg:
            genre = fg
        if artist == "Various Artists" and fa:
            artist = normalize_artist(fa)

    return (
        str(year) if year else "Unknown",
        f"{month:02d}" if isinstance(month, int) else "00",
        genre or "Unknown",
        artist or "Various Artists",
    )


def run(root: Path, execute: bool, structure: list[str], only_root: bool = False) -> None:
    label = "EXECUTE" if execute else "DRY-RUN"
    print(f"{'='*80}")
    print(f"  Music Organizer — {label}")
    print(f"  Root:      {root}")
    print(f"  Structure: {' / '.join(t.capitalize() for t in structure)}")
    if only_root:
        print(f"  Scope:     root folder only (subfolders skipped)")
    print(f"{'='*80}\n")

    moves: list[tuple[Path, Path]] = []
    errors: list[tuple[str, str]] = []

    if only_root:
        file_iter = (
            (root, [], sorted(f for f in os.listdir(root) if (root / f).is_file())),
        )
    else:
        file_iter = os.walk(root)

    for dirpath, _, files in file_iter:
        for fname in sorted(files):
            fpath = Path(dirpath) / fname
            if fpath.suffix.lower() not in MUSIC_EXTS:
                continue
            try:
                year, month, genre, artist = resolve_metadata(fpath)
                meta = {"year": year, "month": month, "genre": genre, "artist": artist}
                target = build_target_path(root, meta, structure, fname)
                if fpath != target:
                    moves.append((fpath, target))
            except Exception as e:
                errors.append((str(fpath.relative_to(root)), str(e)))

    for src, tgt in moves:
        print(f"  {'MOVE' if execute else 'WOULD MOVE'}: "
              f"{src.relative_to(root)}\n"
              f"           → {tgt.relative_to(root)}")

    print(f"\n{'─'*80}")
    print(f"  Total files to move: {len(moves)}")

    for i, token in enumerate(structure):
        counts: Counter = Counter()
        for _, tgt in moves:
            parts = tgt.relative_to(root).parts
            if i < len(parts):
                counts[parts[i]] += 1
        top = ", ".join(f"{k}({v})" for k, v in counts.most_common(8))
        print(f"  By {token.capitalize():<8}: {top}")

    if errors:
        print(f"\n  Errors ({len(errors)}):")
        for f, e in errors:
            print(f"    {f}: {e}")

    if not execute:
        print("\n  Run with --execute to apply changes.")
        return

    print("\n  Moving files...")
    moved = skipped = 0
    for src, tgt in moves:
        if tgt.exists():
            print(f"  SKIP (exists): {tgt.name}")
            skipped += 1
            continue
        tgt.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(tgt))
        moved += 1

    print(f"\n  Done. Moved: {moved}  |  Skipped: {skipped}")

    print("  Cleaning up empty source folders...")
    removed = 0
    for dirpath, _, _ in os.walk(root, topdown=False):
        rel = Path(dirpath).relative_to(root)
        if not rel.parts:
            continue
        try:
            os.rmdir(dirpath)
            removed += 1
        except OSError:
            pass
    print(f"  Removed {removed} empty directories.")


_RE_FOUR_DIGIT_YEAR = re.compile(r"^(19|20)\d{2}$")
_RE_YEAR_PREFIX     = re.compile(r"^(19|20)\d{2}")
_RE_FOLDER_YEAR     = re.compile(r"^(19|20)\d{2}$")


def _recover_year(fpath: Path, root: Path, tags: dict) -> str:
    for key in ("tdor", "trda"):
        val = tags.get(key, "")
        if val and _RE_YEAR_PREFIX.match(val):
            return val[:4]

    # Fall back to the year-named top-level folder under root
    try:
        rel = fpath.relative_to(root)
        top = rel.parts[0]
        if _RE_FOLDER_YEAR.match(top):
            return top
    except ValueError:
        pass

    return ""


def _rewrite_date_tag(fpath: Path, year: str) -> None:
    suffix = fpath.suffix
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix, dir=fpath.parent)
    os.close(tmp_fd)
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-i", str(fpath),
                "-map_metadata", "0",
                "-metadata", f"date={year}",
                "-codec", "copy",
                "-y", tmp_path,
            ],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip().splitlines()[-1])
        os.replace(tmp_path, fpath)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def fix_years(root: Path, execute: bool) -> None:
    label = "EXECUTE" if execute else "DRY-RUN"
    print(f"{'='*80}")
    print(f"  Fix Years — {label}")
    print(f"  Root: {root}")
    print(f"{'='*80}\n")

    issues: list[dict] = []
    for fpath in sorted(root.rglob("*")):
        if not fpath.is_file() or fpath.suffix.lower() not in MUSIC_EXTS:
            continue
        tags = get_tags(fpath)
        date_val = tags.get("date", "")

        if _RE_FOUR_DIGIT_YEAR.match(date_val):
            continue  # already correct

        if _RE_YEAR_PREFIX.match(date_val):
            # e.g. "2025-10-10" or "2025-01" → truncate
            issues.append({
                "path": fpath,
                "current": date_val,
                "year": date_val[:4],
                "reason": "truncate full date to year",
            })
        else:
            # Garbage (URL etc.) or missing — recover
            year = _recover_year(fpath, root, tags)
            if not year:
                continue
            reason = (
                "replace garbage/missing with tdor/trda year"
                if tags.get("tdor") or tags.get("trda")
                else "replace garbage/missing with folder year"
            )
            issues.append({
                "path": fpath,
                "current": date_val,
                "year": year,
                "reason": reason,
            })

    if not issues:
        print("  All DATE tags are already in YYYY format. Nothing to do.")
        return

    by_reason: dict[str, list] = defaultdict(list)
    for iss in issues:
        by_reason[iss["reason"]].append(iss)

    for reason, items in by_reason.items():
        print(f"  ── {reason} ({len(items)} files) ──")
        for iss in items:
            rel = iss["path"].relative_to(root)
            current = iss["current"] or "(missing)"
            print(f"    {str(rel):<72}  {current}  →  {iss['year']}")
        print()

    print(f"{'─'*80}")
    print(f"  Total files to fix: {len(issues)}")

    if not execute:
        print("\n  Run with --fixYears --execute to apply changes.")
        return

    print("\n  Rewriting tags...")
    fixed = errors = 0
    for iss in issues:
        try:
            _rewrite_date_tag(iss["path"], iss["year"])
            rel = iss["path"].relative_to(root)
            print(f"  FIXED: {rel}  →  date={iss['year']}")
            fixed += 1
        except Exception as e:
            print(f"  ERROR: {iss['path'].name}: {e}", flush=True)
            errors += 1

    print(f"\n  Done. Fixed: {fixed}  |  Errors: {errors}")


def flatten(root: Path, execute: bool) -> None:
    label = "EXECUTE" if execute else "DRY-RUN"
    print(f"{'='*80}")
    print(f"  Music Organizer — FLATTEN ({label})")
    print(f"  Root: {root}")
    print(f"{'='*80}\n")

    moves: list[tuple[Path, Path]] = []
    conflicts: list[tuple[Path, Path]] = []

    for dirpath, _, files in os.walk(root):
        if Path(dirpath) == root:
            continue  # files already at root level — skip
        for fname in sorted(files):
            fpath = Path(dirpath) / fname
            if fpath.suffix.lower() not in MUSIC_EXTS:
                continue
            target = root / fname
            if fpath == target:
                continue
            if target.exists():
                conflicts.append((fpath, target))
            else:
                moves.append((fpath, target))

    for src, tgt in moves:
        print(f"  {'MOVE' if execute else 'WOULD MOVE'}: {src.relative_to(root)}\n"
              f"           → {tgt.name}")

    if conflicts:
        print(f"\n  CONFLICTS (target already exists — will be skipped):")
        for src, tgt in conflicts:
            print(f"    {src.relative_to(root)}  →  {tgt.name}")

    print(f"\n{'─'*80}")
    print(f"  Files to move:  {len(moves)}")
    print(f"  Conflicts skip: {len(conflicts)}")

    if not execute:
        print("\n  Run with --flatten --execute to apply changes.")
        return

    print("\n  Moving files...")
    moved = skipped = 0
    for src, tgt in moves:
        if tgt.exists():
            print(f"  SKIP (exists): {tgt.name}")
            skipped += 1
            continue
        shutil.move(str(src), str(tgt))
        moved += 1

    print(f"\n  Done. Moved: {moved}  |  Skipped: {skipped + len(conflicts)}")

    print("  Cleaning up empty directories...")
    removed = 0
    for dirpath, _, _ in os.walk(root, topdown=False):
        if Path(dirpath) == root:
            continue
        try:
            os.rmdir(dirpath)
            removed += 1
        except OSError:
            pass
    print(f"  Removed {removed} empty directories.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="organize.py",
        description="Reorganize a music folder into a configurable hierarchy using embedded audio tags.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
COMMANDS
  organize (default)
    Moves files into <root>/<structure>/ based on metadata tags.

  --only-root
    Only reorganize files directly in <root> — subfolders are not touched.
    Without this flag all files in all subfolders are processed (default).

  --fixYears
    Scans all files and rewrites malformed DATE tags (URLs, YYYY-MM-DD, etc.)
    to a clean 4-digit year (YYYY). Uses ffmpeg — no audio is re-encoded.

  --flatten
    Moves all music files directly into <root>, removing all subfolders.
    Useful for starting a fresh reorganization.

STRUCTURE TOKENS  (case-insensitive, pipe-separated)
  Year    Release year (4-digit)
  Month   Release month (zero-padded 01–12; unknown → 00)
  Genre   Normalized genre name       (unknown → Unknown)
  Artist  Track artist                (compilations → Various Artists)

ROOT FOLDER RESOLUTION  (highest priority first)
  1. --root flag
  2. MUSIC_ROOT in a .env file (script directory, then current directory)
  3. Current working directory

  Example .env:
    MUSIC_ROOT=~/Music/Electronic

EXAMPLES
  python3 organize.py
      Dry-run with default structure: Year|Genre|Artist|Month

  python3 organize.py --execute
      Move files for real.

  python3 organize.py --only-root
      Dry-run, but only files directly in <root> (skip subfolders).

  python3 organize.py --only-root --execute
      Move only root-level files for real.

  python3 organize.py --structure "Genre|Year|Artist" --execute
      Reorganize as  <root>/Melodic House & Techno/2025/Massano/track.flac

  python3 organize.py --structure "Artist|Year"
      Dry-run as  <root>/Massano/2025/track.flac

  python3 organize.py --fixYears
      Preview DATE tag fixes (e.g. "https://djsoundtop.com" → "2024").

  python3 organize.py --fixYears --execute
      Apply DATE tag fixes.

  python3 organize.py --flatten
      Preview flattening all files into root.

  python3 organize.py --flatten --execute
      Move all files to root and delete empty subfolders.

  python3 organize.py --root /Volumes/MyDrive/Electronic --execute
      Operate on a different root folder.

CONVENTIONS
  Unknown month  → 00/
  Unknown year   → Unknown/
  Unknown genre  → Unknown/
  VA             → Various Artists/

Non-music files (.nfo, .sfv, .m3u, .jpg, .crdownload, etc.) are ignored.
""",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help=f"Root folder to operate on (default: {DEFAULT_ROOT})",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply changes. Without this flag the script is a dry-run.",
    )
    parser.add_argument(
        "--structure",
        default=DEFAULT_STRUCTURE,
        metavar="TOKENS",
        help=f"Pipe-separated folder structure (default: {DEFAULT_STRUCTURE})",
    )
    parser.add_argument(
        "--only-root",
        action="store_true",
        dest="only_root",
        help="Only reorganize files directly in root — subfolders are not touched.",
    )
    parser.add_argument(
        "--fixYears",
        action="store_true",
        help="Fix DATE tags to 4-digit year format instead of reorganizing files.",
    )
    parser.add_argument(
        "--flatten",
        action="store_true",
        help="Move all music files directly into root, removing all subfolders.",
    )
    args = parser.parse_args()

    if args.fixYears:
        fix_years(root=args.root, execute=args.execute)
    elif args.flatten:
        flatten(root=args.root, execute=args.execute)
    else:
        try:
            structure = parse_structure(args.structure)
        except ValueError as e:
            parser.error(str(e))
        run(root=args.root, execute=args.execute, structure=structure, only_root=args.only_root)
