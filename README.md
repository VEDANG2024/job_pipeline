# Job Discovery + Application-Package Pipeline

Daily pipeline that finds postings matching your criteria, scores each
one against your resume, tailors the resume when the match is weak,
and logs everything to a spreadsheet. **Total cost to run this: $0** —
see *Cost breakdown* below for exactly why. This is **phase 1** of the
full system — it does not click "Apply" anywhere yet (see *What this
does NOT do yet*, and *Roadmap* for what's next).

## Cost breakdown (why this is genuinely free)

| Piece | What it costs | Why |
|---|---|---|
| Adzuna (discovery) | $0 | Free tier, no card, ~1,000 calls/month |
| RemoteOK / We Work Remotely | $0 | Public feeds, no signup at all |
| JobSpy (LinkedIn/Indeed/Glassdoor/Naukri/Google) | $0 | Open-source library, no API cost |
| Gemini (resume tailoring) | $0 | Google's free tier — no card, as long as you never enable billing on that project |
| Hosting (daily automated runs) | $0 | GitHub Actions free tier (below) |
| LaTeX / PDF compilation | $0 | Runs on GitHub's own runner, nothing to install yourself |

The one thing to watch: if you ever *enable billing* on the Google
Cloud project behind your Gemini key (even to try a paid model),
Google removes that project's free tier entirely. Don't enable billing
and this stays $0 indefinitely.

## What it does — and what it deliberately does not

1. **Discovers** postings — no company list to maintain, everything is
   driven by keyword + location:
   - **Adzuna** (primary source) — a free, official aggregator API that
     already crawls 30+ sources including Workday, Indeed, and
     Glassdoor postings, searched by role + location rather than by
     company. This is what covers "every company" automatically.
   - **RemoteOK** (public JSON) and **We Work Remotely** (RSS)
   - Best-effort: **LinkedIn / Indeed / Glassdoor / Naukri / Google**,
     via the `python-jobspy` library (read-only discovery, also
     keyword+location based — see caveats below)
   - *Optional/advanced:* Greenhouse & Lever public job-board APIs for
     specific companies you explicitly pin in `config.yaml` — this is
     the only part of the system that's company-specific, because
     those two ATSs have no "search every company" endpoint to query
     instead. Left empty by default; you never have to touch it.
2. **Classifies & scores** each posting: Analyst vs SWE, years-of-experience
   band, location priority, internship stipend floor, company tier.
   - **Ahmedabad postings are never silently dropped** — if one fails a
     soft filter (e.g. asks for 5 years), it's kept and flagged
     `mandatory_review` instead of being discarded.
   - Internship postings with a stated stipend below ₹30,000/month are
     dropped. If no stipend is stated, it's kept for you to check.
3. **Dedupes** against `data/jobs.db` so re-runs only surface genuinely
   new postings.
4. **Prepares an application package** for each new match:
   - Scores the JD against the matching resume (`ats_score.py` — a
     keyword-overlap scorer, same style as most real ATS keyword
     matching)
   - If the score is below 85 (`filters.ats_tailor_threshold` in
     `config.yaml`), tailors the LaTeX via **Gemini** (free tier,
     `GEMINI_API_KEY`) and recompiles a job-specific PDF
   - **Tailoring is truthfulness-constrained**: it can reorder the
     skills list, tweak phrasing to mirror the JD's terminology, and
     re-emphasize things that are already true — it cannot invent an
     employer, skill, metric, or experience that isn't already in your
     resume. Every tailoring pass writes a diff to `resumes/diffs/` so
     you can spot-check exactly what changed.
5. **Logs every job** to `application_log.csv` — company, role, JD
   brief, matched/missing skills, ATS score, which resume was used,
   whether it was tailored, and a status.
6. **Auto-applies to Greenhouse and Lever postings, and only those
   two.** `apply_bot.py` fills the application form (name, email,
   phone, LinkedIn, resume upload) using Playwright, screenshots the
   result, and by default (`apply.dry_run: true`) stops there — Submit
   is never clicked. Even with `dry_run: false`, a required field it
   couldn't fill or a resume that failed to attach blocks submission
   outright, regardless of the setting. Screenshots land in
   `applications/screenshots/`; review several real ones against the
   actual posting before ever flipping `dry_run` to `false`.

**Does not touch LinkedIn, Naukri, Indeed, Glassdoor, Wellfound, or
Workday for submission**, on purpose:
- LinkedIn/Naukri/Wellfound need *your* logged-in session to apply as
  you — meaning storing your credentials somewhere this system can
  reach them, on top of the real account-restriction risk automating
  those platforms carries (see the earlier conversation, and this
  project's own Google Cloud suspension for a related reason — an
  automated system correctly detecting a bot-like pattern isn't
  hypothetical, it already happened here once).
- Workday forms vary too much per company to generalize the way
  Greenhouse/Lever's shared template allows; a specific employer's
  Workday flow could be built as its own targeted piece of work, but
  a generic "any Workday posting" bot isn't reliable enough to trust
  with a real submission.
- WWR has no application system of its own to automate — it redirects
  to whatever the company actually uses, which `ats_detect.py` already
  resolves and classifies.

For everything in that second group, the log (`application_log.csv`)
is the tool: it's fully prepared (scored, tailored resume ready, ATS
identified) and just needs your click.

`status` in the log is `package_ready` for auto-apply candidates
before `apply.enabled` runs, then becomes one of `ready_dry_run`,
`submitted`, or `blocked_incomplete` once it does. Everything else
tops out at `package_ready` — that's not a gap to fix, it's the
boundary described above.

## Do I need to give it my LinkedIn/Naukri password?

**No, not for anything this pipeline does today.** Discovery (Adzuna,
RemoteOK, WWR, Greenhouse, Lever, and the JobSpy layer) all read public
pages — none of it logs in as you.

Credentials would only come into play if you wanted actual submission
on LinkedIn or Naukri automated, since posting an application there as
you requires your logged-in session. I'm deliberately not building
that: storing your password (or session cookies) in this system is a
real security exposure if the repo or a secret ever leaked, on top of
the account-ban risk already covered above. If you want speed on those
two platforms specifically, the safer trade is the human-review batch
in the roadmap below — pre-filled, one click each, still fast.

## Which of today's matches can actually be applied to directly?

Every new job now gets an `ats` field (visible in `application_log.csv`
and `data/new_matches_<date>.csv`), telling you exactly what it landed
on:
- **`greenhouse` / `lever`** — public, no-login application systems.
  These get fully auto-applied to (dry-run by default — see above).
- **`linkedin` / `naukri` / `indeed` / `glassdoor`** — need your login;
  these go in the log fully prepared, ready for your one-click review.
- **`workday` / `company_site`** — per-company forms, too inconsistent
  to generalize safely; also logged fully prepared, not auto-submitted.

`resolve_final_url()` follows Adzuna's tracking links to find the real
destination — this is what makes the classification accurate even
though Adzuna itself doesn't tell you which ATS a listing uses.

## One-time setup

### 1. Get a free Adzuna key
Sign up at https://developer.adzuna.com/ — instant App ID + App Key,
no card. This is the primary discovery source.

### 2. Get a free Gemini key (for resume tailoring)
1. Go to https://aistudio.google.com/apikey and create a key — no
   card required.
2. **Do not enable billing** on the Google Cloud project behind that
   key. The free tier (Gemini Flash / Flash-Lite, ~1,500 requests/day)
   only applies while billing is off; enabling it removes the free
   tier for that project entirely, per Google's own docs.
3. Without this key, jobs scoring below the ATS threshold just fall
   back to your base resume and get logged as `needs_manual_tailor`
   instead — the rest of the pipeline still runs fine.

### 3. Put this project on GitHub (free, private repo)
1. Create a **private** repository (private matters here — this repo
   will contain your resume and job-search data).
2. Push this project to it:
   ```bash
   cd job_pipeline
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/<your-username>/<repo-name>.git
   git push -u origin main
   ```

### 4. Add your keys as GitHub Secrets (never commit real keys to the repo)
In the repo: **Settings → Secrets and variables → Actions → New
repository secret**. Add three:
- `ADZUNA_APP_ID`
- `ADZUNA_APP_KEY`
- `GEMINI_API_KEY`

### 5. That's it — the workflow is already in the project
`.github/workflows/daily-job-search.yml` is already set up to run
twice daily (8:00 AM and 5:30 PM IST) on GitHub's free hosted runners,
install everything it needs fresh each time, run the pipeline, and
commit the updated database/logs/tailored resumes back to the repo so
state persists between runs.

You can also trigger it manually any time: repo → **Actions** tab →
**Daily Job Search** → **Run workflow**.

## Configuration
Edit `config.yaml`:
- `adzuna.searches` — the keyword+location combinations to search.
  Already seeded with Analyst/SWE × Ahmedabad/India. Add rows freely
  — just keep the total modest against the ~1,000 calls/month free tier.
- `filters` — experience band, internship stipend floor, Ahmedabad
  aliases, ATS tailoring threshold.
- `resumes` — paths to your two resumes (already pointed at the ones
  in `resumes/`).
- `tailoring.enabled` — **off by default.** Resume choice is a fast,
  free, local comparison (score the JD against both resumes, use
  whichever fits better) — no API call, so applying never waits on
  Gemini being available. Turn this on only if you want Gemini to
  rewrite the chosen resume on top of that when the fit score is low;
  given the free-tier quota already hit in production once, off is the
  more reliable default.
- `companies.greenhouse` / `companies.lever` — **optional, leave empty.**
  Only fill this in if you want to explicitly pin a specific company
  for guaranteed coverage regardless of whether Adzuna/LinkedIn happen
  to index it.

## Checking on it day to day
Everything the workflow does is visible in the repo itself:
- **Actions tab** — see each run, whether it succeeded, and the full log
- `application_log.csv` — open in Excel/Google Sheets for the full list
- `data/new_matches_<date>.csv` — quick glance at what's new each run
- `resumes/tailored/*.pdf` and `resumes/diffs/*.diff` — what got
  tailored and exactly what changed
- `applications/screenshots/*.png` — what the Greenhouse/Lever auto-fill
  actually did to each form

## Running it locally (optional, for testing changes)
```bash
pip install -r requirements.txt --break-system-packages
playwright install --with-deps chromium
sudo apt-get install -y texlive-latex-base texlive-latex-extra \
    texlive-fonts-recommended texlive-fonts-extra
export ADZUNA_APP_ID="..."
export ADZUNA_APP_KEY="..."
export GEMINI_API_KEY="..."
python main.py
```

## Testing the logic without hitting live job boards
`tests/test_pipeline_offline.py` runs the whole scoring/filtering/
tailoring/logging logic against synthetic postings — useful for
checking your filters behave the way you want:
```bash
python tests/test_pipeline_offline.py
```
`tests/test_nan_safety.py`, `tests/test_gemini_budget.py`, and
`tests/test_apply_bot.py` are regression tests for real incidents/risks
this project has already hit or specifically guards against (a
pandas-NaN crash, the Gemini quota/suspension issue, and — critically —
`apply_bot.py` never submitting an incomplete application). Run them
after any change to `classify.py`, `db.py`, `ats_score.py`,
`spreadsheet_log.py`, `gemini_budget.py`, or `apply_bot.py`:
```bash
python tests/test_nan_safety.py
python tests/test_gemini_budget.py
python tests/test_apply_bot.py
```

## Known limitations to expect
- The `python-jobspy` layer (LinkedIn/Indeed/Glassdoor/Naukri/Google)
  is the most likely piece to get rate-limited or blocked, since
  GitHub's runner IPs are shared and not hard to detect. When it fails,
  it fails quietly and the rest of the pipeline still runs — Adzuna/
  RemoteOK/WWR aren't affected since those are legitimate public APIs,
  not scraping.
- Scheduled GitHub Actions workflows can occasionally fire a few
  minutes late during high platform load — not an issue for a daily
  job search, but worth knowing.
- If Google renames the free-tier Gemini model again, `tailor.py` will
  start erroring — set the `GEMINI_MODEL` secret/env var to whatever
  https://ai.google.dev/gemini-api/docs/pricing currently lists as
  free-tier eligible.

## Incident: a suspended Google Cloud project, and what changed

On the first run after the Gemini fix, the pipeline hit Google's
**daily** free-tier quota for `gemini-3.6-flash` (20 requests/day per
project/model — tighter than the commonly-assumed per-minute limits on
Flash models). Instead of stopping there, it kept firing a fresh
request for every next job anyway, got `429 RESOURCE_EXHAUSTED`
repeatedly in a tight loop, and ignored the API's own `retryDelay`
hints. That pattern — rapid, repeated requests against an exhausted
quota — got the Google Cloud project suspended for "repeated Terms of
Service violations."

**What changed as a result:**
- `gemini_budget.py` — a hard, persisted daily cap (15, with headroom
  under Google's 20). The instant a real 429 comes back, it's recorded
  immediately and every subsequent job — this run or any run later
  today — skips Gemini entirely without even attempting a call. This
  makes the hammering pattern structurally impossible, not just
  less likely. It's also **fail-safe, not fail-open**: if the budget
  file is missing, that's treated as a legitimate first-ever run
  (fresh budget); if the file exists but is corrupted or has an
  implausible shape, it's treated as exhausted rather than silently
  handing out a budget that can't be verified. Every run also prints
  a one-line budget banner (`Gemini budget: 4/15 used today, 11
  remaining.`) right at the top of the log, so this state is never
  buried again.
- `pipeline.max_prepare_per_run` (config.yaml) is now actually
  enforced in `main.py` — only the top-scoring N new jobs get full
  processing (ATS detection + tailoring) per run; the rest are logged
  with `status = discovered_not_prepared` and the base resume, with no
  network or Gemini calls at all.
- The tailoring prompt now explicitly requires escaping LaTeX special
  characters (a JD's raw `&` had been breaking compilation on one job
  — a wasted call against an already-scarce daily budget).
- The workflow now runs Python unbuffered (`python -u`), so log
  timestamps reflect what actually happened when — the original
  incident log was confusing partly because Python's default stdout
  buffering made 13 minutes of real work look like it happened in one
  burst at the end.

**If your project got suspended:** Google's suspension notice includes
a link to request an appeal (Cloud Console → the suspended project's
banner). Worth filing — it costs nothing — but appeals aren't fast or
guaranteed; anecdotally some go unanswered for weeks. In parallel, you
can create a new Google Cloud project and a fresh Gemini API key —
safe to do now that the code above prevents the pattern that caused
the suspension in the first place.

## Roadmap (next builds, in a sensible order)
1. **Human-review speedup** for LinkedIn/Naukri/Indeed/Glassdoor/
   Workday/company sites — right now the log is the tool; a small
   local script that opens each `ready_dry_run`-adjacent job's URL in
   order would shave time off the click-through without touching any
   of the automation boundaries above.
2. **Cold email sender** — Gmail API on vedangtrivediworks@gmail.com,
   rate-capped and personalized, pulling contacts via Hunter.io/Apollo.io
   (both have free tiers too).
3. **A specific Workday employer's flow** — if you name one you care
   about, that's a tractable, testable target; a generic "any Workday
   site" bot is not.
