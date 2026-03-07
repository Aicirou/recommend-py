# recommend-py

A fully local, self-hosted **Watchlist Recommendation** application that syncs your Google Watchlist and IMDb Watchlist into a local SQLite database and lets you browse + filter personalised movie picks through a Streamlit UI.

---

## 📁 Project structure

```
recommend-py/
├── app.py           # Streamlit UI (My Watchlist + Recommend pages)
├── scraper.py       # Playwright scraper (Google Watchlist + IMDb Watchlist)
├── db.py            # SQLite3 schema & operations
├── test_app.py      # Pytest test suite
├── requirements.txt # Python dependencies
└── README.md        # This file
```

---

## 🗄️ Database schema

The single `movies` table in `watchlist.db`:

| Column | Type    | Notes                              |
|--------|---------|------------------------------------|
| id     | INTEGER | Auto-increment primary key         |
| title  | TEXT    | Movie title (NOT NULL)             |
| genre  | TEXT    | Comma-separated genres             |
| rating | REAL    | Numeric rating (0–10)              |
| length | INTEGER | Runtime in minutes                 |
| source | TEXT    | `"google"` or `"imdb"`             |

A `UNIQUE(title, source)` constraint prevents duplicates from the same source.

---

## ⚙️ Setup

### 1. Prerequisites

- Python 3.11+
- A modern Chrome, Edge, or Firefox installation

### 2. Clone and install

```bash
git clone https://github.com/Aicirou/recommend-py.git
cd recommend-py

python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell
.venv\Scripts\Activate.ps1

pip install -r requirements.txt

# Install the Playwright browser binaries
playwright install chromium     # or: playwright install firefox
```

---

## 🔑 Finding your browser profile path

The scraper reuses your existing logged-in browser profile so it can access your watchlists without requiring you to log in again.

### Chrome

| OS      | Default path                                                                 |
|---------|------------------------------------------------------------------------------|
| macOS   | `~/Library/Application Support/Google/Chrome/Default`                       |
| Linux   | `~/.config/google-chrome/Default`                                           |
| Windows | `C:\Users\<YOUR_USER>\AppData\Local\Google\Chrome\User Data\Default`        |

### Microsoft Edge

| OS      | Default path                                                                              |
|---------|-------------------------------------------------------------------------------------------|
| macOS   | `~/Library/Application Support/Microsoft Edge/Default`                                   |
| Linux   | `~/.config/microsoft-edge/Default`                                                       |
| Windows | `C:\Users\<YOUR_USER>\AppData\Local\Microsoft\Edge\User Data\Default`                   |

> **Tip (Chrome/Edge):** Navigate to `chrome://version` (or `edge://version`) and look for the **"Profile Path"** field.  Use that exact path.

> **Important:** Close the browser **before** running the scraper, or Playwright will not be able to attach to the profile.

---

## 🕷️ Running the scraper

```bash
# Scrape both Google Watchlist and IMDb Watchlist
python scraper.py --user-data-dir "/path/to/your/profile"

# Scrape only IMDb, providing your IMDb user ID explicitly
python scraper.py --user-data-dir "/path/to/profile" --no-google --imdb-user-id ur12345678

# Use Firefox instead of Chromium
python scraper.py --browser firefox --user-data-dir "/path/to/firefox/profile"

# Store movies in a custom database file
python scraper.py --user-data-dir "/path/to/profile" --db my_movies.db
```

The scraper opens a visible (non-headless) browser window so you can observe what is happening and intervene if a CAPTCHA or consent dialog appears.

### Finding your IMDb user ID

1. Log in to [imdb.com](https://www.imdb.com).
2. Click your avatar → **Your Watchlist**.
3. The URL will be `https://www.imdb.com/user/ur########/watchlist`.  The `ur########` part is your user ID.

---

## 🎬 Running the Streamlit app

```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

By default the app reads from `watchlist.db` in the current directory.  If you scraped into a custom file with `--db`, point the app at it with the `WATCHLIST_DB` environment variable:

```bash
WATCHLIST_DB=my_movies.db streamlit run app.py
# Windows PowerShell
$env:WATCHLIST_DB="my_movies.db"; streamlit run app.py
```

### Page 1 – My Watchlist

- Displays all synced movies in a searchable table.
- Shows aggregate metrics (total count, average rating, sources).
- Lets you delete individual movies from the database.

### Page 2 – Recommend

- Filter by **Genre / Mood** (multi-select from genres in your watchlist).
- Filter by **Rating range** (slider from 0 to 10).
- Filter by **Maximum length** (short / medium / long / epic).
- Displays the **top 3 matching movies** ranked by rating.

---

## 🧪 Running the tests

```bash
pytest test_app.py -v
```

The test suite covers:

| Category                  | What is tested                                                                |
|---------------------------|-------------------------------------------------------------------------------|
| `init_db`                 | Table creation, idempotency                                                   |
| `upsert_movie`            | Insert, update, duplicate prevention (same & different sources)               |
| `get_all_movies`          | Empty DB, field completeness, alphabetical ordering                            |
| `filter_movies`           | Min/max rating, max length, single/multiple genres, combined filters, top-3   |
| `delete_movie`            | Deletion by ID, no-op for missing ID, only correct row deleted                |
| `_parse_runtime`          | Hours+minutes, hours only, minutes, bare integers, edge cases                 |
| `_parse_rating`           | Fraction strings, bare floats, integers, empty/None                           |

---

## 🕐 Scheduling automatic syncs

### macOS / Linux – `cron`

Edit your crontab with `crontab -e` and add:

```cron
# Sync watchlists every day at 08:00
0 8 * * * /path/to/recommend-py/.venv/bin/python /path/to/recommend-py/scraper.py \
    --user-data-dir "/path/to/your/browser/profile" \
    --headless \
    >> /path/to/recommend-py/scraper.log 2>&1
```

> Note: Pass `--headless` so the browser runs without a visible UI in a cron context.

### Windows – Task Scheduler

1. Open **Task Scheduler** → **Create Basic Task**.
2. Set the trigger to **Daily** at your preferred time.
3. Action: **Start a Program**
   - Program: `C:\path\to\recommend-py\.venv\Scripts\python.exe`
   - Arguments: `C:\path\to\recommend-py\scraper.py --user-data-dir "C:\path\to\profile" --headless`
   - Start in: `C:\path\to\recommend-py`

---

## 🛠️ Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `playwright._impl._errors.Error: … user data directory is already in use` | Browser is still open | Close Chrome / Edge / Firefox first |
| Scraper opens browser but watchlist is empty | Not logged in, or wrong profile path | Verify the profile path; open the profile manually and log in |
| IMDb redirects to sign-in page | Cookies expired in the profile | Open the browser manually, sign in again, then re-run the scraper |
| `ModuleNotFoundError: No module named 'playwright'` | Dependencies not installed | Run `pip install -r requirements.txt && playwright install chromium` |

---

## 📄 License

MIT