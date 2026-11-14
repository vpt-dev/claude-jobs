#!/usr/bin/env python3
"""Turn the posting checker's output into site/elig.js.

Usage: python3 pipeline/elig_build.py elig.json site/elig.js

Each posting that was read gets [score, reason, short quote], scored for a final-year
bachelor's student who will start a master's after the summer.
"""
import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from crawl import ELIG  # noqa: E402

RX = dict(ELIG)
FINAL = re.compile(r"final[- ]year (student|undergrad)|or (a )?final[- ]year|final or penultimate|in (your|their|the) final year of|graduat\w+ in (the )?(summer |spring |june |july |may )?(of )?2027|class of 2027|recent(ly)? graduat\w*[^.]{0,60}(welcome|eligible|encouraged|may apply|can apply)|\bor recent(ly)? graduat", re.I)
POSTGRAD_ONLY = re.compile(r"year of (a |an |your |their )?(master|msc|phd|doctora)|graduated from (a |an )?(master|msc|phd)|final[- ]year (phd|master|msc|doctoral|postgrad)|final year of\)? (a |an )?(postgrad|master|phd)|master'?s'? degree in progress", re.I)
UNDERGRAD = re.compile(r"bachelor|undergrad|\\b(2nd|second|3rd|third)[- ]year|sophomore|junior", re.I)
NOT_FINAL = re.compile(r"non[- ]?\s?final|not (be )?in (your|their|the) final|excluding final", re.I)
COOP = re.compile(r"co-?op (program|term|student)|placement year|year in industry", re.I)


def quote(key, excerpt):
    """At most 14 words around the phrase that triggered the signal."""
    excerpt = html.unescape(html.unescape(excerpt)).replace("\xa0", " ")
    m = RX[key].search(excerpt)
    if not m:
        return ""
    before = excerpt[:m.start()].split()[-5:]
    hit = excerpt[m.start():m.end()].split()
    after = excerpt[m.end():].split()[:max(0, 14 - len(before) - len(hit))]
    words = (before + hit + after)[:14]
    q = " ".join(words)
    return "" if re.search(r'[{}\[\]"\\]|":', q) else q  # skip page code that is not prose


def score(v):
    s, x = set(v["s"]), v["x"]
    fin = x.get("final_year_ok", "")
    if fin and NOT_FINAL.search(fin):
        return 1, "the posting asks for students who are not in their final year", quote("final_year_ok", fin)
    if fin and FINAL.search(fin) and not re.search(r"or later", fin, re.I):
        if POSTGRAD_ONLY.search(fin):
            return 1, "the posting asks for master's or PhD students", quote("final_year_ok", fin)
        return 5, "Posting read: names final-year students or 2027 graduates.", quote("final_year_ok", fin)
    if "penultimate_only" in s:
        return 1, "the posting asks for penultimate-year students", quote("penultimate_only", x["penultimate_only"])
    for k in ("must_be_enrolled", "must_return_to_study"):
        if k in s and COOP.search(x[k]):
            return 1, "the posting asks for co-op or placement-year students", quote(k, x[k])
    if "grad_2028_or_later" in s and UNDERGRAD.search(x["grad_2028_or_later"]):
        return 1, "the posting asks for undergraduates finishing in 2028 or later", quote("grad_2028_or_later", x["grad_2028_or_later"])
    if "grad_2028_or_later" in s:
        return 3, "Posting read: asks for a 2028 or later graduation, which fits only if your master's counts.", quote("grad_2028_or_later", x["grad_2028_or_later"])
    if "must_return_to_study" in s:
        return 3, "Posting read: asks you to return to study afterwards, which depends on your master's place.", quote("must_return_to_study", x["must_return_to_study"])
    return 4, "Posting read: no year-of-study limit found.", ""


def main():
    src = json.load(open(sys.argv[1]))
    out = {jid: list(score(v)) for jid, v in src["read"].items()}
    with open(sys.argv[2], "w") as f:
        f.write("window.ELIG=" + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n")
        f.write("window.ELIG_INFO=" + json.dumps({"checked": src.get("checked", ""), "total": src.get("total", 0), "read": len(out)}) + ";\n")
    tally = {}
    for v in out.values():
        tally[v[0]] = tally.get(v[0], 0) + 1
    print("scores", dict(sorted(tally.items())))


if __name__ == "__main__":
    main()
