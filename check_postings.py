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


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/json;q=0.9,*/*;q=0.5"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read(3_000_000).decode("utf-8", "replace")


def unescape_json(s):
    """Postings embedded in page scripts carry escaped markup; make it readable."""
    return (s.replace("\\u003c", "<").replace("\\u003e", ">").replace("\\u0026", "&")
             .replace("\\n", " ").replace("\\t", " ").replace('\\"', '"').replace("\\/", "/"))


def describe(url):
    """Return the posting's text, or '' when it cannot be read."""
    u = urllib.parse.urlparse(url)
    host, path = u.netloc.lower(), u.path

    m = re.search(r"greenhouse\.io/(?:embed/job_app/?\?for=)?([\w-]+)/jobs/(\d+)", url)
    if m:
        j = get(f"https://boards-api.greenhouse.io/v1/boards/{m.group(1)}/jobs/{m.group(2)}")
        return text(j.get("content", ""))

    m = re.search(r"jobs\.(eu\.)?lever\.co/([\w.-]+)/([0-9a-f-]{36})", url)
    if m:
        j = get(f"https://api.{'eu.' if m.group(1) else ''}lever.co/v0/postings/{m.group(2)}/{m.group(3)}")
        parts = [j.get("descriptionPlain", ""), j.get("additionalPlain", "")]
        parts += [x.get("text", "") + " " + text(x.get("content", "")) for x in j.get("lists", [])]
        return " ".join(parts)

    if host.endswith("myworkdayjobs.com"):
        seg = [s for s in path.split("/") if s]
        if seg and re.fullmatch(r"[a-z]{2}-[A-Z]{2}", seg[0]):
            seg = seg[1:]
        if len(seg) >= 3 and "job" in seg[1:]:
            i = seg.index("job", 1)
            site, rest = seg[i - 1], "/".join(seg[i + 1:])
            j = get(f"https://{host}/wday/cxs/{host.split('.')[0]}/{site}/job/{rest}")
            return text(j.get("jobPostingInfo", {}).get("jobDescription", ""))
        return ""

    m = re.search(r"jobs\.smartrecruiters\.com/([\w-]+)/(\d+)", url)
    if m:
        j = get(f"https://api.smartrecruiters.com/v1/companies/{m.group(1)}/postings/{m.group(2)}")
        sec = j.get("jobAd", {}).get("sections", {})
        return text(" ".join(v.get("text", "") for v in sec.values() if isinstance(v, dict)))

    page = text(unescape_json(fetch(url)))
    return page if len(page) > 1500 and LOOKS_LIKE_A_POSTING.search(page) else ""


def check(target):
    jid, url = target
    try:
        desc = describe(url)
    except Exception as e:  # one bad posting must not stop the run
        return jid, None, type(e).__name__
    if len(desc) < 400:
        return jid, None, "unreadable"
    sig = eligibility(desc)
    return jid, {"s": sorted(sig), "x": {k: v[:170] for k, v in sig.items()}}, None


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    targets = json.load(open(sys.argv[1]))
    if "--limit" in sys.argv:
        targets = targets[: int(sys.argv[sys.argv.index("--limit") + 1])]
    out, why = {}, {}
    start, total = time.time(), len(targets)
    with cf.ThreadPoolExecutor(8) as ex:
        for n, (jid, res, err) in enumerate(ex.map(check, targets), 1):
            if res is not None:
                out[jid] = res
            else:
                why[err] = why.get(err, 0) + 1
            progress(n, total, len(out), n - len(out), start)
    sys.stderr.write("\n")
    json.dump({"checked": time.strftime("%Y-%m-%d"), "total": total, "read": out, "not_read": why}, open(sys.argv[2], "w"))
    print(f"postings {total} | read {len(out)} | not readable {total - len(out)} {why}")


if __name__ == "__main__":
    main()
