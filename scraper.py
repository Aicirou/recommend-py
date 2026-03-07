"""
scraper.py - Playwright-based scraper for Google Watchlist and IMDb Watchlist.

Uses your local browser profile (user-data-dir) to bypass logins automatically.
"""

import asyncio
import re
from typing import Optional

from playwright.async_api import async_playwright, BrowserContext, Page

from db import upsert_movie, init_db


# ---------------------------------------------------------------------------
# Compiled regex patterns (module-level for performance)
# ---------------------------------------------------------------------------

_RE_HM = re.compile(r"(\d+)\s*h(?:\s*(\d+)\s*m)?", re.IGNORECASE)
_RE_MIN = re.compile(r"(\d+)\s*(?:min|minutes?)", re.IGNORECASE)
_RE_BARE_INT = re.compile(r"^\d+$")
_RE_RATING = re.compile(r"(\d+(?:\.\d+)?)")
_RE_LIST_NUM = re.compile(r"^\d+\.\s*")


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _parse_runtime(text: Optional[str]) -> Optional[int]:
    """Convert a human-readable runtime string to total minutes.

    Handles formats such as:
    - "2h 15m" -> 135
    - "1h"     -> 60
    - "90 min" -> 90
    - "90"     -> 90  (bare number assumed to be minutes)
    """
    if not text:
        return None
    text = text.strip()

    # "Xh Ym" or "Xh" format
    hm = _RE_HM.search(text)
    if hm:
        hours = int(hm.group(1))
        minutes = int(hm.group(2)) if hm.group(2) else 0
        return hours * 60 + minutes

    # "X min" or "X minutes"
    m = _RE_MIN.search(text)
    if m:
        return int(m.group(1))

    # Bare integer
    if _RE_BARE_INT.match(text):
        return int(text)

    return None


def _parse_rating(text: Optional[str]) -> Optional[float]:
    """Extract a numeric rating from a string like '7.5/10' or '7.5'."""
    if not text:
        return None
    m = _RE_RATING.search(text)
    return float(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# Google Watchlist scraper
# ---------------------------------------------------------------------------

async def _scrape_google_watchlist(
    page: Page,
    url: str = "https://www.google.com/search?q=my+watchlist",
) -> list[dict]:
    """Scrape titles from the Google 'Want to watch' knowledge panel.

    Google shows a limited carousel of items from your watchlist when you
    search for "my watchlist" while logged in.  After waiting for dynamic
    content to settle, we query the DOM once for all visible carousel cards.

    Returns a list of dicts with keys: title, genre, rating, length, source.
    """
    movies: list[dict] = []

    await page.goto(url, wait_until="domcontentloaded", timeout=60_000)

    # Accept cookie/consent dialogs if present
    for selector in ['button:has-text("Accept all")', 'button:has-text("I agree")']:
        try:
            btn = page.locator(selector).first
            if await btn.is_visible(timeout=3_000):
                await btn.click()
                await page.wait_for_load_state("domcontentloaded")
                break
        except Exception:
            pass

    # Allow dynamic content to load
    await page.wait_for_timeout(3_000)

    # Google's watchlist cards live inside a knowledge-panel carousel
    # Each card typically has a title, sometimes genre/rating info
    cards = await page.query_selector_all(
        'div[data-hveid] [data-docid], '
        'div.kp-wholepage div[jsname] g-scrolling-carousel div[role="listitem"]'
    )

    for card in cards:
        title_el = await card.query_selector('div[role="heading"], .kltat, .yKMVIe')
        if not title_el:
            continue
        title = (await title_el.inner_text()).strip()
        if not title:
            continue

        genre = None
        rating = None
        length = None

        # Try to grab supplementary info (genre/rating/runtime rows)
        meta_rows = await card.query_selector_all('.ellip, .rVusze, .z4P7Td')
        texts = [await el.inner_text() for el in meta_rows]
        for txt in texts:
            if re.search(r"\d+h|\d+\s*min", txt, re.IGNORECASE) and length is None:
                length = _parse_runtime(txt)
            elif re.search(r"\d+(\.\d+)?(/10)?", txt) and rating is None:
                rating = _parse_rating(txt)
            elif genre is None and re.search(r"[A-Za-z]", txt):
                genre = txt.strip()

        movies.append(
            {
                "title": title,
                "genre": genre,
                "rating": rating,
                "length": length,
                "source": "google",
            }
        )

    return movies


# ---------------------------------------------------------------------------
# IMDb Watchlist scraper
# ---------------------------------------------------------------------------

async def _scrape_imdb_watchlist(
    page: Page,
    imdb_user_id: Optional[str] = None,
) -> list[dict]:
    """Scrape the IMDb watchlist for a given user.

    If *imdb_user_id* is not provided the scraper first navigates to
    the IMDb homepage to detect the currently logged-in user's watchlist URL
    from the nav bar.

    Returns a list of dicts with keys: title, genre, rating, length, source.
    """
    movies: list[dict] = []

    if imdb_user_id:
        url = f"https://www.imdb.com/user/{imdb_user_id}/watchlist"
    else:
        # Let IMDb redirect us to our own watchlist
        url = "https://www.imdb.com/watchlist"

    await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    await page.wait_for_timeout(3_000)

    # Handle sign-in redirect
    if "signin" in page.url.lower() or "registration" in page.url.lower():
        print("[IMDb] Not logged in – cannot scrape watchlist.")
        return movies

    # Wait for list items to appear
    try:
        await page.wait_for_selector(
            'li.ipc-metadata-list-summary-item, div.lister-item',
            timeout=15_000,
        )
    except Exception:
        print("[IMDb] Watchlist items did not load.")
        return movies

    # Scroll to load all lazy-loaded items
    previous_count = 0
    for _ in range(20):
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1_500)
        items = await page.query_selector_all(
            'li.ipc-metadata-list-summary-item, div.lister-item'
        )
        if len(items) == previous_count:
            break
        previous_count = len(items)

    items = await page.query_selector_all(
        'li.ipc-metadata-list-summary-item, div.lister-item'
    )

    for item in items:
        # --- Title ---
        title_el = await item.query_selector(
            'h3.ipc-title__text, h3.lister-item-header a, a.lister-item-header'
        )
        if not title_el:
            continue
        title = (await title_el.inner_text()).strip()
        # Remove leading list numbers like "1. Movie Title"
        title = _RE_LIST_NUM.sub("", title).strip()
        if not title:
            continue

        # --- Genre ---
        genre_el = await item.query_selector(
            'span.ipc-chip__text, span.genre, .genres-and-tags'
        )
        genre = None
        if genre_el:
            genre = (await genre_el.inner_text()).strip()

        # --- Rating ---
        rating_el = await item.query_selector(
            'span[aria-label*="IMDb rating"], span.ipc-rating-star--imdb, '
            'div.ratings-imdb-rating strong'
        )
        rating = None
        if rating_el:
            rating_text = await rating_el.get_attribute("aria-label") or await rating_el.inner_text()
            rating = _parse_rating(rating_text)

        # --- Runtime ---
        runtime_el = await item.query_selector(
            'span.ipc-inline-list__item:has-text("h"), '
            'span.runtime, '
            '.lister-item-year + .text-muted'
        )
        length = None
        if runtime_el:
            length = _parse_runtime(await runtime_el.inner_text())

        movies.append(
            {
                "title": title,
                "genre": genre,
                "rating": rating,
                "length": length,
                "source": "imdb",
            }
        )

    return movies


# ---------------------------------------------------------------------------
# Main entry-point
# ---------------------------------------------------------------------------

async def run_scraper(
    browser_type: str = "chromium",
    user_data_dir: Optional[str] = None,
    imdb_user_id: Optional[str] = None,
    scrape_google: bool = True,
    scrape_imdb: bool = True,
    db_path: str = "watchlist.db",
    headless: bool = False,
) -> list[dict]:
    """Launch Playwright, scrape watchlists, and persist results to the DB.

    Args:
        browser_type:  "chromium", "firefox", or "webkit".
        user_data_dir: Path to your browser's user-data directory so the
                       scraper inherits your existing login session.
                       If None, a temporary profile is used (you will be
                       prompted to log in manually).
        imdb_user_id:  IMDb user ID (e.g. "ur12345678").  Leave as None to
                       auto-detect from your logged-in session.
        scrape_google: Whether to scrape Google Watchlist.
        scrape_imdb:   Whether to scrape IMDb Watchlist.
        db_path:       Path to the SQLite database file.
        headless:      Run the browser without a visible UI.  Set to True
                       for scheduled/cron runs; keep False (default) for
                       interactive runs so you can handle CAPTCHAs.

    Returns:
        Combined list of movie dicts that were scraped and persisted.
    """
    init_db(db_path)
    all_movies: list[dict] = []

    async with async_playwright() as pw:
        browser_launcher = getattr(pw, browser_type)

        launch_kwargs: dict = {
            "headless": headless,
            "args": ["--disable-blink-features=AutomationControlled"],
        }

        browser = None
        if user_data_dir:
            # persistent_context keeps cookies/local-storage from your profile
            context: BrowserContext = await browser_launcher.launch_persistent_context(
                user_data_dir,
                **launch_kwargs,
            )
            page = await context.new_page()
        else:
            browser = await browser_launcher.launch(**launch_kwargs)
            context = await browser.new_context()
            page = await context.new_page()

        try:
            if scrape_google:
                print("[Google] Scraping watchlist …")
                google_movies = await _scrape_google_watchlist(page)
                print(f"[Google] Found {len(google_movies)} items.")
                all_movies.extend(google_movies)

            if scrape_imdb:
                print("[IMDb] Scraping watchlist …")
                imdb_movies = await _scrape_imdb_watchlist(page, imdb_user_id)
                print(f"[IMDb] Found {len(imdb_movies)} items.")
                all_movies.extend(imdb_movies)
        finally:
            await context.close()
            if browser is not None:
                await browser.close()

    # Persist to database (upsert to avoid duplicates)
    for movie in all_movies:
        upsert_movie(
            title=movie["title"],
            genre=movie.get("genre"),
            rating=movie.get("rating"),
            length=movie.get("length"),
            source=movie.get("source"),
            db_path=db_path,
        )

    print(f"[Scraper] Done. {len(all_movies)} movies saved/updated.")
    return all_movies


def main() -> None:
    """CLI entry-point.  Run:  python scraper.py --help"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Scrape Google/IMDb watchlists using your local browser profile."
    )
    parser.add_argument(
        "--browser",
        default="chromium",
        choices=["chromium", "firefox", "webkit"],
        help="Browser type to use (default: chromium).",
    )
    parser.add_argument(
        "--user-data-dir",
        default=None,
        help=(
            "Path to your browser profile directory so login sessions are reused.\n"
            "Chrome example:  ~/.config/google-chrome/Default\n"
            "Edge example:    ~/.config/microsoft-edge/Default\n"
            "Windows Chrome:  C:\\Users\\<USER>\\AppData\\Local\\Google\\Chrome\\User Data\\Default"
        ),
    )
    parser.add_argument(
        "--imdb-user-id",
        default=None,
        help="IMDb user ID (e.g. ur12345678).  Auto-detected if omitted.",
    )
    parser.add_argument("--no-google", action="store_true", help="Skip Google Watchlist.")
    parser.add_argument("--no-imdb", action="store_true", help="Skip IMDb Watchlist.")
    parser.add_argument("--db", default="watchlist.db", help="Path to SQLite database file.")
    parser.add_argument(
        "--headless",
        action="store_true",
        help=(
            "Run the browser without a visible UI.  "
            "Recommended for scheduled/cron runs; keep off (default) for "
            "interactive sessions where you may need to handle CAPTCHAs."
        ),
    )

    args = parser.parse_args()

    asyncio.run(
        run_scraper(
            browser_type=args.browser,
            user_data_dir=args.user_data_dir,
            imdb_user_id=args.imdb_user_id,
            scrape_google=not args.no_google,
            scrape_imdb=not args.no_imdb,
            db_path=args.db,
            headless=args.headless,
        )
    )


if __name__ == "__main__":
    main()
