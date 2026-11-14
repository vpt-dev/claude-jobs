#!/usr/bin/env python3
"""Look for employers' own job boards, and keep the ones that exist.

Usage: python3 probe.py jobs.json seeds.json ats_jobs.json probe_tried.json probe_report.json

Two kinds of employer are tried:
  1. a hand-written list of high-paying UK and Canada employers (MUST below), and
  2. employers whose UK or Canada roles we only know through another list's link.

For each, likely board addresses on Greenhouse, Lever and Ashby are tested. A board that answers
is added to seeds.json for every later crawl, and its early-career roles are added to ats_jobs.json.
Addresses that do not answer are remembered and retried after RETRY_DAYS.
"""
import concurrent.futures as cf
import datetime
import json
import os
import re
import sys
import time

import crawl

RETRY_DAYS = 30
MAX_PROBES = 700
LIST_LINK = re.compile(r"csjobs\.ca|go\.vansh\.nyc|grind\.fyi|dreamworkhq\.com|simplify\.jobs|linkedin\.com|reed\.co\.uk")
GENERIC = {"float", "neo", "ada", "cleo", "tide", "peak", "bell", "bolt", "wave", "flex", "loop", "nova", "apex", "atlas", "unity",
           "relay", "ritual", "bench", "clear", "scale", "notion", "linear", "vital", "pivot", "orbit", "summit", "motion", "signal",
           "confidential", "stealth", "jobgether", "mthree", "mthreerecruitingportal"}

# Employer, then board addresses worth trying: "greenhouse:slug", "lever:slug", "ashby:slug" or "workday:tenant.wdN/site".
MUST = [
    ("XTX Markets", ["greenhouse:xtxmarketstechnologies", "greenhouse:xtxmarkets"]), ("Man Group", ["greenhouse:mangroup"]),
    ("Flow Traders", ["greenhouse:flowtraders"]), ("Balyasny Asset Management", ["greenhouse:bamfunds", "greenhouse:balyasny"]),
    ("Google DeepMind", ["greenhouse:deepmind"]), ("Monzo", ["greenhouse:monzo"]), ("Arm", ["workday:arm.wd1/Careers"]),
    ("Spotify", ["lever:spotify"]), ("Faculty", ["ashby:faculty", "greenhouse:faculty"]), ("Wayve", ["greenhouse:wayve", "ashby:wayve"]),
    ("Isomorphic Labs", ["greenhouse:isomorphiclabs"]), ("Synthesia", ["ashby:synthesia", "greenhouse:synthesia"]),
    ("ElevenLabs", ["ashby:elevenlabs"]), ("Datadog", ["greenhouse:datadog"]), ("Roblox", ["greenhouse:roblox"]),
    ("Airbnb", ["greenhouse:airbnb"]), ("Coinbase", ["greenhouse:coinbase"]), ("Robinhood", ["greenhouse:robinhood"]),
    ("Okta", ["greenhouse:okta"]), ("Instacart", ["greenhouse:instacart"]), ("Rippling", ["ashby:rippling", "greenhouse:rippling"]),
    ("Plaid", ["lever:plaid", "ashby:plaid"]), ("Ada", ["greenhouse:ada18", "greenhouse:ada"]), ("Samsara", ["greenhouse:samsara"]),
    ("1Password", ["ashby:1password", "lever:1password"]), ("Wealthsimple", ["ashby:wealthsimple", "lever:wealthsimple"]),
    ("Jump Trading", ["greenhouse:jumptrading"]), ("Millennium", ["workday:mlp.wd5/mlpcareers"]),
    ("Deliveroo", ["greenhouse:deliveroo"]), ("GoCardless", ["greenhouse:gocardless"]), ("Snyk", ["greenhouse:snyk"]),
    ("Thought Machine", ["greenhouse:thoughtmachine"]), ("Cleo", ["greenhouse:cleoai", "greenhouse:cleo"]),
    ("Octopus Energy", ["lever:octoenergy", "greenhouse:octopusenergy"]), ("Speechmatics", ["greenhouse:speechmatics", "ashby:speechmatics"]),
    ("PolyAI", ["greenhouse:polyai", "ashby:polyai"]), ("Graphcore", ["greenhouse:graphcore"]), ("Improbable", ["greenhouse:improbable"]),
    ("Quantexa", ["greenhouse:quantexa"]), ("Darktrace", ["greenhouse:darktrace"]), ("Ocado Technology", ["greenhouse:ocadotechnology"]),
    ("Tractable", ["greenhouse:tractable", "ashby:tractable"]), ("Onfido", ["greenhouse:onfido"]),
    ("Motorway", ["greenhouse:motorway", "ashby:motorway"]), ("Zopa", ["greenhouse:zopa", "ashby:zopa"]),
    ("Starling Bank", ["greenhouse:starlingbank"]), ("Checkout.com", ["greenhouse:checkoutcom", "ashby:checkout.com"]),
    ("Moneybox", ["greenhouse:moneybox"]), ("Lendable", ["greenhouse:lendable", "ashby:lendable"]), ("ClearScore", ["greenhouse:clearscoreltd"]),
    ("Nscale", ["ashby:nscale", "greenhouse:nscale"]), ("Helsing", ["greenhouse:helsing", "ashby:helsing"]),
    ("Skyscanner", ["greenhouse:skyscanner"]), ("Oxa", ["greenhouse:oxa"]), ("GSA Capital", ["greenhouse:gsacapital"]),
    ("Stability AI", ["greenhouse:stabilityai"]), ("Featurespace", ["greenhouse:featurespace"]), ("Marshmallow", ["greenhouse:marshmallow", "ashby:marshmallow"]),
    ("Paddle", ["greenhouse:paddle"]), ("Multiverse", ["greenhouse:multiverse"]), ("Depop", ["greenhouse:depop"]),
    ("KOHO", ["greenhouse:koho", "lever:koho"]), ("Clio", ["lever:clio", "greenhouse:clio"]), ("Hootsuite", ["greenhouse:hootsuite"]),
    ("ecobee", ["greenhouse:ecobee"]), ("Wattpad", ["greenhouse:wattpad"]), ("Waabi", ["lever:waabi", "greenhouse:waabi"]),
    ("Xanadu", ["lever:xanadu", "greenhouse:xanadu"]), ("ApplyBoard", ["greenhouse:applyboard"]), ("Top Hat", ["greenhouse:tophat", "lever:tophat"]),
    ("Vidyard", ["greenhouse:vidyard"]), ("BenchSci", ["greenhouse:benchsci", "lever:benchsci"]), ("Deep Genomics", ["greenhouse:deepgenomics"]),
    ("Untether AI", ["greenhouse:untetherai"]), ("Tenstorrent", ["greenhouse:tenstorrent", "lever:tenstorrent"]),
    ("Neo Financial", ["greenhouse:neofinancial"]), ("Lightspeed", ["greenhouse:lightspeedhq"]), ("Hopper", ["greenhouse:hopper", "lever:hopper"]),
    ("Mistplay", ["greenhouse:mistplay"]), ("PointClickCare", ["lever:pointclickcare"]), ("Thinkific", ["greenhouse:thinkific"]),
    ("Trulioo", ["greenhouse:trulioo"]), ("Jobber", ["greenhouse:jobber"]), ("Borealis AI", ["greenhouse:borealisai"]),
]


def norm(s):
    s = re.sub(r"[^a-z0-9 ]", "", s.lower())
    return re.sub(r"\b(inc|llc|ltd|limited|corp|corporation|co|company|group|technologies|technology|the|canada|uk)\b", "", s).replace(" ", "")


def load(path, default):
    return json.load(open(path)) if os.path.exists(path) and os.path.getsize(path) else default


def guesses(jobs, known_names):
    """Employers we only reach through a list's link, most roles first, with board addresses to try."""
    count, name = {}, {}
    for r in jobs:
        if set(r[3]) & {"UK", "CA"} and LIST_LINK.search(r[6]):
            k = norm(r[0])
            if len(k) >= 4 and k not in known_names and k not in GENERIC:
                count[k] = count.get(k, 0) + 1
                name.setdefault(k, r[0])
    out = []
    for k in sorted(count, key=count.get, reverse=True):
        cands = ["greenhouse:" + k]  # Greenhouse names its boards, so a wrong match can be caught
        if len(k) >= 8 and k not in GENERIC:
            cands += ["lever:" + k, "ashby:" + k]
        out.append((name[k], cands, False))
    return out


def try_board(item):
    """Return (company, address, kept roles or None, board display name)."""
    company, addr, trusted = item
    ats, board = addr.split(":", 1)
    shown = company
    try:
        if ats == "greenhouse":
            info = crawl.get(f"https://boards-api.greenhouse.io/v1/boards/{board}")
            title = (info.get("name") or "").strip()
            a, b = norm(title), norm(company)
            if not trusted and not (a and b and (a.startswith(b) or b.startswith(a))):
                return company, addr, None, ""  # a different employer owns this address
        seed, rows, err = crawl.run({"ats": ats, "board": board, "company": shown})
    except Exception:
        return company, addr, None, ""
    if err:
        return company, addr, None, ""
    time.sleep(crawl.PAUSE)
    return company, addr, rows, shown


def main():
    jobs_path, seeds_path, ats_path, tried_path, report_path = sys.argv[1:6]
    today = datetime.date.today()
    jobs = load(jobs_path, [])
    seeds = load(seeds_path, [])
    tried = load(tried_path, {})
    ats = load(ats_path, {"jobs": [], "errors": {}})

    # Earlier guesses that were stored as seeds are handled here instead.
    seeds = [s for s in seeds if not s.get("probe")]
    known = {f"{s['ats']}:{s['board']}".lower() for s in seeds}
    known_names = {norm(s.get("company", "")) for s in seeds}
    stale = lambda a: a.lower() in tried and (today - datetime.date.fromisoformat(tried[a.lower()])).days < RETRY_DAYS

    plan, planned = [], set()
    for company, cands, trusted in [(c, a, True) for c, a in MUST] + guesses(jobs, known_names):
        if trusted and any(a.lower() in known for a in cands):
            continue  # already have a working board for this employer
        for a in cands:
            if a.lower() not in known and a.lower() not in planned and not stale(a):
                planned.add(a.lower())
                plan.append((company, a, trusted))
    plan = plan[:MAX_PROBES]

    found, got_company, start = [], set(), time.time()
    have_urls = {j["url"] for j in ats["jobs"]}
    with cf.ThreadPoolExecutor(6) as ex:
        for n, (company, addr, rows, shown) in enumerate(ex.map(try_board, plan), 1):
            if rows is None or company in got_company:
                if rows is None:
                    tried[addr.lower()] = today.isoformat()
            else:
                got_company.add(company)
                a, board = addr.split(":", 1)
                cs = sorted({c for r in rows for c in r.get("countries", [])})
                seeds.append({"ats": a, "board": board, "company": shown, "roles_seen": len(rows), "countries": cs, "added": today.isoformat()})
                fresh = [r for r in rows if r["url"] not in have_urls]
                ats["jobs"] += fresh
                have_urls.update(r["url"] for r in fresh)
                found.append({"company": shown, "board": addr, "early_career_roles": len(rows),
                              "uk_or_canada": sum(1 for r in rows if set(r.get("countries", [])) & {"UK", "CA"})})
            crawl.progress(n, len(plan), len(found), n - len(found), start)
    if plan:
        sys.stderr.write("\n")

    json.dump(seeds, open(seeds_path, "w"), ensure_ascii=False)
    json.dump(tried, open(tried_path, "w"))
    json.dump(ats, open(ats_path, "w"), ensure_ascii=False, indent=0)
    report = load(report_path, {"runs": []})
    report["runs"] = ([{"date": today.isoformat(), "addresses_tried": len(plan), "boards_found": found}] + report.get("runs", []))[:20]
    json.dump(report, open(report_path, "w"), ensure_ascii=False, indent=1)
    print(f"employer boards tried {len(plan)} | found {len(found)} | "
          f"new UK or Canada roles {sum(f['uk_or_canada'] for f in found)}")
    for f in found[:40]:
        print(f"  + {f['company']} ({f['board']}): {f['early_career_roles']} early-career roles, {f['uk_or_canada']} in the UK or Canada")


if __name__ == "__main__":
    main()
