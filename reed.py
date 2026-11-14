#!/usr/bin/env python3
"""Fetch UK early-career tech roles from the Reed API and write reed_jobs.json.

The API key is read from the REED_API_KEY environment variable, or from a file named
reed_key.txt next to this script. It is never printed or written to the output.
Usage: python3 reed.py reed_jobs.json
"""
import base64
import datetime
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

import eligibility as E
from crawl import INTERN, text, wanted

HERE = os.path.dirname(os.path.abspath(__file__))
QUERIES = ["software engineer intern", "software developer internship", "data science intern", "machine learning intern",
           "technology summer internship", "data analyst intern", "quantitative intern", "graduate software engineer",
           "graduate data scientist", "computer science internship"]
PAUSE = 1.0


def key():
    k = os.environ.get("REED_API_KEY", "").strip()
    if not k:
        try:
            k = open(os.path.join(HERE, "reed_key.txt")).read().strip()
        except OSError:
            pass
    if not k:
        sys.exit("No Reed key found. Set REED_API_KEY or put the key in reed_key.txt beside this script.")
    return k


def get(url, k):
    req = urllib.request.Request(url, headers={"Authorization": "Basic " + base64.b64encode((k + ":").encode()).decode(),
                                               "User-Agent": "early-career-jobs-board/0.1 (personal job search tool)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def main():
    k, seen, out = key(), set(), []
    today = datetime.date.today().isoformat()
    for q in QUERIES:
        for skip in (0, 100):
            url = "https://www.reed.co.uk/api/1.0/search?" + urllib.parse.urlencode({"keywords": q, "resultsToTake": 100, "resultsToSkip": skip})
            try:
                res = get(url, k).get("results", [])
            except Exception as e:
                print(f"query '{q}' failed: {type(e).__name__}")
                break
            for j in res:
                t = (j.get("jobTitle") or "").strip()
                if j.get("jobId") in seen or not wanted(t):
                    continue
                seen.add(j["jobId"])
                lo, hi = j.get("minimumSalary"), j.get("maximumSalary")
                out.append({"company": j.get("employerName", ""), "title": t, "locations": [(j.get("locationName") or "") + ", UK"],
                            "countries": ["UK"], "url": j.get("jobUrl", ""), "posted": _iso(j.get("date")),
                            "pay": {"min": lo, "max": hi or lo, "cur": j.get("currency") or "GBP",
                                    "period": "year" if lo >= 5000 else "day" if lo >= 60 else "hour"} if lo else None,
                            "reed_id": j["jobId"], "type": "Internship" if INTERN.search(t) else "New Grad", "ats": "reed", "board": "reed",
                            "seen": today, "deadline": _iso(j.get("expirationDate")), "rolling": False,
                            # The search result carries only an excerpt: partial evidence until the full posting is read below.
                            "_desc": j.get("jobDescription") or "", "quality": "partial"})
            if len(res) < 100:
                break
            time.sleep(PAUSE)
        time.sleep(PAUSE)
    for r in out[:400]:
        try:
            full = get(f"https://www.reed.co.uk/api/1.0/jobs/{r['reed_id']}", k)
            if len(text(full.get("jobDescription", ""))) >= 400:
                r["_desc"], r["quality"] = full["jobDescription"], "full"
                r["deadline"] = _iso(full.get("expirationDate")) or r["deadline"]
        except Exception:
            pass  # stays partial
        time.sleep(0.5)
    for r in out:
        req, info = E.requirements(r.pop("_desc"))
        r["req"] = req if r["type"] == "Internship" else []
        r["hash"], r["lang"] = info["hash"], info["lang"]
    json.dump({"fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "jobs": out}, open(sys.argv[1], "w"), ensure_ascii=False, indent=0)
    print(f"Reed: kept {len(out)} early-career tech roles | with pay {sum(1 for r in out if r['pay'])} | "
          f"read in full {sum(1 for r in out if r['quality'] == 'full')} | with a closing date {sum(1 for r in out if r['deadline'])}")


def _iso(d):
    m = re.match(r"(\d\d)/(\d\d)/(\d{4})", d or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""


if __name__ == "__main__":
    main()
