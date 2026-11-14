#!/usr/bin/env python3
"""Open each UK and Canada internship posting and pull out its year-of-study wording.

Usage: python3 check_postings.py targets.json elig.json

targets.json is a list of [job id, posting URL]. The result maps each job id whose
posting could be read to the signals found (see ELIG in crawl.py) with a short excerpt.
Postings that cannot be read are left out, so the site treats them as unchecked.
"""
import concurrent.futures as cf
import json
import re
import sys
import time
import urllib.parse
import urllib.request

from crawl import UA, eligibility, get, progress, text

TIMEOUT = 25
LOOKS_LIKE_A_POSTING = re.compile(r"responsibilit|qualif|requirement|about you|what you|who you are|we are looking|you will|your role", re.I)


ATS_LINK = re.compile(r"greenhouse\.io/|lever\.co/|myworkdayjobs\.com/|jobs\.smartrecruiters\.com/")


def fetch(url):
    """Return (address after any redirects, page text)."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/json;q=0.9,*/*;q=0.5"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.geturl(), r.read(3_000_000).decode("utf-8", "replace")


def unescape_json(s):
    """Postings embedded in page scripts carry escaped markup; make it readable."""
    return (s.replace("\\u003c", "<").replace("\\u003e", ">").replace("\\u0026", "&")
             .replace("\\n", " ").replace("\\t", " ").replace('\\"', '"').replace("\\/", "/"))


def describe(url, hop=0):
    """Return (posting text or '' when it cannot be read, the posting's real address)."""
    u = urllib.parse.urlparse(url)
    host, path = u.netloc.lower(), u.path

    m = re.search(r"greenhouse\.io/(?:embed/job_app/?\?for=)?([\w-]+)/jobs/(\d+)", url)
    if m:
        j = get(f"https://boards-api.greenhouse.io/v1/boards/{m.group(1)}/jobs/{m.group(2)}")
        return text(j.get("content", "")), url

    m = re.search(r"jobs\.(eu\.)?lever\.co/([\w.-]+)/([0-9a-f-]{36})", url)
    if m:
        j = get(f"https://api.{'eu.' if m.group(1) else ''}lever.co/v0/postings/{m.group(2)}/{m.group(3)}")
        parts = [j.get("descriptionPlain", ""), j.get("additionalPlain", "")]
        parts += [x.get("text", "") + " " + text(x.get("content", "")) for x in j.get("lists", [])]
        return " ".join(parts), url

    if host.endswith("myworkdayjobs.com"):
        seg = [s for s in path.split("/") if s]
        if seg and re.fullmatch(r"[a-z]{2}-[A-Z]{2}", seg[0]):
            seg = seg[1:]
        if len(seg) >= 3 and "job" in seg[1:]:
            i = seg.index("job", 1)
            site, rest = seg[i - 1], "/".join(seg[i + 1:])
            j = get(f"https://{host}/wday/cxs/{host.split('.')[0]}/{site}/job/{rest}")
            return text(j.get("jobPostingInfo", {}).get("jobDescription", "")), url
        return "", url

    m = re.search(r"jobs\.smartrecruiters\.com/([\w-]+)/(\d+)", url)
    if m:
        j = get(f"https://api.smartrecruiters.com/v1/companies/{m.group(1)}/postings/{m.group(2)}")
        sec = j.get("jobAd", {}).get("sections", {})
        return text(" ".join(v.get("text", "") for v in sec.values() if isinstance(v, dict))), url

    final, raw = fetch(url)
    if hop == 0 and final != url and ATS_LINK.search(final):
        return describe(final, 1)  # a short link that led to an employer board: read it the proper way
    page = text(unescape_json(raw))
    return (page if len(page) > 1500 and LOOKS_LIKE_A_POSTING.search(page) else ""), final


def host(u):
    return urllib.parse.urlparse(u).netloc.lower()


def check(target):
    """Return (job id, signals or None, reason it was not read, real address when a short link led elsewhere)."""
    jid, url = target
    try:
        desc, final = describe(url)
    except Exception as e:  # one bad posting must not stop the run
        return jid, None, type(e).__name__, None
    moved = final if host(final) and host(final) != host(url) else None
    if len(desc) < 400:
        return jid, None, "unreadable", moved
    sig = eligibility(desc)
    return jid, {"s": sorted(sig), "x": {k: v[:170] for k, v in sig.items()}}, None, moved


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    targets = json.load(open(sys.argv[1]))
    if "--limit" in sys.argv:
        targets = targets[: int(sys.argv[sys.argv.index("--limit") + 1])]
    out, why, links = {}, {}, {}
    start, total = time.time(), max(1, len(targets))
    with cf.ThreadPoolExecutor(8) as ex:
        for n, (jid, res, err, moved) in enumerate(ex.map(check, targets), 1):
            if moved:
                links[jid] = moved
            if res is not None:
                out[jid] = res
            else:
                why[err] = why.get(err, 0) + 1
            progress(n, total, len(out), n - len(out), start)
    sys.stderr.write("\n")
    json.dump({"checked": time.strftime("%Y-%m-%d"), "total": total, "read": out, "not_read": why, "links": links}, open(sys.argv[2], "w"))
    print(f"postings {total} | read {len(out)} | not readable {total - len(out)} {why}")


if __name__ == "__main__":
    main()
