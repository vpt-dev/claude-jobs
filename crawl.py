#!/usr/bin/env python3
"""Crawl employer hiring systems listed in seeds.json and write ats_jobs.json.

Reads each employer's public job-board endpoint (the one its own careers page calls).
Standard library only. Usage: python3 crawl.py seeds.json ats_jobs.json [--limit N]

Keeps early-career roles (internships, new grad, junior) located in the US, UK or Canada.
Is polite: one request at a time per host, a pause between requests, an honest User-Agent.
"""
import concurrent.futures as cf
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request

UA = "early-career-jobs-board/0.1 (personal job search tool)"
TIMEOUT = 25
PAUSE = 0.4  # seconds between requests to the same host
EARLY = re.compile(r"\bintern(ship)?s?\b|co-?op\b|new grad|graduate|early career|entry[- ]level|university|campus|junior|\bjr\b|placement|apprentice|associate (software|engineer)|\b20(26|27) (start|grad)", re.I)
SENIOR = re.compile(r"\bsenior\b|\bsr\b|staff|principal|director|manager|\blead\b|head of|\bvp\b|architect|\bII+\b|\b[2-9]\b", re.I)
TECH = re.compile(r"software|engineer|developer|data|machine learning|\bml\b|\bai\b|quant|trading|trader|research|statistic|analyst|scientist|hardware|firmware|fpga|security|devops|\bsre\b|product manager|actuar", re.I)


def get(url, body=None):
    headers = {"User-Agent": UA, "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def text(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(s or ""))).strip()


PAY = re.compile(r"([$£]|C\$|CA\$|USD|GBP|CAD)\s?(\d{2,3}(?:,\d{3})?(?:\.\d+)?)\s?(k)?(?:\s?(?:-|–|—|to)\s?(?:[$£]|C\$|CA\$)?\s?(\d{2,3}(?:,\d{3})?(?:\.\d+)?)\s?(k)?)?\s?(?:(?:per|an|a|/)\s?(hour|hr|year|yr|annum|month))?", re.I)


def find_pay(s):
    """Return {min,max,cur,period} from free text, or None. Only accepts plausible pay figures."""
    for m in PAY.finditer(s or ""):
        cur = {"$": "USD", "£": "GBP", "USD": "USD", "GBP": "GBP", "CAD": "CAD"}.get(m.group(1).upper(), "CAD")
        lo = float(m.group(2).replace(",", "")) * (1000 if m.group(3) else 1)
        hi = float(m.group(4).replace(",", "")) * (1000 if m.group(5) else 1) if m.group(4) else lo
        unit = (m.group(6) or "").lower()
        period = "hour" if unit in ("hour", "hr") else "month" if unit == "month" else "year"
        if re.match(r"\s?(million|billion|bn|mm?)\b", (s or "")[m.end():m.end() + 9], re.I):
            continue  # funding or revenue, not pay
        if not unit and lo < 15000:
            continue  # a bare small number is too ambiguous to call pay
        if period == "year" and not (15000 <= lo <= 900000):
            continue
        if period == "hour" and not (8 <= lo <= 300):
            continue
        return {"min": lo, "max": max(lo, hi), "cur": cur, "period": period}
    return None


ELIG = [
    ("penultimate_only", r"penultimate[- ]year|second[- ]to[- ]last year|one year (left|remaining)|at least (one|1) (more )?(year|semester|term) (left|remaining)|rising (junior|senior)"),
    ("grad_2028_or_later", r"(graduat\w+|graduation|class of|completing your degree)[^.]{0,60}\b20(28|29)\b"),
    ("must_return_to_study", r"return(ing)? to (school|university|college|your stud\w+|full[- ]time (study|education|studies)|a degree)|must be returning|returning student|continuing (your )?(studies|education) after"),
    ("must_be_enrolled", r"(currently )?enrol+ed in (a|an|your)|currently (pursuing|studying|completing)|active(ly)? (student|enrol+ment)|co-?op (program|term|student)"),
    ("final_year_ok", r"final[- ]year|last year of (your )?(study|studies|degree)|penultimate or final|graduat\w+[^.]{0,40}\b2027\b|class of 2027|recent(ly)? graduat\w+|new graduates? (are )?(also )?welcome"),
    ("masters_ok", r"master'?s|\bmsc\b|\bmeng\b|postgraduate|graduate student"),
]
ELIG = [(k, re.compile(p, re.I)) for k, p in ELIG]


def eligibility(desc):
    """Return year-of-study signals found in a posting, with one short excerpt per signal."""
    out = {}
    for key, rx in ELIG:
        m = rx.search(desc or "")
        if m:
            a, b = max(0, m.start() - 70), min(len(desc), m.end() + 70)
            out[key] = desc[a:b].strip()
    return out


def job(seed, title, locs, url, posted="", desc="", pay=None):
    return {"company": seed["company"], "title": title.strip(), "locations": [l for l in locs if l], "url": url,
            "posted": (posted or "")[:10], "pay": pay or find_pay(desc), "elig": eligibility(desc),
            "ats": seed["ats"], "board": seed["board"]}


def greenhouse(s):
    d = get(f"https://boards-api.greenhouse.io/v1/boards/{s['board']}/jobs?content=true&pay_transparency=true")
    out = []
    for j in d.get("jobs", []):
        pay = None
        for r in j.get("pay_input_ranges") or []:
            if r.get("min_cents"):
                pay = {"min": r["min_cents"] / 100, "max": (r.get("max_cents") or r["min_cents"]) / 100,
                       "cur": r.get("currency_type", "USD"), "period": "hour" if r["min_cents"] < 30000 else "year"}
                break
        out.append(job(s, j.get("title", ""), [(j.get("location") or {}).get("name", "")], j.get("absolute_url", ""),
                       j.get("first_published") or j.get("updated_at"), text(j.get("content")), pay))
    return out


def lever(s):
    out = []
    for j in get(f"https://api.lever.co/v0/postings/{s['board']}?mode=json"):
        c = j.get("categories") or {}
        sr = j.get("salaryRange") or {}
        pay = {"min": sr["min"], "max": sr.get("max", sr["min"]), "cur": sr.get("currency", "USD"),
               "period": "hour" if "hour" in (sr.get("interval") or "") else "year"} if sr.get("min") else None
        posted = time.strftime("%Y-%m-%d", time.gmtime(j["createdAt"] / 1000)) if j.get("createdAt") else ""
        out.append(job(s, j.get("text", ""), c.get("allLocations") or [c.get("location", "")], j.get("hostedUrl", ""),
                       posted, (j.get("descriptionPlain") or "") + " " + " ".join(text(x.get("content", "")) for x in j.get("lists") or []) + " " + text(j.get("additionalPlain", "")), pay))
    return out


def ashby(s):
    d = get(f"https://api.ashbyhq.com/posting-api/job-board/{s['board']}?includeCompensation=true")
    out = []
    for j in d.get("jobs", []):
        locs = [j.get("location", "")] + [x.get("location", "") for x in j.get("secondaryLocations") or []]
        comp = (j.get("compensation") or {}).get("compensationTierSummary") or ""
        out.append(job(s, j.get("title", ""), locs, j.get("jobUrl", ""), j.get("publishedAt"),
                       comp + " " + (j.get("descriptionPlain") or "")))
    return out


def smartrecruiters(s):
    out, off = [], 0
    while True:
        d = get(f"https://api.smartrecruiters.com/v1/companies/{s['board']}/postings?limit=100&offset={off}")
        for j in d.get("content", []):
            l = j.get("location") or {}
            loc = ", ".join(x for x in [l.get("city"), l.get("region"), (l.get("country") or "").upper()] if x)
            out.append(job(s, j.get("name", ""), [loc], f"https://jobs.smartrecruiters.com/{s['board']}/{j.get('id')}", j.get("releasedDate")))
        off += 100
        if off >= d.get("totalFound", 0) or off >= 2000:
            return out
        time.sleep(PAUSE)


def workable(s):
    d = get(f"https://apply.workable.com/api/v1/widget/accounts/{s['board']}?details=true")
    out = []
    for j in d.get("jobs", []):
        loc = ", ".join(x for x in [j.get("city"), j.get("state"), j.get("country")] if x)
        out.append(job(s, j.get("title", ""), [loc], j.get("url") or j.get("shortlink", ""), j.get("published_on"), text(j.get("description"))))
    return out


def workday(s):
    host, site = s["board"].split("/", 1)
    tenant = host.split(".")[0]
    base = f"https://{host}.myworkdayjobs.com"
    out, off = [], 0
    # Search for early-career terms so large employers do not need thousands of requests.
    for term in ("intern", "graduate", "new grad", "early career"):
        off = 0
        while off < 400:
            d = get(f"{base}/wday/cxs/{tenant}/{site}/jobs", {"appliedFacets": {}, "limit": 20, "offset": off, "searchText": term})
            posts = d.get("jobPostings", [])
            for j in posts:
                out.append(job(s, j.get("title", ""), [j.get("locationsText", "")], f"{base}/{site}{j.get('externalPath', '')}"))
            off += 20
            if len(posts) < 20:
                break
            time.sleep(PAUSE)
    return out


FETCH = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby, "smartrecruiters": smartrecruiters, "workable": workable, "workday": workday}
US = re.compile(r"\b(A[LKZR]|C[AOT]|DE|FL|GA|HI|I[DLNA]|K[SY]|LA|M[EDAINSOT]|N[EVHJMYCD]|O[HKR]|PA|RI|S[CD]|T[NX]|UT|V[TA]|W[AVIY]|DC)\b|United States|USA|\bUS\b|New York|San Francisco|Remote", re.I)
UK = re.compile(r"United Kingdom|\bUK\b|\bGB\b|England|Scotland|Wales|London|Manchester|Edinburgh|Cambridge, (UK|England)|Bristol|Belfast|Glasgow", re.I)
CA = re.compile(r"Canada|\b(ON|BC|QC|AB|MB|SK|NS|NB)\b|Toronto|Vancouver|Montr[eé]al|Ottawa|Waterloo|Calgary", re.I)


def countries(locs):
    s = " | ".join(locs)
    out = [c for c, rx in (("CA", CA), ("UK", UK)) if rx.search(s)]
    if US.search(s) and not (out and not re.search(r"United States|USA|\bUS\b", s)):
        out.append("US")
    return out


def run(seed):
    try:
        rows = FETCH[seed["ats"]](seed)
    except urllib.error.HTTPError as e:
        return seed, [], f"HTTP {e.code}"
    except Exception as e:  # network errors, bad JSON, changed shapes
        return seed, [], type(e).__name__
    keep, seen = [], set()
    for r in rows:
        t = r["title"]
        if not r["url"] or r["url"] in seen or not EARLY.search(t) or SENIOR.search(t) or not TECH.search(t):
            continue
        r["countries"] = countries(r["locations"])
        if not r["countries"]:
            continue
        r["type"] = "Internship" if re.search(r"intern|co-?op|placement", t, re.I) else "New Grad"
        seen.add(r["url"])
        keep.append(r)
    return seed, keep, ""


def progress(n, total, kept, failed, start):
    """Draw a one-line progress bar. On a terminal it redraws in place; in logs it prints every 100 boards."""
    tty = sys.stderr.isatty()
    if not tty and n % 100 and n != total:
        return
    done = int(30 * n / total)
    left = (time.time() - start) / n * (total - n)
    eta = f"{int(left // 60)}m {int(left % 60):02d}s left" if n < total else "finished"
    line = f"[{'#' * done}{'.' * (30 - done)}] {n}/{total} boards | {kept} kept | {failed} failed | {eta}"
    sys.stderr.write(("\r" + line + "   ") if tty else (line + "\n"))
    sys.stderr.flush()


def main():
    seeds = json.load(open(sys.argv[1]))
    if "--limit" in sys.argv:
        seeds = seeds[: int(sys.argv[sys.argv.index("--limit") + 1])]
    seeds = [s for s in seeds if s["ats"] in FETCH]
    jobs, errors = [], {}
    # Group by ATS host so each host sees a small, steady stream.
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        start, total = time.time(), len(seeds)
        for n, (seed, rows, err) in enumerate(ex.map(run, seeds), 1):
            jobs += rows
            if err:
                errors[f"{seed['ats']}:{seed['board']}"] = err
            progress(n, total, len(jobs), len(errors), start)
    sys.stderr.write("\n")
    json.dump({"fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "jobs": jobs, "errors": errors},
              open(sys.argv[2], "w"), ensure_ascii=False, indent=0)
    print(f"boards {len(seeds)} | failed {len(errors)} | early-career roles kept {len(jobs)} | with pay {sum(1 for j in jobs if j['pay'])} | with year-of-study wording {sum(1 for j in jobs if j['elig'])}")
    if seeds and len(errors) > len(seeds) * 0.5:
        sys.exit("More than half the boards failed; treat this run as broken.")


if __name__ == "__main__":
    main()
