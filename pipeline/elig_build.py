#!/usr/bin/env python3
"""Judge every UK, Canada and unknown-location internship against the candidate profile.

Usage: python3 pipeline/elig_build.py jobs.json work_dir data_dir site/elig.js [profile.json]

For each role the newest evidence is used: the requirement sentences stored by the crawler
(work_dir/elig_crawl.json) or by the posting checker (data_dir/evidence.json). The result is one of
four states, kept apart from how well the posting was read:

  window.ELIG[id] = [state, quality, reason, sentence, checked, kind, deadline, rolling, failed]

  state    M published match | C conditional | U unknown | X explicit mismatch
  quality  full | partial | none          (none = the posting has not been read)
  failed   the day the posting could last not be opened, if it could not

A role is never ruled out without a sentence from its posting or title, and a posting that was not
read is "unknown", never a match and never a mismatch.
"""
import collections
import datetime
import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import eligibility as E  # noqa: E402
from targets import better, in_scope, load  # noqa: E402

MONTHS = "January February March April May June July August September October November December".split()


def month(ym):
    y, m = ym.split("-")[:2]
    return f"{MONTHS[int(m) - 1]} {y}"


def describe(prof):
    """The facts the judgement rests on, in plain words, shown on the page so they can be checked."""
    d, m, a = prof["degree"], prof["masters"], prof["available"]
    lines = [f"Final-year {d['level']}'s student in {d['field']}: teaching ends {month(d['study_ends'])}, degree awarded {month(d['award'])}."]
    where = " or ".join({"US": "the US", "CA": "Canada", "UK": "the UK"}.get(c, c) for c in m.get("countries", []))
    status = {"applied": "applied for, not yet confirmed", "offer": "offer held, not yet accepted", "confirmed": "place confirmed", "none": "not planned"}
    if m.get("status") and m["status"] != "none":
        lines.append(f"Master's in {where}: {status.get(m['status'], m['status'])}; it would start {month(m['starts'])}.")
    else:
        lines.append("No master's planned.")
    lines.append("Right to work: " + " and ".join({"UK": "the UK", "CA": "Canada", "US": "the US"}.get(c, c) for c in prof["work_rights"]) + ".")
    lines.append(f"Free to work from {month(a['from'])} to {month(a['to'])}. " + ("On a co-op programme." if prof.get("coop_registered") else "Not on a co-op programme."))
    return lines


def sentences(ev):
    """Requirement sentences from an evidence record. Older records hold short fragments rather than whole sentences."""
    if not ev:
        return []
    if "req" in ev:
        return ev["req"] or []
    out = []
    for x in (ev.get("legacy") or {}).values():
        x = re.sub(r"\s+", " ", html.unescape(html.unescape(x or "")).replace("\xa0", " ")).strip()
        if x and x not in out:
            out.append(x)
    return out


def shown(text, ev):
    """The sentence as displayed. Fragments kept by the older reader are cut mid-sentence, so they are marked as cut."""
    text = (text or "").strip()
    if text and ev and "req" not in ev:
        text = ("" if text[:1].isupper() else "… ") + text + ("" if text[-1:] in ".!?" else " …")
    return text[:340]


def main():
    jobs, work, data, out_path = sys.argv[1:5]
    prof = E.load_profile(sys.argv[5] if len(sys.argv) > 5 else None)
    rows = json.load(open(jobs))
    crawl = load(os.path.join(work, "elig_crawl.json"), {"read": {}})["read"]
    store = load(os.path.join(data, "evidence.json"), {"read": {}, "tried": {}})
    out, states, quals = {}, collections.Counter(), collections.Counter()
    for r in rows:
        if not in_scope(r):
            continue
        jid = r[18]
        ev = better(crawl.get(jid), store["read"].get(jid))
        quality = (ev or {}).get("quality", "none")
        res = E.evaluate(r[1], r[17], sentences(ev), prof, quality=quality, lang=(ev or {}).get("lang", ""))
        if res["state"] == "X" and res["from"] == "posting" and ev and "req" not in ev:
            # The older reader kept short excerpts, which can cut a sentence in half. A role is not ruled out on
            # half a sentence: it is held as conditional until the posting has been read again in full.
            res["state"] = "C"
            res["reason"] += " This rests on an excerpt, not the whole sentence; the posting is due to be read again."
        failed = store["tried"].get(jid, "")
        if ev and failed and failed <= ev.get("checked", ""):
            failed = ""
        out[jid] = [res["state"], quality, res["reason"], shown(res["evidence"], ev), (ev or {}).get("checked", ""), res["kind"],
                    r[20] or (ev or {}).get("deadline", ""), 1 if (ev or {}).get("rolling") else 0, failed]
        states[res["state"]] += 1
        quals[quality] += 1
    info = {"date": datetime.date.today().isoformat(), "reader": E.EXTRACT_VERSION, "profile": describe(prof),
            "states": dict(states), "quality": dict(quals)}
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("window.ELIG=" + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n")
        f.write("window.ELIG_INFO=" + json.dumps(info, ensure_ascii=False) + ";\n")
    os.replace(tmp, out_path)
    names = {"M": "published match", "C": "conditional", "U": "unknown", "X": "explicit mismatch"}
    print("internships judged:", len(out), "|", ", ".join(f"{names[k]} {states.get(k, 0)}" for k in "MCUX"),
          "| read in full", quals.get("full", 0), "partly", quals.get("partial", 0), "not read", quals.get("none", 0))


if __name__ == "__main__":
    main()
