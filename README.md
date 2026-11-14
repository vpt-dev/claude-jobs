# Early-career tech & quant job board

Private tool that collects internships and new grad roles in the US, UK and Canada.

- `seeds.json`: 2,060 employer job boards (Workday, Greenhouse, Ashby, Lever, Workable, SmartRecruiters), derived from links in public GitHub job lists.
- `crawl.py`: reads each board's public endpoint, keeps early-career tech roles, extracts pay where stated. Standard library only.
- `.github/workflows/crawl.yml`: runs the crawl daily and commits `data/ats_jobs.json`.
- `pipeline/`: builds the combined dataset and the site page from the GitHub lists.

Status: `crawl.py` has not yet been run against live boards. Expect to fix field names on the first run.
Not included by design: LinkedIn, Indeed (their terms forbid scraping) and Zapply's list (its terms forbid re-aggregation).
