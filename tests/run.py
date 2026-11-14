#!/usr/bin/env python3
"""Regression checks. Run from the repository root: python3 tests/run.py"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import eligibility as E  # noqa: E402

fails = 0


def check(ok, label, detail=""):
    global fails
    if not ok:
        fails += 1
        print("FAIL", label, detail)


prof = E.DEFAULT_PROFILE
cases = json.load(open(os.path.join(ROOT, "tests", "eligibility_cases.json")))
for c in cases:
    r = E.evaluate(c.get("title", "Software Engineer Intern"), c.get("terms", []), c["req"], prof, quality=c.get("quality", "full"))
    good = r["state"] == c["state"] and (not c.get("kind") or r["kind"] == c["kind"])
    check(good, "eligibility: " + c["name"], f"-> {r['state']}/{r['kind']}: {r['reason']}")
print(f"eligibility cases: {len(cases)}")

for extra in ("test_text.py", "test_identity.py", "test_places.py", "test_crawl.py", "test_build.py"):
    path = os.path.join(ROOT, "tests", extra)
    if os.path.exists(path):
        ns = {"check": check, "ROOT": ROOT}
        exec(compile(open(path).read(), path, "exec"), ns)
print("ALL PASSED" if not fails else f"{fails} FAILED")
sys.exit(1 if fails else 0)
