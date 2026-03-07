"""
app.py - Streamlit UI for the Watchlist Recommendation application.

Pages:
  1. My Watchlist - browse and manage all synced movies.
  2. Recommend    - filter-based recommendation engine (top 3 matches).

Run with:
    streamlit run app.py
"""

import streamlit as st
import pandas as pd
from db import init_db, get_all_movies, filter_movies, delete_movie

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Watchlist Recommender",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

DB_PATH = "watchlist.db"
init_db(DB_PATH)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _movies_dataframe(movies: list[dict]) -> pd.DataFrame:
    """Convert a list of movie dicts into a display-ready DataFrame."""
    if not movies:
        return pd.DataFrame(
            columns=["ID", "Title", "Genre", "Rating", "Length (min)", "Source"]
        )
    df = pd.DataFrame(movies)
    df = df.rename(
        columns={
            "id": "ID",
            "title": "Title",
            "genre": "Genre",
            "rating": "Rating",
            "length": "Length (min)",
            "source": "Source",
        }
    )
    col_order = ["ID", "Title", "Genre", "Rating", "Length (min)", "Source"]
    for col in col_order:
        if col not in df.columns:
            df[col] = None
    return df[col_order]


def _collect_genres(movies: list[dict]) -> list[str]:
    """Return a sorted, unique list of all genres found in *movies*."""
    genres: set[str] = set()
    for m in movies:
        raw = (m.get("genre") or "").strip()
        for part in raw.split(","):
            g = part.strip()
            if g:
                genres.add(g)
    return sorted(genres)


# ---------------------------------------------------------------------------
# Page: My Watchlist
# ---------------------------------------------------------------------------


def page_watchlist() -> None:
    st.title("🎬 My Watchlist")
    st.caption("All movies currently synced from Google Watchlist and IMDb.")

    movies = get_all_movies(DB_PATH)

    if not movies:
        st.info(
            "Your watchlist is empty.  "
            "Run `python scraper.py` to pull in your Google / IMDb watchlists."
        )
        return

    # --- Summary metrics ---
    total = len(movies)
    rated = [m for m in movies if m.get("rating") is not None]
    avg_rating = round(sum(m["rating"] for m in rated) / len(rated), 2) if rated else "N/A"
    sources = {m.get("source") for m in movies if m.get("source")}

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Movies", total)
    col2.metric("Avg Rating", avg_rating)
    col3.metric("Sources", ", ".join(sorted(sources)) if sources else "—")

    st.divider()

    # --- Search / filter ---
    search_term = st.text_input("🔍 Search by title", placeholder="e.g. Inception")

    filtered_movies = movies
    if search_term:
        filtered_movies = [
            m for m in movies if search_term.lower() in (m.get("title") or "").lower()
        ]

    df = _movies_dataframe(filtered_movies)

    st.dataframe(
        df.drop(columns=["ID"]),
        use_container_width=True,
        hide_index=True,
    )

    st.caption(f"Showing {len(filtered_movies)} of {total} movies.")

    # --- Delete a movie ---
    with st.expander("🗑️ Remove a movie from the database"):
        movie_titles = {m["title"]: m["id"] for m in movies}
        selected_title = st.selectbox("Select movie to remove", options=list(movie_titles.keys()))
        if st.button("Delete selected movie", type="primary"):
            delete_movie(movie_titles[selected_title], DB_PATH)
            st.success(f"'{selected_title}' has been removed.")
            st.rerun()


# ---------------------------------------------------------------------------
# Page: Recommend
# ---------------------------------------------------------------------------


def page_recommend() -> None:
    st.title("🍿 Movie Recommender")
    st.caption("Get personalised picks from YOUR watchlist only.")

    movies = get_all_movies(DB_PATH)

    if not movies:
        st.info(
            "No movies found in your watchlist.  "
            "Run `python scraper.py` first, then come back here."
        )
        return

    all_genres = _collect_genres(movies)

    st.subheader("Filters")

    col_a, col_b, col_c = st.columns(3)

    with col_a:
        selected_genres = st.multiselect(
            "🎭 Genre / Mood",
            options=all_genres,
            help="Leave empty to include all genres.",
        )

    with col_b:
        min_rating, max_rating = st.slider(
            "⭐ Rating range",
            min_value=0.0,
            max_value=10.0,
            value=(5.0, 10.0),
            step=0.5,
            help="Only movies whose rating falls in this range.",
        )

    with col_c:
        length_options = {
            "Any length": None,
            "Short  (≤ 90 min)": 90,
            "Medium (≤ 120 min)": 120,
            "Long   (≤ 150 min)": 150,
            "Epic   (≤ 180 min)": 180,
        }
        chosen_length_label = st.selectbox("⏱️ Max Length", options=list(length_options.keys()))
        max_length = length_options[chosen_length_label]

    st.divider()

    results = filter_movies(
        genres=selected_genres if selected_genres else None,
        min_rating=min_rating,
        max_rating=max_rating,
        max_length=max_length,
        db_path=DB_PATH,
    )

    top3 = results[:3]

    if not top3:
        st.warning(
            "No movies match your current filters.  "
            "Try relaxing the genre, rating, or length constraints."
        )
        return

    st.subheader(f"🏆 Top {len(top3)} Recommendation{'s' if len(top3) > 1 else ''}")

    for rank, movie in enumerate(top3, start=1):
        with st.container(border=True):
            cols = st.columns([0.07, 0.93])
            cols[0].markdown(f"### #{rank}")
            with cols[1]:
                st.markdown(f"### {movie['title']}")
                meta_parts = []
                if movie.get("genre"):
                    meta_parts.append(f"🎭 {movie['genre']}")
                if movie.get("rating") is not None:
                    meta_parts.append(f"⭐ {movie['rating']}/10")
                if movie.get("length") is not None:
                    h, m = divmod(movie["length"], 60)
                    runtime_str = f"{h}h {m}m" if h else f"{m}m"
                    meta_parts.append(f"⏱️ {runtime_str}")
                if movie.get("source"):
                    meta_parts.append(f"📡 {movie['source'].capitalize()}")
                st.markdown("  ·  ".join(meta_parts) if meta_parts else "_No metadata_")

    if len(results) > 3:
        with st.expander(f"Show all {len(results)} matches"):
            df = _movies_dataframe(results)
            st.dataframe(df.drop(columns=["ID"]), use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

PAGES = {
    "🎬 My Watchlist": page_watchlist,
    "🍿 Recommend": page_recommend,
}

st.sidebar.title("Navigation")
selection = st.sidebar.radio("Go to", list(PAGES.keys()), label_visibility="collapsed")
PAGES[selection]()

st.sidebar.divider()
st.sidebar.caption(
    "**Watchlist Recommender**\n\n"
    "Sync your watchlists with:\n"
    "```bash\npython scraper.py\n```"
)
