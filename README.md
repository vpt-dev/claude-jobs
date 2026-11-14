# claude-jobs

Internships and new-grad roles in tech, data and quant across the US, UK and Canada, published as a static site at
https://claude-jobs.pages.dev (Cloudflare Pages serves the `site/` folder on every push to `main`).

## What runs

`bash refresh.sh auto` does everything and publishes. It is run daily by a scheduled job on the owner's Mac, and by
`.github/workflows/crawl.yml` when GitHub Actions is available. `quick` skips the hour-long read of employer boards;
`auto` does that read when the last one is over six days old or was made by an older version of the crawler.

1. `tests/run.py` — the regression suite. A failing suite stops the run before anything is touched.
2. `pipeline/fetch.sh` — downloads the public lists. A failed or cut-short download keeps the previous copy and is reported.
3. `crawl.py` — reads employer boards (Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Workday) listed in `seeds.json`.
   Boards that fail keep their previous roles for up to 14 days. `reed.py` adds UK roles when a Reed key is present.
4. `pipeline/build.py` — one row per vacancy (see below), written to the work folder with a health summary.
5. `probe.py` — looks for the employer boards behind roles known only from lists.
6. `pipeline/targets.py` and `check_postings.py` — read postings that have no stored evidence, or whose evidence is over
   about ten days old. Sites that rule out automated reading (`identity.NO_READ`) are never opened.
7. `pipeline/elig_build.py` — judges every UK, Canada and unplaced internship against `profile.json`.
8. `pipeline/assemble.py` and `tests/page_check.js` — write `site/` and run the page's own script against it. A dataset
   that shrank sharply, or a page that fails its checks, is not published.

## The rules the code keeps

- **One vacancy, one row.** `identity.py` keys a vacancy by its requisition on the employer's system. The same title in
  two cities stays two rows with two links. A list entry that links through the list's own site joins an employer row
  only when employer, title, type and town agree.
- **Unknown stays unknown.** `places.py` returns `??` for a location it cannot place; such roles are kept and labelled.
  A posting that was not read is "unknown", never a match and never a mismatch.
- **Four states, with evidence.** `eligibility.py` extracts whole requirement sentences and returns match, conditional,
  unknown or mismatch, with the sentence it rests on. How well the posting was read (full, partial, none) is separate.
- **Nothing hidden silently.** The For you tab's place and field chips only choose what to show; everything left out is
  counted with its reason.

## Files

| Path | What it holds |
|---|---|
| `profile.json` | The candidate's dated facts. Edit this when they change; the target season and year live here too. |
| `data/ats_jobs.json`, `data/reed_jobs.json` | Last good read of employer boards and Reed. |
| `data/evidence.json` | Requirement sentences per posting, with when and how well each was read. |
| `data/links.json` | Short list links traced to the employer's posting. |
| `data/first_seen.json` | The day each role first appeared here ("new" on the site means this). |
| `data/sources.json` | The usual number of listings per source, for spotting a source that has broken. |
| `data/manual.json` | Roles added by hand. |
| `apps_script/Code.gs` | The Google Sheet backend for the tracker. Deployed by hand; holds no secrets in this repo. |

## Tests

`python3 tests/run.py` runs the eligibility cases (`tests/eligibility_cases.json`: designed sentences plus real excerpts
labelled by hand) and the place, identity, text and crawler tests. Add a case whenever a posting is judged wrongly.
`node tests/page_check.js site` checks a built site. Python 3.9 or later; no packages to install.

## Keys

No key belongs in this repository. The Reed key is read from the file named by `REED_KEY_FILE` (default `../reed_key.txt`)
or the `REED_API_KEY` secret in Actions. `.gitignore` excludes key files, but a zip of the surrounding folder does not.
