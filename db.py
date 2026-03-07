"""
db.py - SQLite3 database operations for the Watchlist Recommendation app.

Handles schema creation, inserting/updating movies, and filtering logic.
"""

import sqlite3
from typing import Optional

DB_PATH = "watchlist.db"


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Return a database connection with row_factory set to sqlite3.Row."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = DB_PATH) -> None:
    """Initialize the database schema if it does not already exist."""
    conn = get_connection(db_path)
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS movies (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                title   TEXT    NOT NULL,
                genre   TEXT,
                rating  REAL,
                length  INTEGER,
                source  TEXT,
                UNIQUE(title, source)
            )
            """
        )
    conn.close()


def upsert_movie(
    title: str,
    genre: Optional[str] = None,
    rating: Optional[float] = None,
    length: Optional[int] = None,
    source: Optional[str] = None,
    db_path: str = DB_PATH,
) -> None:
    """Insert a movie or update it if (title, source) already exists.

    Args:
        title:   Movie title.
        genre:   Comma-separated genre string (e.g. "Action, Drama").
        rating:  Numeric rating (0-10 scale).
        length:  Runtime in minutes.
        source:  Origin of the entry, e.g. "google" or "imdb".
        db_path: Path to the SQLite database file.
    """
    conn = get_connection(db_path)
    with conn:
        conn.execute(
            """
            INSERT INTO movies (title, genre, rating, length, source)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(title, source) DO UPDATE SET
                genre  = excluded.genre,
                rating = excluded.rating,
                length = excluded.length
            """,
            (title, genre, rating, length, source),
        )
    conn.close()


def get_all_movies(db_path: str = DB_PATH) -> list[dict]:
    """Return every movie in the database as a list of dicts."""
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT id, title, genre, rating, length, source FROM movies ORDER BY title"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def filter_movies(
    genres: Optional[list[str]] = None,
    min_rating: float = 0.0,
    max_rating: float = 10.0,
    max_length: Optional[int] = None,
    db_path: str = DB_PATH,
) -> list[dict]:
    """Filter movies from the watchlist according to given criteria.

    Args:
        genres:     List of genres to include (case-insensitive substring match).
                    Pass None or an empty list to skip genre filtering.
        min_rating: Minimum rating (inclusive). Defaults to 0.
        max_rating: Maximum rating (inclusive). Defaults to 10.
        max_length: Maximum runtime in minutes (inclusive). Pass None to skip.
        db_path:    Path to the SQLite database file.

    Returns:
        List of matching movie dicts sorted by rating descending, then title
        and id for deterministic ordering. Movies without a rating are excluded;
        only movies whose rating falls within [min_rating, max_rating] are returned.
    """
    conn = get_connection(db_path)

    query = """
        SELECT id, title, genre, rating, length, source
        FROM movies
        WHERE rating >= ? AND rating <= ?
    """
    params: list = [min_rating, max_rating]

    if max_length is not None:
        query += " AND (length IS NULL OR length <= ?)"
        params.append(max_length)

    query += " ORDER BY rating DESC, title ASC, id ASC"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    results = [dict(row) for row in rows]

    # Genre filtering is done in Python so we can support comma-separated values
    if genres:
        genres_lower = [g.strip().lower() for g in genres if g.strip()]
        if genres_lower:
            filtered = []
            for movie in results:
                movie_genre = (movie.get("genre") or "").lower()
                if any(g in movie_genre for g in genres_lower):
                    filtered.append(movie)
            results = filtered

    return results


def delete_movie(movie_id: int, db_path: str = DB_PATH) -> None:
    """Delete a movie by its primary key.

    Args:
        movie_id: The integer primary key of the movie to delete.
        db_path:  Path to the SQLite database file.
    """
    conn = get_connection(db_path)
    with conn:
        conn.execute("DELETE FROM movies WHERE id = ?", (movie_id,))
    conn.close()
