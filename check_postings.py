#!/usr/bin/env python3
"""Open individual postings and store what each says about who can apply.

Usage: python3 check_postings.py targets.json results.json [--limit N]

targets.json is a list of [job id, posting link, job title]. For every posting that can be read,
the result holds its requirement sentences, any closing date, when it was read and how well:

  full     the employer system's own data for that exact posting (or its structured job data)
  partial  text taken from a general web page, which may include unrelated wording

A page is only accepted when it is recognisably the posting asked for. Postings that cannot be
read are left out, so the site shows them as not read rather than guessing.
"""
import concurrent.futures as cf
import datetime
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import eligibility as E
import identity as ID
from crawl import UA, get, progress, text

TIMEOUT = 25
LOOKS_LIKE_A_POSTING = re.compile(r"responsibilit|qualif|requirement|about you|what you|who you are|we are looking|you will|your role", re.I)
ATS_LINK = re.compile(r"greenhouse\.io/|lever\.co/|myworkdayjobs\.com/|jobs\.smartrecruiters\.com/|oraclecloud\.com/hcmUI/")
SHORT_LINK = ID.SHORT
_FILLER = set("intern internship interns summer winter fall autumn spring coop placement student students graduate program programme "
              "with and the for from team role position opportunity year month months 2026 2027 2028".split())


def host(u):
    return urllib.parse.urlparse(u).netloc.lower()


class NotAllowed(Exception):
    """The link leads to a site that does not allow automated reading."""


class _Polite(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if ID.no_read(newurl):
            raise NotAllowed(newurl)  # stop before the request is made
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_Polite)


def fetch(url):
    """Return (address after any redirects, page source). Sites that rule out automated reading are never opened."""
    if ID.no_read(url):
        raise NotAllowed(url)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/json;q=0.9,*/*;q=0.5"})
    with _OPENER.open(req, timeout=TIMEOUT) as r:
        return r.geturl(), r.read(3_000_000).decode("utf-8", "replace")


def job_posting_data(page):
    """(title, description) from a page's schema.org JobPosting block, when it has one."""
    for m in re.finditer(r"(?is)<script[^>]+application/ld\+json[^>]*>(.*?)</script>", page):
        try:
            data = json.loads(m.group(1).strip())
        except ValueError:
            continue
        stack = [data]
        while stack:
            x = stack.pop()
            if isinstance(x, list):
                stack += x
            elif isinstance(x, dict):
                if x.get("@type") == "JobPosting" and x.get("description"):
                    return x.get("title") or "", x["description"]
                stack += [v for v in x.values() if isinstance(v, (dict, list))]
    return None


def is_this_job(title, page_text):
    """Whether a page is recognisably the posting asked for: most of the title's distinctive words appear in it."""
    words = {w for w in re.findall(r"[a-zà-ÿ0-9+#]{3,}", (title or "").lower()) if w not in _FILLER}
    if not words:
        return True
    low = page_text.lower()
    return sum(1 for w in words if w in low) / len(words) >= 0.6


def describe(url, title="", hop=0):
    """Return (description, the posting's real address, quality). The description is '' when it cannot be read."""
    u = urllib.parse.urlparse(url)
    h, path = u.netloc.lower(), u.path

    m = re.search(r"greenhouse\.io/(?:embed/job_app/?\?for=)?([\w-]+)/jobs/(\d+)", url)
    if m:
        j = get(f"https://boards-api.greenhouse.io/v1/boards/{m.group(1)}/jobs/{m.group(2)}")
        return html.unescape(j.get("content", "")), url, "full"

    m = re.search(r"jobs\.(eu\.)?lever\.co/([\w.-]+)/([0-9a-f-]{36})", url)
    if m:
        j = get(f"https://api.{'eu.' if m.group(1) else ''}lever.co/v0/postings/{m.group(2)}/{m.group(3)}")
        parts = [j.get("description") or j.get("descriptionPlain") or ""]
        parts += [(x.get("text") or "") + "\n" + (x.get("content") or "") for x in j.get("lists", [])]
        parts.append(j.get("additional") or j.get("additionalPlain") or "")
        return "\n".join(parts), url, "full"

    if h.endswith("myworkdayjobs.com"):
        seg = [s for s in path.split("/") if s]
        if seg and re.fullmatch(r"[a-z]{2}-[A-Z]{2}", seg[0]):
            seg = seg[1:]
        if len(seg) >= 3 and "job" in seg[1:]:
            i = seg.index("job", 1)
            site, rest = seg[i - 1], "/".join(seg[i + 1:])
            j = get(f"https://{h}/wday/cxs/{h.split('.')[0]}/{site}/job/{rest}")
            return j.get("jobPostingInfo", {}).get("jobDescription", ""), url, "full"
        return "", url, "none"

    m = re.search(r"jobs\.smartrecruiters\.com/([\w-]+)/(\d+)", url)
    if m:
        j = get(f"https://api.smartrecruiters.com/v1/companies/{m.group(1)}/postings/{m.group(2)}")
        sec = j.get("jobAd", {}).get("sections", {})
        return "\n".join("<p>" + (v.get("text") or "") + "</p>" for v in sec.values() if isinstance(v, dict)), url, "full"

    m = re.search(r"([\w.-]+oraclecloud\.com)/hcmUI/CandidateExperience/[^?#]*?/sites/([\w-]+)/job/(\w+)", url)
    if m:
        # Oracle Recruiting's public candidate-experience data for one requisition.
        j = get(f"https://{m.group(1)}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails?expand=all&onlyData=true"
                f"&finder=ById;Id=%22{m.group(3)}%22,siteNumber={m.group(2)}")
        item = (j.get("items") or [{}])[0]
        parts = [v for k, v in item.items() if isinstance(v, str) and k.endswith("Str") and len(v) > 40]
        return "\n".join(parts), url, "full"

    final, raw = fetch(url)
    if hop == 0 and final != url and ATS_LINK.search(final):
        return describe(final, title, 1)  # a short link that led to an employer board: read it the proper way
    data = job_posting_data(raw)
    if data and is_this_job(title, data[0] + " " + text(data[1])[:600]):
        return html.unescape(data[1]), final, "full"
    # A general page: drop navigation and scripts, then require that it is recognisably this posting.
    body = re.sub(r"(?is)<(script|style|noscript|nav|header|footer|aside|form|svg)\b.*?</\1>", " ", raw)
    plain = text(body)
    if len(plain) > 1500 and LOOKS_LIKE_A_POSTING.search(plain) and is_this_job(title, plain):
        return body, final, "partial"
    return "", final, "none"


def check(target):
    """Return (job id, record or None, reason it was not read, real address when a short link led elsewhere)."""
    jid, url = target[0], target[1]
    title = target[2] if len(target) > 2 else ""
    try:
        desc, final, quality = describe(url, title)
    except urllib.error.HTTPError as e:
        # The employer's site refused the read, but a short link has still told us where the posting lives.
        end = getattr(e, "filename", None) or ""
        return jid, None, f"HTTP {e.code}", end if SHORT_LINK.search(host(url)) and host(end) and host(end) != host(url) else None
    except NotAllowed:
        return jid, None, "site does not allow automated reading", None
    except Exception as e:  # one bad posting must not stop the run
        return jid, None, type(e).__name__, None
    moved = final if host(final) and host(final) != host(url) else None
    req, info = E.requirements(desc)
    if info["len"] < 400:
        return jid, None, "unreadable", moved
    deadline, rolling = E.find_deadline(req)
    rec = {"url": final or url, "req": req, "deadline": deadline, "rolling": rolling, "quality": quality, "hash": info["hash"],
           "lang": info["lang"], "checked": datetime.date.today().isoformat(), "v": E.EXTRACT_VERSION}
    return jid, rec, None, moved


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
    json.dump({"checked": time.strftime("%Y-%m-%d"), "total": len(targets), "read": out, "not_read": why, "links": links}, open(sys.argv[2], "w"), ensure_ascii=False)
    full = sum(1 for r in out.values() if r["quality"] == "full")
    print(f"postings {len(targets)} | read in full {full} | partly read {len(out) - full} | not readable {len(targets) - len(out)} {why}")


if __name__ == "__main__":
    main()
