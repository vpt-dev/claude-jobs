#!/usr/bin/env python3
"""Decide which postings the checker should read, and fold its results back in.

  targets.py make  jobs.json data_dir targets.json   list UK and Canada internships not yet read
  targets.py merge new_elig.json data_dir targets.json   add the checker's results to data_dir/elig.json

Postings that could not be read are remembered in data_dir/elig_tried.json and retried after a week.
"""
import datetime
import json
import os
import sys

RETRY_DAYS = 7


def load(path, default):
    return json.load(open(path)) if os.path.exists(path) else default


def main():
    mode, a, data, targets = sys.argv[1:5]
    today = datetime.date.today()
    tried_path = os.path.join(data, "elig_tried.json")
    tried = load(tried_path, {})
    elig = load(os.path.join(data, "elig.json"), {"read": {}})
    if mode == "make":
        rows = json.load(open(a))
        done = set(elig["read"]) | set(load(os.path.join(data, "elig_crawl.json"), {"read": {}})["read"])
        recent = {k for k, d in tried.items() if (today - datetime.date.fromisoformat(d)).days < RETRY_DAYS}
        out = [[r[18], r[6]] for r in rows if r[4] == "Internship" and (set(r[3]) & {"UK", "CA"}) and r[6].startswith("http")
               and r[18] not in done and r[18] not in recent]
        json.dump(out, open(targets, "w"))
        print(f"postings to read: {len(out)}")
    else:
        new = load(a, {"read": {}})
        elig["read"].update(new["read"])
        elig["checked"] = today.isoformat()
        json.dump(elig, open(os.path.join(data, "elig.json"), "w"), ensure_ascii=False)
        for jid, _ in load(targets, []):
            if jid not in new["read"]:
                tried[jid] = today.isoformat()
        json.dump(tried, open(tried_path, "w"))
        print(f"postings read so far: {len(elig['read'])}")


if __name__ == "__main__":
    main()
