# MMML Job Board

A self-hosted job board feature: an admin panel to add company careers pages,
a background worker that keeps job counts fresh every 24 hours, and a public
page that shows live "N open roles in India" per company.

## How it works

- **Add a source** in the admin panel (`/admin.html`) with a company name and
  its careers URL. It's immediately queued for a first sync.
- **URL type is detected automatically, nothing is hardcoded per company:**
  - `greenhouse.io` links → Greenhouse's public JSON API
    (`boards-api.greenhouse.io/v1/boards/{token}/jobs`).
  - `lever.co` links → Lever's public JSON API (`api.lever.co/v0/postings/{site}`).
  - `*.myworkdayjobs.com` links → Workday's internal CXS JSON API
    (`{tenant}.{cluster}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs`),
    paginated automatically.
  - `jobs.ashbyhq.com` links → Ashby's public posting API
    (`api.ashbyhq.com/posting-api/job-board/{board}`).
  - Anything else (Oracle HCM, Skima, an in-house board like TCS's, etc.) →
    the **custom Playwright scraper**, now a true last resort since the four
    providers above cover most of what companies actually use. It drives a
    real headless Chromium tab and combines three independent signals to
    land on a job count, *and* tries to extract the individual postings
    (title/location/department/URL) so the board can list real jobs, not
    just a number. This is the part that fixes the JPMorgan problem in your
    screenshot, where the page's own "300+ jobs" text is a *global* figure,
    not India's.
- **Two strict filters apply to every job, from every source type**, in one
  place (`app/scrapers/filters.py`), applied centrally in `tasks.py` so
  Greenhouse/Lever/Workday/Ashby/custom all behave identically:
  1. **Location** — the job must be based in India, or be a remote role
     (with some care taken not to count "Remote — US only" style listings as
     a match; see `EXCLUDED_REMOTE_REGIONS`).
  2. **Relevance** — the job must be finance or finance-adjacent, matched
     against title/department/team text (see `FINANCE_KEYWORDS`).

  For the custom scraper specifically: if individual postings couldn't be
  extracted (e.g. an unusually large or unusual page), the filters can't run
  per-job, so it falls back to the unfiltered heuristic count rather than
  silently reporting 0 — and flags `unfiltered_fallback_used: true` in that
  source's debug info so you know the number wasn't filtered.
- **Company-wise and total job lists**, not just counts: click a company's
  job count in the admin table, or a company card on the public board
  (`/board.html`), to see its actual filtered listings. The board's "All
  jobs" tab shows every filtered job across every company in one searchable
  list, via `GET /api/jobs`.
- **Sync all** re-syncs every source. **Every sync is chained sequentially**
  (`app/tasks.py::sync_all_sources`), and the Celery worker itself is run
  with `--concurrency=1`, so there is only ever one Chromium instance open at
  a time (used only for custom sources), regardless of how many companies
  are on the board.
- **Celery beat** re-runs sync-all automatically every 24 hours.

## The custom scraper's 3 detection methods

Implemented in `app/scrapers/custom.py`:

1. **Text match** — regex over the rendered page for phrases like
   `"3,241 jobs found"`. Weakest signal on its own (this is what breaks for
   global companies reporting a worldwide count), so it's only used as a
   fallback.
2. **Card count** — counts DOM elements matching a broad list of common
   job-card selector patterns (`[class*="job-card"]`, Workday's
   `data-automation-id*="job"`, etc.), i.e. counts how many times the
   repeating "one posting" element actually appears on the page.
3. **ID count** — counts unique `jobId` / `requisitionId` / `jobPostingId`
   style identifiers embedded in the page's HTML/hydration JSON — reliable
   for SPA boards where each posting has exactly one such ID.

The three numbers are stored per-source in `detection_debug` and shown to
the admin, and reconciled into one `job_count` favoring the two structural
signals (2 and 3) over the text claim. The reconciliation logic
(`_reconcile` in `custom.py`) is intentionally simple and commented so you
can tune it per-board if a specific company's page needs a different rule.

## Deploying (get a shareable public link)

This app has real infrastructure — an API, a Celery worker, Celery beat, and
Redis — so it can't run as a static hosted page. The included
`render.yaml` deploys the API, worker, beat, and a Postgres database on
[Render](https://render.com) in one shot via their **Blueprint** feature.

**About Redis:** Render caps free accounts at *one* free Redis/Key-Value
instance total (account-wide, not per-project) — if you hit "cannot have
more than 1 free tier Key Value instance," that's this cap, not a bug in the
blueprint. Rather than fight it, `render.yaml` doesn't create a Render Redis
at all; instead you point `REDIS_URL` at a free external Redis. Two minutes
on [Upstash](https://upstash.com) gets you one with no such cap:

1. Sign up at upstash.com (free, no card needed) → **Create Database** →
   pick any region → **Create**.
2. On the database's page, copy the connection string labeled something
   like "Redis Connect" / `ioredis` / `redis://` — it looks like
   `redis://default:xxxxxxxx@some-name.upstash.io:6379`.
3. Keep that value handy for step 3 below.

Then:

1. Push this folder to a new GitHub repo.
2. On Render: **New → Blueprint**, connect the repo. Render reads
   `render.yaml`. Because `REDIS_URL` is marked as a secret
   (`sync: false`), Render will prompt you to paste in a value for it —
   paste the same Upstash connection string for all three services (api,
   worker, beat) when asked.
3. Click **Apply**. First build takes a few minutes (Playwright's Chromium
   image is large).
4. Once live, Render gives `mmml-job-board-api` a public URL like
   `https://mmml-job-board-api.onrender.com`. Share:
   - `https://mmml-job-board-api.onrender.com/admin.html` — admin panel
   - `https://mmml-job-board-api.onrender.com/board.html` — public job board

**Worth knowing:**
- Every Render service in `render.yaml` is on the **free** plan, including
  Postgres. Free web/worker instances can be spun down or recycled by
  Render when idle, so the `beat` service's 24h auto-schedule may not fire
  reliably. If a sync looks stale, just open the admin panel and hit
  **Sync all** — that always works regardless of beat's state, since it
  queues the sync directly through the (also free) `api` service and Redis.
- Upstash's free tier has its own generous-but-real request cap; this app's
  traffic to Redis (Celery task queuing + a light DB-driven admin UI) is
  small enough that it's very unlikely to be an issue.
- Free Postgres on Render expires after 90 days unless upgraded — fine for
  testing/demoing, worth knowing if you're keeping this long-term.
- Railway and Fly.io both work too if you'd rather use those — same idea:
  one service per process (api / worker / beat), a Redis instance (Railway
  does offer its own free Redis add-on with a more generous cap), and
  `DATABASE_URL` / `REDIS_URL` env vars wired between them. The
  `docker-compose.yml` in this repo is the reference for what each service's
  start command should be.

## Running locally

```bash
cp .env.example .env
docker compose up --build
```

- Admin panel: http://localhost:8000/admin.html
- Public board: http://localhost:8000/board.html
- API docs: http://localhost:8000/docs

Without Docker:

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium --with-deps

# terminal 1
redis-server

# terminal 2
uvicorn app.main:app --reload

# terminal 3 — concurrency=1 is what enforces "one scrape at a time"
celery -A app.tasks.celery_app worker --loglevel=info --concurrency=1

# terminal 4 — drives the 24h auto-refresh
celery -A app.tasks.celery_app beat --loglevel=info
```

## Deploying

Any host that can run 3 long-lived processes (API, worker, beat) plus Redis
works: Railway, Render, Fly.io, or a plain VPS with `docker compose up -d`.
Swap `DATABASE_URL` in `.env` to Postgres for production — SQLite is fine for
development but not for concurrent writes at scale. Point your marketing
site's job board section at `GET /api/board` (and `GET
/api/companies/{id}/jobs` for the detail view), or just iframe
`/board.html`.

## A couple of things worth knowing before you rely on this in production

- **Scraping etiquette:** the custom scraper hits a real browser page once
  per company per 24h cycle, which is polite by scraping standards, but you
  should still check each target site's `robots.txt` and terms of service —
  some career sites (Workday tenants especially) explicitly disallow
  automated access, and a few rate-limit or block by user agent/IP after
  repeated visits.
- **The custom scraper is a heuristic, not a guarantee.** It's built to be
  right for the vast majority of common board layouts, and the admin panel
  surfaces the raw `detection_debug` numbers so you can spot-check a source
  that looks off and adjust its selector list or reconciliation rule if
  needed — there's no way to make a generic scraper 100% correct against a
  page format it hasn't seen before.
- **Greenhouse/Lever/Workday/Ashby job data is exact** since it comes from
  each provider's real API — only the custom scraper's count is a heuristic.
- **The two strict filters are keyword-based**, not a language model or a
  true geo-IP/role classifier. `FINANCE_KEYWORDS` and the remote/location
  logic in `app/scrapers/filters.py` are deliberately broad and easy to
  extend, but a role with an unusual title (e.g. "Numbers Person" instead of
  "Financial Analyst") won't match — tune the keyword lists there as you see
  real postings slip through or get excluded incorrectly.

## Project layout

```
app/
  main.py              FastAPI app, mounts frontend + routers
  tasks.py             Celery app + sync_source / sync_all_sources tasks;
                        applies the two strict filters centrally
  models.py, schemas.py, database.py, config.py
  scrapers/
    detector.py        URL type detection + India location matching
    filters.py           Strict filter 1 (India/remote) + filter 2 (finance)
    greenhouse.py         Greenhouse API handler
    lever.py               Lever API handler
    workday.py              Workday CXS API handler
    ashby.py                 Ashby posting API handler
    custom.py                 Playwright scraper (last resort): 3-signal
                               count detection + per-job extraction
  routers/
    admin.py            add/list/sync/delete sources
    public.py            public board + per-company job list + total job list
frontend/
  admin.html           Admin panel (add source, sync, table, sync all, job preview)
  board.html             Public-facing job board (by-company + all-jobs tabs)
docker-compose.yml       redis + api + worker(-c 1) + beat
Dockerfile                Playwright's official Python image (chromium preinstalled)
```
