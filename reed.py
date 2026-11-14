#!/usr/bin/env python3
"""Fetch UK early-career tech roles from the Reed API and write reed_jobs.json.

The API key is read from the REED_API_KEY environment variable, or from a file named
reed_key.txt next to this script. It is never printed or written to the output.
Usage: python3 reed.py reed_jobs.json
"""
import base64
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

from crawl import EARLY, SENIOR, TECH, eligibility, text

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
    for q in QUERIES:
        for skip in (0, 100):
            url = "https://www.reed.co.uk/api/1.0/search?" + urllib.parse.urlencode({"keywords": q, "resultsToTake": 100, "resultsToSkip": skip})
            try:
                res = get(url, k).get("results", [])
            except Exception as e:
                print(f"query '{q}' failed: {type(e).__name__}")
                break
            for j in res:
                t = j.get("jobTitle", "")
                if j.get("jobId") in seen or not EARLY.search(t) or SENIOR.search(t) or not TECH.search(t):
                    continue
                seen.add(j["jobId"])
                d = j.get("date", "")
                m = re.match(r"(\d\d)/(\d\d)/(\d{4})", d)
                lo, hi = j.get("minimumSalary"), j.get("maximumSalary")
                out.append({"company": j.get("employerName", ""), "title": t.strip(), "locations": [(j.get("locationName") or "") + ", UK"],
                            "countries": ["UK"], "url": j.get("jobUrl", ""), "posted": f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else "",
                            "pay": {"min": lo, "max": hi or lo, "cur": j.get("currency") or "GBP", "period": "year" if lo >= 5000 else "day" if lo >= 60 else "hour"} if lo else None,
                            "elig": eligibility(text(j.get("jobDescription", ""))), "reed_id": j["jobId"],
                            "type": "Internship" if re.search(r"intern|placement", t, re.I) else "New Grad", "ats": "reed", "board": "reed"})
            if len(res) < 100:
                break
            time.sleep(PAUSE)
        time.sleep(PAUSE)
    # The search only returns a short excerpt, so read the full description of each kept role for year-of-study wording.
    for r in out[:400]:
        try:
            full = get(f"https://www.reed.co.uk/api/1.0/jobs/{r['reed_id']}", k)
            r["elig"] = eligibility(text(full.get("jobDescription", ""))) or r["elig"]
        except Exception:
            pass
        time.sleep(0.5)
    json.dump({"fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "jobs": out}, open(sys.argv[1], "w"), ensure_ascii=False, indent=0)
    print(f"Reed: kept {len(out)} early-career tech roles | with pay {sum(1 for r in out if r['pay'])} | with year-of-study wording {sum(1 for r in out if r['elig'])}")


if __name__ == "__main__":
    main()
