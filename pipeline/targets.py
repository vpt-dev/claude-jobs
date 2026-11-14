#!/usr/bin/env python3
"""Decide which postings the checker should read, and fold its results back in.

  targets.py make  jobs.json work_dir data_dir targets.json   choose postings to read or re-read
  targets.py merge results.json data_dir targets.json         store what the checker read

What is stored (data_dir/evidence.json):
  read   job id -> the requirement sentences of its posting, when it was read and how well
  tried  job id -> the day a posting could not be read (retried after RETRY_DAYS)

A posting is read again when its record is older than about ten days or was made by an older
version of the reader, so a posting that changes or closes is noticed. Short links that led to an
employer's posting are remembered in data_dir/links.json, keyed by the short link.
"""
import datetime
import hashlib
import json
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import eligibility as E  # noqa: E402
import identity as ID  # noqa: E402

RETRY_DAYS = 7      # how long to wait before trying an unreadable posting again
RECHECK_DAYS = 8    # a read posting is read again after 8 to 14 days (spread out so they do not all fall on one day)
KEEP_DAYS = 45      # how long to keep the record of a posting that is no longer listed
MAX_PER_RUN = 4000
NO_READ, SHORT = ID.NO_READ, ID.SHORT


def host(u):
    return urllib.parse.urlparse(u).netloc.lower()


def load(path, default):
    try:
        return json.load(open(path)) if os.path.exists(path) else default
    except ValueError:
        return default


def age(day, today):
    try:
        return (today - datetime.date.fromisoformat((day or "")[:10])).days
    except ValueError:
        return 10 ** 6


def better(a, b):
    """The more useful of two records: newer reader, then a full read, then the more recent."""
    if not a or not b:
        return a or b
    rank = lambda e: (e.get("v", 1), e.get("quality") == "full", e.get("checked", ""))
    return b if rank(b) > rank(a) else a


def in_scope(r):
    """Internships in the UK or Canada, and those whose country could not be worked out."""
    return r[4] == "Internship" and (set(r[3]) & {"UK", "CA", "??"})


def main():
    mode = sys.argv[1]
    today = datetime.date.today()
    if mode == "make":
        jobs, work, data, out_path = sys.argv[2:6]
        rows = json.load(open(jobs))
        store = load(os.path.join(data, "evidence.json"), {"read": {}, "tried": {}})
        crawl = load(os.path.join(work, "elig_crawl.json"), {"read": {}})["read"]
        want, unreadable = [], 0
        for r in rows:
            jid, url = r[18], r[6]
            if not in_scope(r) or not url.startswith("http"):
                continue
            if NO_READ.search(host(url)):
                unreadable += 1
                continue
            best = better(crawl.get(jid), store["read"].get(jid))
            spread = int(hashlib.sha1(jid.encode()).hexdigest(), 16) % 7
            if best and best.get("v", 1) >= E.EXTRACT_VERSION and age(best.get("checked"), today) < RECHECK_DAYS + spread:
                continue
            if age(store["tried"].get(jid), today) < RETRY_DAYS:
                continue
            # Never read first, then the oldest records.
            want.append(((0, "") if not best else (1, best.get("checked", "")), [jid, url, r[1]]))
        want.sort(key=lambda w: w[0])
        targets = [w[1] for w in want[:MAX_PER_RUN]]
        json.dump(targets, open(out_path, "w"))
        print(f"postings to read: {len(targets)} | on sites that do not allow automated reading: {unreadable}")
    elif mode == "merge":
        new_path, data, targets_path = sys.argv[2:5]
        new = load(new_path, {"read": {}, "links": {}})
        store = load(os.path.join(data, "evidence.json"), {"read": {}, "tried": {}})
        links = load(os.path.join(data, "links.json"), {})
        targets = load(targets_path, [])
        for t in targets:
            jid, url = t[0], t[1]
            moved = (new.get("links") or {}).get(jid)
            rid = jid
            if moved and SHORT.search(host(url)) and not NO_READ.search(host(moved)) and not SHORT.search(host(moved)):
                links[ID.nurl(url)] = moved
                key = ID.vkey(moved)
                if key:
                    rid = ID.job_id(key)  # the next build files this role under the employer's own posting
            if jid in new["read"]:
                store["read"][rid] = new["read"][jid]
                store["tried"].pop(jid, None)
                store["tried"].pop(rid, None)
            else:
                store["tried"][jid] = today.isoformat()
        # Forget postings that have not been listed, and so not re-read, for a long time.
        store["read"] = {k: v for k, v in store["read"].items() if age(v.get("checked"), today) <= KEEP_DAYS}
        store["tried"] = {k: v for k, v in store["tried"].items() if age(v, today) <= KEEP_DAYS}
        store["checked"] = today.isoformat()
        json.dump(store, open(os.path.join(data, "evidence.json"), "w"), ensure_ascii=False, indent=0, sort_keys=True)
        json.dump(links, open(os.path.join(data, "links.json"), "w"), indent=0, sort_keys=True)
        full = sum(1 for v in store["read"].values() if v.get("quality") == "full" and v.get("v", 1) >= E.EXTRACT_VERSION)
        print(f"postings on record: {len(store['read'])} ({full} read in full by the current reader) | links traced to employers: {len(links)}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
