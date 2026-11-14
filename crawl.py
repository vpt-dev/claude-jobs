#!/usr/bin/env python3
"""Read early-career roles from the employer job boards listed in seeds.json.

Usage: python3 crawl.py seeds.json ats_jobs.json [--previous OLD.json] [--limit N]

Uses each employer's public job-board endpoint (the one its own careers page calls). Standard
library only. Polite: a pause between requests to a host, a few boards at a time, an honest
User-Agent.

What is kept: internships, placements, graduate and junior technology roles in the UK, Canada
or the US, plus roles whose location cannot be worked out (kept as unknown, never guessed).
For each kept role outside the US the requirement sentences of the posting are stored, so
eligibility is judged from what the posting says.

--previous  rows from the last run are carried forward for any board that fails this time,
            so a board being down is not mistaken for all its roles closing.
--limit     try only the first N boards; the result goes to "<out>.partial", never the real file.
"""
import concurrent.futures as cf
import datetime
import html
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.request

import eligibility as E
import places

UA = "early-career-jobs-board/0.1 (personal job search tool)"
TIMEOUT = 25
PAUSE = 0.4       # seconds between requests to the same host
STALE_DAYS = 14   # how long a failed board's last known rows are kept
# Raise this when the filters or stored fields change, so the next automatic refresh re-crawls every board.
CRAWL_VERSION = 3

INTERN = re.compile(r"\bintern(ship)?s?\b|co-?op\b|placement|summer (analyst|associate|engineer|developer|technolog\w*|student|program(me)?|scheme)|"
                    r"year in industry|off[- ]?cycle|spring (week|insight)|insight (week|program(me)?|day)|thesis|stagiaire|\bstage (en|de|d')|"
                    r"working student|werkstudent|vacation (scheme|placement|student)|"
                    r"\bstudents?\b(?! (success|services?|affairs|recruit\w*|loans?|advis\w*|support|experience|life|engagement|accounts?|financ\w*|housing|union|outcomes|records))", re.I)
EARLY = re.compile(INTERN.pattern + r"|new grad|graduate|early career|entry[- ]level|university|campus|junior|\bjr\b|apprentice|trainee|"
                   r"associate (software|engineer|product manager)|\bapm\b|\b20(26|27) (start|grad)", re.I)
# Seniority words. Not applied to explicit internship titles: "Product Manager Intern" and
# "Software Engineer Intern - 4 months" are internships.
SENIOR = re.compile(r"\bsenior\b|\bsr\.?\b|\bstaff\b|principal|director|(?<!product )(?<!program )(?<!project )\bmanager\b|\blead\b|head of|\bvp\b|"
                    r"architect|\b(II|III|IV)\b|\b(engineer|developer|analyst|scientist|designer|associate|level|grade) [2-5]\b|\b[2-9]\+ years", re.I)
TECH = re.compile(r"software|engineer|developer|data|machine learning|\bml\b|\bai\b|quant|trading|trader|research|statistic|analyst|scientist|hardware|"
                  r"firmware|fpga|security|cyber|devops|\bsre\b|product (manager|management|owner|analyst|design)|actuar|\bit\b|information technology|"
                  r"technolog|technical|\bqa\b|quality assurance|\btest(ing|er)?\b|\bux\b|\bui\b|cloud|network|systems?\b|infrastructure|\bweb\b|mobile|"
                  r"digital|comput|programm|automation|robot|analytics|business intelligence|platform|solutions (engineer|architect)|electronic|electrical|"
                  r"embedded|semiconductor|mathemat|physics|informati(cs|que)|logiciel|d[ée]veloppeu|donn[ée]es", re.I)


def wanted(title):
    """Whether a title is an early-career technology role."""
    if not EARLY.search(title) or not TECH.search(title):
        return False
    return bool(INTERN.search(title)) or not SENIOR.search(title)


def get(url, body=None, tries=3):
    """Fetch JSON. Retries when the server is busy or sends a broken reply; a missing board (404) is not retried."""
    headers = {"User-Agent": UA, "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or attempt == tries - 1:
                raise
        except (json.JSONDecodeError, urllib.error.URLError, socket.timeout, ConnectionError):
            if attempt == tries - 1:
                raise
        time.sleep(2 + 4 * attempt)


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


def job(seed, title, locs, url, posted="", desc="", pay=None, hints=()):
    """One posting as read from a board. `desc` is the raw description; it is reduced to requirement sentences later."""
    return {"company": seed["company"], "title": (title or "").strip(), "locations": [l for l in locs if l], "url": url,
            "posted": (posted or "")[:10], "pay": pay, "ats": seed["ats"], "board": seed["board"],
            "hints": [h for h in hints if h], "_desc": desc or ""}


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
        offices = [o.get("location") or o.get("name") for o in j.get("offices") or []]
        out.append(job(s, j.get("title", ""), [(j.get("location") or {}).get("name", "")], j.get("absolute_url", ""),
                       j.get("first_published") or j.get("updated_at"), html.unescape(j.get("content") or ""), pay, hints=offices))
    return out


def lever(s):
    out = []
    for j in get(f"https://api.lever.co/v0/postings/{s['board']}?mode=json"):
        c = j.get("categories") or {}
        sr = j.get("salaryRange") or {}
        pay = {"min": sr["min"], "max": sr.get("max", sr["min"]), "cur": sr.get("currency", "USD"),
               "period": "hour" if "hour" in (sr.get("interval") or "") else "year"} if sr.get("min") else None
        posted = time.strftime("%Y-%m-%d", time.gmtime(j["createdAt"] / 1000)) if j.get("createdAt") else ""
        desc = "\n".join([j.get("description") or j.get("descriptionPlain") or ""]
                         + [(x.get("text") or "") + "\n" + (x.get("content") or "") for x in j.get("lists") or []]
                         + [j.get("additional") or j.get("additionalPlain") or ""])
        out.append(job(s, j.get("text", ""), c.get("allLocations") or [c.get("location", "")], j.get("hostedUrl", ""), posted, desc, pay,
                       hints=["iso:" + j["country"]] if j.get("country") else ()))
    return out


def ashby(s):
    d = get(f"https://api.ashbyhq.com/posting-api/job-board/{s['board']}?includeCompensation=true")
    out = []
    for j in d.get("jobs", []):
        locs = [j.get("location", "")] + [x.get("location", "") for x in j.get("secondaryLocations") or []]
        comp = (j.get("compensation") or {}).get("compensationTierSummary") or ""
        country = ((j.get("address") or {}).get("postalAddress") or {}).get("addressCountry")
        r = job(s, j.get("title", ""), locs, j.get("jobUrl", ""), j.get("publishedAt"), j.get("descriptionHtml") or j.get("descriptionPlain") or "",
                find_pay(comp), hints=[country])
        out.append(r)
    return out


def smartrecruiters(s):
    out, off = [], 0
    while True:
        d = get(f"https://api.smartrecruiters.com/v1/companies/{s['board']}/postings?limit=100&offset={off}")
        for j in d.get("content", []):
            l = j.get("location") or {}
            loc = ", ".join(x for x in [l.get("city"), l.get("region")] if x)
            r = job(s, j.get("name", ""), [loc], f"https://jobs.smartrecruiters.com/{s['board']}/{j.get('id')}", j.get("releasedDate"),
                    hints=["iso:" + l["country"]] if l.get("country") else ())
            r["_detail"] = ("smartrecruiters", f"https://api.smartrecruiters.com/v1/companies/{s['board']}/postings/{j.get('id')}")
            out.append(r)
        off += 100
        if off >= d.get("totalFound", 0) or off >= 2000:
            return out
        time.sleep(PAUSE)


def workable(s):
    d = get(f"https://apply.workable.com/api/v1/widget/accounts/{s['board']}?details=true")
    out = []
    for j in d.get("jobs", []):
        loc = ", ".join(x for x in [j.get("city"), j.get("state")] if x)
        more = [x for x in j.get("locations") or [] if isinstance(x, dict)]
        locs = [loc] + [", ".join(v for v in [x.get("city"), x.get("region")] if v) for x in more]
        hints = [j.get("country")] + ["iso:" + x["countryCode"] for x in more if x.get("countryCode")]
        out.append(job(s, j.get("title", ""), list(dict.fromkeys(locs)), j.get("url") or j.get("shortlink", ""), j.get("published_on"),
                       j.get("description") or "", hints=hints))
    return out


WD_TERMS = ("intern", "internship", "co-op", "graduate", "student", "placement", "early career")


def _days_ago(s):
    m = re.search(r"(\d+)\+?\s+days?\s+ago", s or "", re.I)
    n = int(m.group(1)) if m else 0 if re.search(r"today", s or "", re.I) else 1 if re.search(r"yesterday", s or "", re.I) else None
    return (datetime.date.today() - datetime.timedelta(days=n)).isoformat() if n is not None else ""


def workday(s):
    host, site = s["board"].split("/", 1)
    tenant = host.split(".")[0]
    base = f"https://{host}.myworkdayjobs.com"
    out, seen = [], set()
    # Search for early-career terms so large employers do not need thousands of requests.
    for term in WD_TERMS:
        off = 0
        while off < 600:
            d = get(f"{base}/wday/cxs/{tenant}/{site}/jobs", {"appliedFacets": {}, "limit": 20, "offset": off, "searchText": term})
            posts = d.get("jobPostings", [])
            for j in posts:
                path = j.get("externalPath", "")
                if not path or path in seen:
                    continue
                seen.add(path)
                r = job(s, j.get("title", ""), [j.get("locationsText", "")], f"{base}/{site}{path}", _days_ago(j.get("postedOn")))
                r["_detail"] = ("workday", f"{base}/wday/cxs/{tenant}/{site}{path}")
                out.append(r)
            off += 20
            if len(posts) < 20:
                break
            time.sleep(PAUSE)
    return out


FETCH = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby, "smartrecruiters": smartrecruiters, "workable": workable, "workday": workday}


def countries(locs, hints=()):
    return places.countries(locs, hints)


def detail(r):
    """Fetch the full posting where the list did not carry it: real locations, country and description."""
    kind, url = r["_detail"]
    d = get(url)
    if kind == "workday":
        info = d.get("jobPostingInfo", {})
        locs = [info.get("location")] + list(info.get("additionalLocations") or [])
        r["locations"] = [l for l in locs if l] or r["locations"]
        r["hints"] = [(info.get("country") or {}).get("descriptor")] if info.get("country") else r["hints"]
        r["_desc"] = info.get("jobDescription") or ""
        if info.get("startDate"):
            r["posted"] = info["startDate"][:10]
    else:
        sec = (d.get("jobAd") or {}).get("sections") or {}
        r["_desc"] = "\n".join("<p>" + (v.get("text") or "") + "</p>" for v in sec.values() if isinstance(v, dict))


def finish(r, today):
    """Turn a kept posting into its stored form: requirement sentences, deadline, pay; drop the raw description."""
    desc = r.pop("_desc", "")
    r.pop("_detail", None)
    r["type"] = "Internship" if INTERN.search(r["title"]) else "New Grad"
    r["seen"] = today
    r["pay"] = r["pay"] or find_pay(text(desc))
    req, info = E.requirements(desc)
    r["quality"] = "full" if info["len"] >= 400 else "none"
    r["deadline"], r["rolling"] = E.find_deadline(req) if r["quality"] == "full" else ("", False)
    # Requirement sentences are kept where they matter for the shortlist: internships outside the US.
    keep_req = r["type"] == "Internship" and r["countries"] != ["US"] and r["quality"] == "full"
    r["req"] = req if keep_req else []
    r["hash"], r["lang"] = (info["hash"], info["lang"]) if r["quality"] == "full" else ("", "")
    return r


def run(seed):
    try:
        rows = FETCH[seed["ats"]](seed)
    except urllib.error.HTTPError as e:
        return seed, [], f"HTTP {e.code}"
    except Exception as e:  # network errors, bad JSON, changed shapes
        return seed, [], type(e).__name__
    today = datetime.date.today().isoformat()
    keep, seen = [], set()
    for r in rows:
        if not r["url"] or r["url"] in seen or not wanted(r["title"]):
            continue
        seen.add(r["url"])
        r["countries"] = countries(r["locations"], r["hints"])
        # The list view often lacks the real location ("3 Locations") and the description. Fetch the
        # posting itself when the place is unresolved or the role is outside the US.
        if r.get("_detail") and r["countries"] and r["countries"] != ["US"]:
            try:
                detail(r)
                r["countries"] = countries(r["locations"], r["hints"])
                time.sleep(PAUSE)
            except Exception:
                pass  # keep the summary row; its quality stays "none"
        if not r["countries"]:
            continue  # recognisably somewhere else
        keep.append(finish(r, today))
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


def carry_forward(previous, errors, today):
    """Rows from the last run for boards that failed this time, marked stale. Dropped after STALE_DAYS."""
    out = []
    limit = (datetime.date.fromisoformat(today) - datetime.timedelta(days=STALE_DAYS)).isoformat()
    for r in previous.get("jobs", []):
        if f"{r.get('ats')}:{r.get('board')}" in errors:
            since = r.get("stale") or r.get("seen") or previous.get("fetched_at", today)[:10]
            if since >= limit:
                r["stale"] = since
                out.append(r)
    return out


def main():
    args = sys.argv[1:]
    seeds = json.load(open(args[0]))
    out_path = args[1]
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else None
    previous = {}
    if "--previous" in args:
        try:
            previous = json.load(open(args[args.index("--previous") + 1]))
        except (OSError, ValueError):
            previous = {}
    if limit:
        seeds = seeds[:limit]
        out_path += ".partial"  # a test run never replaces the real results
    seeds = [s for s in seeds if s["ats"] in FETCH]
    jobs, errors = [], {}
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        start, total = time.time(), len(seeds)
        for n, (seed, rows, err) in enumerate(ex.map(run, seeds), 1):
            jobs += rows
            if err:
                errors[f"{seed['ats']}:{seed['board']}"] = err
            progress(n, total, len(jobs), len(errors), start)
    sys.stderr.write("\n")
    today = datetime.date.today().isoformat()
    kept_stale = carry_forward(previous, errors, today) if not limit else []
    jobs += kept_stale
    broken = bool(seeds) and len(errors) > len(seeds) * 0.5
    # Written beside the real file and moved into place only when the run is sound, so a failed run never replaces good data.
    tmp = out_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "version": CRAWL_VERSION, "boards": len(seeds),
                   "jobs": jobs, "errors": errors, "stale_rows": len(kept_stale)}, f, ensure_ascii=False, indent=0)
    if broken:
        os.remove(tmp)
        sys.exit(f"More than half the boards failed ({len(errors)} of {len(seeds)}); the previous results were left in place.")
    os.replace(tmp, out_path)
    print(f"boards {len(seeds)} | failed {len(errors)} | early-career roles kept {len(jobs)} | with pay {sum(1 for j in jobs if j['pay'])} | "
          f"postings read in full {sum(1 for j in jobs if j.get('quality') == 'full')} | location unknown {sum(1 for j in jobs if j['countries'] == ['??'])} | "
          f"carried forward from failed boards {len(kept_stale)}")
    if limit:
        print(f"Test run: written to {out_path}")


if __name__ == "__main__":
    main()
