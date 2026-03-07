"""
test_app.py - Pytest tests for database operations and filtering logic.

Run with:
    pytest test_app.py -v
"""

import pytest

from db import init_db, upsert_movie, get_all_movies, filter_movies, delete_movie


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path):
    """Return the path to a fresh, initialised SQLite database in a tmp directory."""
    db_file = str(tmp_path / "test_watchlist.db")
    init_db(db_file)
    return db_file


@pytest.fixture
def populated_db(tmp_db):
    """A database pre-loaded with a small set of movies for filter tests."""
    movies = [
        {
            "title": "Inception",
            "genre": "Sci-Fi, Thriller",
            "rating": 8.8,
            "length": 148,
            "source": "imdb",
        },
        {
            "title": "The Dark Knight",
            "genre": "Action, Crime",
            "rating": 9.0,
            "length": 152,
            "source": "imdb",
        },
        {
            "title": "Interstellar",
            "genre": "Sci-Fi, Drama",
            "rating": 8.6,
            "length": 169,
            "source": "google",
        },
        {
            "title": "Parasite",
            "genre": "Thriller, Drama",
            "rating": 8.5,
            "length": 132,
            "source": "imdb",
        },
        {
            "title": "The Grand Budapest Hotel",
            "genre": "Comedy, Drama",
            "rating": 8.1,
            "length": 99,
            "source": "google",
        },
        {
            "title": "Mad Max: Fury Road",
            "genre": "Action, Adventure",
            "rating": 8.1,
            "length": 120,
            "source": "imdb",
        },
        {
            "title": "No Metadata Movie",
            "genre": None,
            "rating": None,
            "length": None,
            "source": "imdb",
        },
    ]
    for m in movies:
        upsert_movie(
            title=m["title"],
            genre=m["genre"],
            rating=m["rating"],
            length=m["length"],
            source=m["source"],
            db_path=tmp_db,
        )
    return tmp_db


# ---------------------------------------------------------------------------
# init_db
# ---------------------------------------------------------------------------


class TestInitDb:
    def test_creates_movies_table(self, tmp_db):
        """movies table should exist after init_db."""
        import sqlite3

        conn = sqlite3.connect(tmp_db)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='movies'"
        ).fetchall()
        conn.close()
        assert len(tables) == 1

    def test_idempotent(self, tmp_db):
        """Calling init_db twice should not raise an error."""
        init_db(tmp_db)  # second call
        movies = get_all_movies(tmp_db)
        assert isinstance(movies, list)


# ---------------------------------------------------------------------------
# upsert_movie
# ---------------------------------------------------------------------------


class TestUpsertMovie:
    def test_insert_new_movie(self, tmp_db):
        upsert_movie("Parasite", genre="Thriller", rating=8.5, length=132, source="imdb", db_path=tmp_db)
        movies = get_all_movies(tmp_db)
        assert len(movies) == 1
        assert movies[0]["title"] == "Parasite"

    def test_insert_multiple_movies(self, tmp_db):
        upsert_movie("Movie A", source="imdb", db_path=tmp_db)
        upsert_movie("Movie B", source="imdb", db_path=tmp_db)
        assert len(get_all_movies(tmp_db)) == 2

    def test_no_duplicate_same_title_same_source(self, tmp_db):
        upsert_movie("Inception", genre="Sci-Fi", rating=8.8, source="imdb", db_path=tmp_db)
        upsert_movie("Inception", genre="Sci-Fi", rating=8.8, source="imdb", db_path=tmp_db)
        assert len(get_all_movies(tmp_db)) == 1

    def test_same_title_different_source_creates_two_rows(self, tmp_db):
        upsert_movie("Inception", genre="Sci-Fi", rating=8.8, source="imdb", db_path=tmp_db)
        upsert_movie("Inception", genre="Sci-Fi", rating=8.9, source="google", db_path=tmp_db)
        assert len(get_all_movies(tmp_db)) == 2

    def test_upsert_updates_existing_fields(self, tmp_db):
        upsert_movie("Dune", genre="Sci-Fi", rating=7.9, length=155, source="imdb", db_path=tmp_db)
        # Update with corrected rating
        upsert_movie("Dune", genre="Sci-Fi, Adventure", rating=8.0, length=155, source="imdb", db_path=tmp_db)
        movies = get_all_movies(tmp_db)
        assert len(movies) == 1
        assert movies[0]["rating"] == 8.0
        assert movies[0]["genre"] == "Sci-Fi, Adventure"

    def test_insert_minimal_fields(self, tmp_db):
        """Only title is required; all other fields can be None."""
        upsert_movie("Mystery Film", db_path=tmp_db)
        movies = get_all_movies(tmp_db)
        assert len(movies) == 1
        assert movies[0]["title"] == "Mystery Film"
        assert movies[0]["rating"] is None

    def test_insert_null_source(self, tmp_db):
        """source=None inserts two rows because SQLite treats NULL != NULL for UNIQUE."""
        upsert_movie("Film A", source=None, db_path=tmp_db)
        upsert_movie("Film A", source=None, db_path=tmp_db)
        # SQLite UNIQUE constraint does not consider two NULLs equal, so both rows insert.
        movies = get_all_movies(tmp_db)
        assert len(movies) == 2


# ---------------------------------------------------------------------------
# get_all_movies
# ---------------------------------------------------------------------------


class TestGetAllMovies:
    def test_empty_database(self, tmp_db):
        assert get_all_movies(tmp_db) == []

    def test_returns_list_of_dicts(self, populated_db):
        movies = get_all_movies(populated_db)
        assert isinstance(movies, list)
        for m in movies:
            assert isinstance(m, dict)

    def test_returns_all_expected_fields(self, populated_db):
        movies = get_all_movies(populated_db)
        required_fields = {"id", "title", "genre", "rating", "length", "source"}
        for m in movies:
            assert required_fields.issubset(m.keys())

    def test_order_is_alphabetical(self, populated_db):
        titles = [m["title"] for m in get_all_movies(populated_db)]
        assert titles == sorted(titles)


# ---------------------------------------------------------------------------
# filter_movies
# ---------------------------------------------------------------------------


class TestFilterMovies:
    def test_no_filters_returns_all_rated(self, populated_db):
        all_movies = get_all_movies(populated_db)
        rated_count = sum(1 for m in all_movies if m["rating"] is not None)
        filtered = filter_movies(db_path=populated_db)
        assert len(filtered) == rated_count

    def test_min_rating_filter(self, populated_db):
        results = filter_movies(min_rating=8.7, db_path=populated_db)
        for m in results:
            assert m["rating"] >= 8.7

    def test_max_rating_filter(self, populated_db):
        results = filter_movies(max_rating=8.2, db_path=populated_db)
        for m in results:
            assert m["rating"] <= 8.2

    def test_rating_range_filter(self, populated_db):
        results = filter_movies(min_rating=8.5, max_rating=8.9, db_path=populated_db)
        for m in results:
            assert 8.5 <= m["rating"] <= 8.9

    def test_max_length_filter(self, populated_db):
        results = filter_movies(max_length=130, db_path=populated_db)
        for m in results:
            assert m["length"] is None or m["length"] <= 130

    def test_genre_single_filter(self, populated_db):
        results = filter_movies(genres=["Sci-Fi"], db_path=populated_db)
        for m in results:
            assert "sci-fi" in (m.get("genre") or "").lower()

    def test_genre_multiple_filter_or_logic(self, populated_db):
        """Passing multiple genres should return movies matching ANY of them."""
        results = filter_movies(genres=["Comedy", "Action"], db_path=populated_db)
        for m in results:
            genre_lower = (m.get("genre") or "").lower()
            assert "comedy" in genre_lower or "action" in genre_lower

    def test_genre_case_insensitive(self, populated_db):
        lower = filter_movies(genres=["sci-fi"], db_path=populated_db)
        upper = filter_movies(genres=["SCI-FI"], db_path=populated_db)
        mixed = filter_movies(genres=["Sci-Fi"], db_path=populated_db)
        assert len(lower) == len(upper) == len(mixed)

    def test_empty_genre_list_returns_all_rated(self, populated_db):
        all_movies = get_all_movies(populated_db)
        rated_count = sum(1 for m in all_movies if m["rating"] is not None)
        filtered = filter_movies(genres=[], db_path=populated_db)
        assert len(filtered) == rated_count

    def test_results_sorted_by_rating_desc(self, populated_db):
        results = filter_movies(db_path=populated_db)
        ratings = [m["rating"] for m in results if m["rating"] is not None]
        assert ratings == sorted(ratings, reverse=True)

    def test_combined_filters(self, populated_db):
        results = filter_movies(
            genres=["Drama"],
            min_rating=8.5,
            max_length=150,
            db_path=populated_db,
        )
        for m in results:
            assert "drama" in (m.get("genre") or "").lower()
            assert m["rating"] >= 8.5
            assert m["length"] is None or m["length"] <= 150

    def test_no_matches_returns_empty_list(self, populated_db):
        results = filter_movies(genres=["Horror"], min_rating=10.0, db_path=populated_db)
        assert results == []

    def test_top3_slice(self, populated_db):
        """Slicing the first 3 results simulates the Recommend page logic."""
        results = filter_movies(db_path=populated_db)
        top3 = results[:3]
        assert len(top3) <= 3

    def test_movies_with_no_rating_excluded(self, populated_db):
        """Movies with NULL rating must not appear in filter_movies results."""
        results = filter_movies(db_path=populated_db)
        null_rating_movies = [m for m in results if m["rating"] is None]
        assert null_rating_movies == []


# ---------------------------------------------------------------------------
# delete_movie
# ---------------------------------------------------------------------------


class TestDeleteMovie:
    def test_delete_existing_movie(self, tmp_db):
        upsert_movie("Delete Me", source="imdb", db_path=tmp_db)
        movies = get_all_movies(tmp_db)
        assert len(movies) == 1
        delete_movie(movies[0]["id"], db_path=tmp_db)
        assert get_all_movies(tmp_db) == []

    def test_delete_nonexistent_id_is_noop(self, tmp_db):
        """Deleting an ID that does not exist should not raise."""
        delete_movie(9999, db_path=tmp_db)
        assert get_all_movies(tmp_db) == []

    def test_delete_only_target_row(self, tmp_db):
        upsert_movie("Keep Me", source="imdb", db_path=tmp_db)
        upsert_movie("Delete Me", source="google", db_path=tmp_db)
        movies = get_all_movies(tmp_db)
        to_delete = next(m for m in movies if m["title"] == "Delete Me")
        delete_movie(to_delete["id"], db_path=tmp_db)
        remaining = get_all_movies(tmp_db)
        assert len(remaining) == 1
        assert remaining[0]["title"] == "Keep Me"


# ---------------------------------------------------------------------------
# Scraper helper functions (pure Python, no browser required)
# ---------------------------------------------------------------------------


class TestParseHelpers:
    """Tests for the pure-Python helper functions in scraper.py."""

    def test_parse_runtime_hours_and_minutes(self):
        from scraper import _parse_runtime

        assert _parse_runtime("2h 15m") == 135
        assert _parse_runtime("1h 30m") == 90

    def test_parse_runtime_hours_only(self):
        from scraper import _parse_runtime

        assert _parse_runtime("2h") == 120

    def test_parse_runtime_minutes_only(self):
        from scraper import _parse_runtime

        assert _parse_runtime("90 min") == 90
        assert _parse_runtime("105 minutes") == 105

    def test_parse_runtime_bare_number(self):
        from scraper import _parse_runtime

        assert _parse_runtime("90") == 90

    def test_parse_runtime_empty_string(self):
        from scraper import _parse_runtime

        assert _parse_runtime("") is None

    def test_parse_runtime_none(self):
        from scraper import _parse_runtime

        assert _parse_runtime(None) is None

    def test_parse_rating_fraction(self):
        from scraper import _parse_rating

        assert _parse_rating("7.5/10") == 7.5

    def test_parse_rating_bare_float(self):
        from scraper import _parse_rating

        assert _parse_rating("8.8") == 8.8

    def test_parse_rating_integer(self):
        from scraper import _parse_rating

        assert _parse_rating("9") == 9.0

    def test_parse_rating_empty_string(self):
        from scraper import _parse_rating

        assert _parse_rating("") is None

    def test_parse_rating_none(self):
        from scraper import _parse_rating

        assert _parse_rating(None) is None
