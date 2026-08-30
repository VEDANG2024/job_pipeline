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

## What it does

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

## What this does NOT do yet

- It does not submit applications on LinkedIn/Naukri/Indeed/Glassdoor —
  automating that risks your account being flagged or restricted (see
  the conversation above for why). The plan is a human-gated
  "review and click" batch for these.
- It does not yet submit to Greenhouse/Lever/company sites — that's a
  safe automation target (public, no-login APIs) and is the natural
  next build.
- It does not send cold emails yet — also a natural next build, and
  the lowest-risk piece since it's your own outbound email.
- `status` in the log currently tops out at `package_ready` — it will
  become `applied` once the submission layer (above) actually fires.

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

## Running it locally (optional, for testing changes)
```bash
pip install -r requirements.txt --break-system-packages
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

## Roadmap (next builds, in a sensible order)
1. **Human-gated review batch** for LinkedIn/Naukri/Indeed/Glassdoor —
   pre-filled applications queued for a single daily approve-and-click
   pass, capped well under each site's flag thresholds. Also covers
   Adzuna-sourced Workday postings, since Adzuna's `redirect_url`
   ultimately lands on the employer's own application page.
2. **Cold email sender** — Gmail API on vedangtrivediworks@gmail.com,
   rate-capped and personalized, pulling contacts via Hunter.io/Apollo.io
   (both have free tiers too).
3. **Greenhouse/Lever auto-submit** — only relevant if you later pin
   specific companies in `config.yaml`; fully automatable since these
   are public, intentionally-scriptable APIs.
