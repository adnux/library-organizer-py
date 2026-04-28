"""
Tests for organize.py — covers all pure (non-I/O) functions.

Run with:
    python -m pytest test_organize.py -v
  or:
    python -m unittest test_organize -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from organize import (
    normalize_genre,
    normalize_artist,
    parse_date_tag,
    parse_folder_name,
    parse_structure,
    build_target_path,
    week_to_month,
)


class TestNormalizeGenre(unittest.TestCase):
    def test_empty_returns_none(self):
        self.assertIsNone(normalize_genre(None))
        self.assertIsNone(normalize_genre(""))

    def test_melodic_house_and_techno_variants(self):
        for raw in [
            "Melodic House & Techno",
            "Melodic H&T",
            "melodic house and techno",
            "melodic house & techno",
        ]:
            self.assertEqual(normalize_genre(raw), "Melodic House & Techno", msg=raw)

    def test_melodic_techno_maps_to_techno(self):
        # "Melodic Techno" has no "house" — doesn't match Melodic H&T rule, falls through to Techno
        self.assertEqual(normalize_genre("Melodic Techno"), "Techno")

    def test_indie_dance(self):
        self.assertEqual(normalize_genre("Indie Dance"), "Indie Dance")

    def test_techno_variants(self):
        for raw in ["Techno", "Techno (Peak Time / Driving)", "Driving Techno"]:
            self.assertEqual(normalize_genre(raw), "Techno", msg=raw)

    def test_drum_and_bass(self):
        self.assertEqual(normalize_genre("Drum & Bass"), "Drum & Bass")
        self.assertEqual(normalize_genre("DnB"), "Drum & Bass")

    def test_trance(self):
        self.assertEqual(normalize_genre("Trance"), "Trance")

    def test_house(self):
        self.assertEqual(normalize_genre("House"), "House")
        self.assertEqual(normalize_genre("Deep House"), "House")

    def test_electronic_variants(self):
        self.assertEqual(normalize_genre("Electronic"), "Electronic")
        self.assertEqual(normalize_genre("EDM"), "Electronic")
        self.assertEqual(normalize_genre("Electronica"), "Electronic")

    def test_dance(self):
        self.assertEqual(normalize_genre("Dance"), "Dance")

    def test_electro(self):
        self.assertEqual(normalize_genre("Electro"), "Electro")

    def test_pop(self):
        self.assertEqual(normalize_genre("Pop"), "Pop")

    def test_unknown_genre_passed_through(self):
        self.assertEqual(normalize_genre("Jazz"), "Jazz")
        self.assertEqual(normalize_genre("Classical"), "Classical")

    def test_multi_segment_rule_order_wins(self):
        # Rules iterate first, then segments — first rule matching ANY segment wins.
        # Techno rule (#4) comes before House rule (#7), so "Techno" segment wins.
        self.assertEqual(normalize_genre("Techno; House"), "Techno")
        self.assertEqual(normalize_genre("House, Techno"), "Techno")


class TestNormalizeArtist(unittest.TestCase):
    def test_empty_and_none(self):
        self.assertEqual(normalize_artist(None), "Various Artists")
        self.assertEqual(normalize_artist(""), "Various Artists")

    def test_va_abbreviation(self):
        self.assertEqual(normalize_artist("VA"), "Various Artists")
        self.assertEqual(normalize_artist("va"), "Various Artists")

    def test_various_prefix(self):
        self.assertEqual(normalize_artist("Various Artists"), "Various Artists")
        self.assertEqual(normalize_artist("Various"), "Various Artists")
        self.assertEqual(normalize_artist("various artists"), "Various Artists")

    def test_single_artist_preserved(self):
        self.assertEqual(normalize_artist("Massano"), "Massano")
        self.assertEqual(normalize_artist("Bicep"), "Bicep")

    def test_whitespace_trimmed(self):
        self.assertEqual(normalize_artist("  Bicep  "), "Bicep")

    def test_comma_separated_becomes_va(self):
        self.assertEqual(normalize_artist("Agoria, Mooglie"), "Various Artists")
        self.assertEqual(normalize_artist("A, B, C"), "Various Artists")


class TestParseDateTag(unittest.TestCase):
    def test_year_only(self):
        self.assertEqual(parse_date_tag({"date": "2025"}), (2025, None))

    def test_year_month(self):
        self.assertEqual(parse_date_tag({"date": "2025-04"}), (2025, 4))

    def test_full_date(self):
        self.assertEqual(parse_date_tag({"date": "2025-04-15"}), (2025, 4))

    def test_tdor_priority(self):
        self.assertEqual(parse_date_tag({"tdor": "2023-07", "date": "2024"}), (2023, 7))

    def test_trda_tag(self):
        self.assertEqual(parse_date_tag({"trda": "2022-12"}), (2022, 12))

    def test_year_tag_fallback(self):
        self.assertEqual(parse_date_tag({"year": "2020"}), (2020, None))

    def test_missing_tags(self):
        self.assertEqual(parse_date_tag({}), (None, None))

    def test_empty_date(self):
        self.assertEqual(parse_date_tag({"date": ""}), (None, None))

    def test_garbage_date(self):
        self.assertEqual(parse_date_tag({"date": "https://djsoundtop.com"}), (None, None))


class TestWeekToMonth(unittest.TestCase):
    # Reference: ISO week 1 of 2024 starts Jan 1 (Monday).
    def test_week_1_2024(self):
        self.assertEqual(week_to_month(2024, 1), 1)

    def test_week_5_2024(self):
        self.assertEqual(week_to_month(2024, 5), 1)  # Jan 29

    def test_week_6_2024(self):
        self.assertEqual(week_to_month(2024, 6), 2)  # Feb 5

    def test_week_14_2024(self):
        self.assertEqual(week_to_month(2024, 14), 4)  # Apr 1

    def test_week_26_2024(self):
        self.assertEqual(week_to_month(2024, 26), 6)  # Jun 24

    def test_week_52_2024(self):
        self.assertEqual(week_to_month(2024, 52), 12)  # Dec 23

    def test_invalid_week_returns_none(self):
        self.assertIsNone(week_to_month(2024, 99))


class TestParseFolderName(unittest.TestCase):
    def test_explicit_date(self):
        year, month, genre, artist = parse_folder_name("Beatport Top 100 2025-04")
        self.assertEqual(year, 2025)
        self.assertEqual(month, 4)

    def test_month_name_and_year(self):
        year, month, genre, artist = parse_folder_name("Beatport Best New Tracks April 2025")
        self.assertEqual(year, 2025)
        self.assertEqual(month, 4)

    def test_march_year(self):
        year, month, genre, artist = parse_folder_name("New Releases March 2024")
        self.assertEqual(year, 2024)
        self.assertEqual(month, 3)

    def test_bracketed_year_artist(self):
        year, month, genre, artist = parse_folder_name("[2024] Massano - Every Day")
        self.assertEqual(year, 2024)
        self.assertEqual(artist, "Massano")

    def test_artist_dash_year_pattern(self):
        year, month, genre, artist = parse_folder_name("Massano - 2024 - Every Day")
        self.assertEqual(year, 2024)
        self.assertEqual(artist, "Massano")

    def test_va_prefix_no_artist(self):
        year, month, genre, artist = parse_folder_name("VA - 2025 - Compilation")
        self.assertEqual(year, 2025)
        self.assertIsNone(artist)

    def test_genre_melodic_house_techno(self):
        year, month, genre, artist = parse_folder_name(
            "Beatport Best New Melodic House & Techno April 2025"
        )
        self.assertEqual(genre, "Melodic House & Techno")
        self.assertEqual(year, 2025)
        self.assertEqual(month, 4)

    def test_genre_techno(self):
        _, _, genre, _ = parse_folder_name("Beatport Techno Top 100 2024")
        self.assertEqual(genre, "Techno")

    def test_plain_year(self):
        year, month, genre, artist = parse_folder_name("Singles 2023")
        self.assertEqual(year, 2023)
        self.assertIsNone(month)

    def test_no_metadata(self):
        year, month, genre, artist = parse_folder_name("Random Folder")
        self.assertIsNone(year)
        self.assertIsNone(month)
        self.assertIsNone(genre)
        self.assertIsNone(artist)


class TestParseStructure(unittest.TestCase):
    def test_default_structure(self):
        self.assertEqual(
            parse_structure("Year|Genre|Artist|Month"),
            ["year", "genre", "artist", "month"],
        )

    def test_partial_structure(self):
        self.assertEqual(parse_structure("Genre|Artist"), ["genre", "artist"])

    def test_single_token(self):
        self.assertEqual(parse_structure("year"), ["year"])

    def test_whitespace_trimmed(self):
        self.assertEqual(parse_structure("Year | Genre"), ["year", "genre"])

    def test_case_insensitive(self):
        self.assertEqual(parse_structure("YEAR|GENRE"), ["year", "genre"])

    def test_invalid_token_raises(self):
        with self.assertRaises(ValueError):
            parse_structure("Invalid")

    def test_mixed_valid_invalid_raises(self):
        with self.assertRaises(ValueError):
            parse_structure("Year|BadToken|Month")

    def test_empty_string_returns_empty_list(self):
        self.assertEqual(parse_structure(""), [])


class TestBuildTargetPath(unittest.TestCase):
    def test_default_structure(self):
        root = Path("/root/Electronic")
        meta = {
            "year": "2025",
            "month": "04",
            "genre": "Melodic House & Techno",
            "artist": "Massano",
        }
        structure = ["year", "genre", "artist", "month"]
        result = build_target_path(root, meta, structure, "track.flac")
        expected = Path("/root/Electronic/2025/Melodic House & Techno/Massano/04/track.flac")
        self.assertEqual(result, expected)

    def test_custom_structure(self):
        root = Path("/music")
        meta = {"year": "2024", "genre": "House", "artist": "Bicep", "month": "06"}
        result = build_target_path(root, meta, ["genre", "artist"], "song.mp3")
        self.assertEqual(result, Path("/music/House/Bicep/song.mp3"))

    def test_various_artists(self):
        root = Path("/music")
        meta = {"year": "2026", "genre": "Techno", "artist": "Various Artists", "month": "03"}
        result = build_target_path(root, meta, ["year", "genre", "artist", "month"], "comp.flac")
        self.assertEqual(result, Path("/music/2026/Techno/Various Artists/03/comp.flac"))


if __name__ == "__main__":
    unittest.main()
