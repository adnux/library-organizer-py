# music-organizer (Python)

Reorganizes a music folder into a configurable hierarchical structure based on embedded audio tags.

## Requirements

- Python 3.9+
- `ffprobe` + `ffmpeg` — used to read/write embedded audio tags

### Install Python

**macOS**
```bash
brew install python@3.12
```

**Linux (Debian / Ubuntu)**
```bash
sudo apt update && sudo apt install -y python3 python3-pip
```

**Windows**
```powershell
winget install Python.Python.3
# or download from: https://www.python.org/downloads/
```

### Install ffmpeg (includes ffprobe)

**macOS**
```bash
brew install ffmpeg
```

**Linux (Debian / Ubuntu)**
```bash
sudo apt update && sudo apt install -y ffmpeg
```

**Windows**
```powershell
winget install ffmpeg
# or: choco install ffmpeg
```

## Configuration

The root folder is resolved in this priority order:

1. `--root` flag (explicit override)
2. `MUSIC_ROOT` in a `.env` file (script directory, then current directory)
3. Current working directory

Copy `.env.example` to `.env` and set your music root:

**macOS / Linux**
```bash
cp .env.example .env
# Edit .env:
# MUSIC_ROOT=~/Music/Electronic
```

**Windows**
```powershell
copy .env.example .env
# Edit .env:
# MUSIC_ROOT=C:\Users\YourName\Music\Electronic
```

## Usage

**macOS / Linux**
```bash
# Dry-run — prints what would happen, no files touched (default)
python3 organize.py

# Execute — actually move the files
python3 organize.py --execute

# Custom root folder
python3 organize.py --root /Volumes/MyDrive/Electronic --execute

# Custom folder structure (pipe-separated tokens)
python3 organize.py --structure "Genre|Year|Artist"
python3 organize.py --structure "Artist|Year" --execute

# Only reorganize files directly in root (skip subfolders)
python3 organize.py --only-root
python3 organize.py --only-root --execute

# Fix malformed DATE tags (normalize to 4-digit year)
python3 organize.py --fixYears            # preview
python3 organize.py --fixYears --execute  # apply

# Flatten — move all files directly into root, removing subfolders
python3 organize.py --flatten             # preview
python3 organize.py --flatten --execute   # apply
```

**Windows**
```powershell
# Dry-run
python organize.py

# Execute
python organize.py --execute

# Custom root folder
python organize.py --root "D:\Music\Electronic" --execute

# Only reorganize files in root (skip subfolders)
python organize.py --only-root
python organize.py --only-root --execute

# Custom folder structure
python organize.py --structure "Genre|Year|Artist"

# Fix malformed DATE tags
python organize.py --fixYears
python organize.py --fixYears --execute

# Flatten
python organize.py --flatten
python organize.py --flatten --execute
```

## Flags

| Flag | Default | Description |
|---|---|---|
| `--root PATH` | `.env` `MUSIC_ROOT` or CWD | Root folder to operate on |
| `--execute` | dry-run | Apply changes (without this flag nothing is written) |
| `--structure TOKENS` | `Year\|Genre\|Artist\|Month` | Pipe-separated folder hierarchy |
| `--only-root` | — | Only process files directly in root; skip subdirectories |
| `--fixYears` | — | Normalize DATE tags to 4-digit year instead of reorganizing |
| `--flatten` | — | Move all music files to root, removing all subfolders |

### `--structure` tokens

Tokens are case-insensitive and can be combined in any order:

| Token | Description |
|---|---|
| `Year` | Release year (4-digit) |
| `Month` | Release month (zero-padded, `01`–`12`) |
| `Genre` | Normalized genre name |
| `Artist` | Track artist (or `Various Artists` for compilations) |

Examples:
```
Year|Genre|Artist|Month   → 2025/Melodic House & Techno/Massano/04/
Genre|Year|Artist         → Melodic House & Techno/2025/Massano/
Artist|Year               → Massano/2025/
```

## How it works

1. **Reads embedded tags** via `ffprobe` (`artist`, `album_artist`, `genre`, `date`, `TDOR`/`TRDA`)
2. **Falls back to folder-name heuristics** for files with missing/incomplete tags:
   - `[YYYY] Artist - Album` → year + artist
   - `Beatport Top 100 YYYY-MM Month YYYY` → year + month
   - `Beatport Best New <Genre> [Month YYYY]` → genre + date
   - `Singles week NN YYYY` / `WK05 2026` → ISO week converted to month
   - Scene format `VA-Release_Name-WEB-YYYY-GROUP` → year
3. **Normalizes genres** — compound Beatport tags like `edm;edm:techno:festival:melodic` resolve to the most specific known genre (`Melodic House & Techno`)
4. **No overwrites** — existing files at the target path are always skipped
5. **Cleans up** empty source directories after moving

## Conventions

| Value | Folder name |
|---|---|
| Unknown month | `00` |
| Unknown year | `Unknown` |
| Unknown genre | `Unknown` |
| VA / Various Artists | `Various Artists` |

Non-music files (`.nfo`, `.sfv`, `.m3u`, `.jpg`, `.crdownload`, etc.) are ignored and left in place.
