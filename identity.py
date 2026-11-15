"""Tell vacancies apart by their application link.

Two listings are the same vacancy only when their links name the same requisition on the same
employer system. A shared job title is not enough: employers post the same title in several
offices under different requisition numbers.
"""
import hashlib
import re
import urllib.parse

# Links that go through a list or aggregator, so they do not reveal the employer's requisition.
INDIRECT = re.compile(r"(^|\.)(firstjobby\.com|go\.vansh\.nyc|grind\.fyi|csjobs\.ca|dreamworkhq\.com|simplify\.jobs|linkedin\.com|indeed\.com|"
                      r"glassdoor\.[a-z.]+|bit\.ly|lnkd\.in|tinyurl\.com)$")
# Sites whose terms or bot checks rule out automated reading. Nothing on them is fetched; their roles stay
# "not read" unless the same role is found on the employer's own board.
NO_READ = re.compile(r"(^|\.)(firstjobby\.com|csjobs\.ca|linkedin\.com|indeed\.com|glassdoor\.[a-z.]+|simplify\.jobs|dreamworkhq\.com|the-trackr\.com|"
                     r"gradcracker\.com|brightnetwork\.co\.uk|bloomberg\.com|bloomberg\.avature\.net|revolut\.com)$")
# Link shorteners used by some lists. Following one shows where the posting really lives.
SHORT = re.compile(r"(^|\.)(go\.vansh\.nyc|grind\.fyi|bit\.ly|lnkd\.in|tinyurl\.com)$")
_TRACK = re.compile(r"^(utm_.*|ref|referrer|source|src|gh_src|lever-.*|trk|trackingid|refid|s|campaign|jobboardid|codes|mode|lang|locale|"
                    r"mobile|needsredirect|iis|iisn|icims|ats|embed|type)$")
_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


def host(u):
    return urllib.parse.urlparse(u or "").netloc.lower()


def is_indirect(u):
    return bool(INDIRECT.search(host(u)))


def no_read(u):
    return bool(NO_READ.search(host(u)))


def is_short(u):
    return bool(SHORT.search(host(u)))


def nurl(u):
    """A link without tracking tags. Query values that identify the job are kept."""
    u, _, frag = (u or "").strip().lower().partition("#")
    base, _, query = u.partition("?")
    keep = sorted(p for p in query.split("&") if p and not _TRACK.match(p.split("=")[0]))
    base = re.sub(r"/(apply|application)$", "", base.rstrip("/"))
    # Some career sites put the job in the part after "#" ("/jobs#en/sites/jobsearch/job/312345"); a plain anchor is dropped.
    frag = frag if re.search(r"/|=|\d{4,}", frag) else ""
    return base + ("?" + "&".join(keep) if keep else "") + ("#" + frag if frag else "")


def vkey(u):
    """Employer system + employer + requisition for a link, or None when the link does not show one."""
    u = (u or "").strip()
    if not u or is_indirect(u):
        return None
    h, low = host(u), u.lower()
    path = urllib.parse.urlparse(u).path
    m = re.search(r"greenhouse\.io/[\w-]+/jobs/(\d+)", low) or re.search(r"[?&]gh_jid=(\d+)", low) \
        or re.search(r"greenhouse\.io/embed/job_app\?(?:[^#]*&)?token=(\d+)", low)
    if m:
        return "gh:" + m.group(1)
    m = re.search(r"lever\.co/[\w.-]+/(" + _UUID + ")", low)
    if m:
        return "lever:" + m.group(1)
    m = re.search(r"ashbyhq\.com/[^/?#]+/(" + _UUID + ")", low)
    if m:
        return "ashby:" + m.group(1)
    if h.endswith("myworkdayjobs.com") or h.endswith("myworkdaysite.com"):
        tenant = h.split(".")[0]
        if h.endswith("myworkdaysite.com"):
            t = re.search(r"/recruiting/([\w-]+)/", path)
            tenant = t.group(1).lower() if t else tenant
        last = re.sub(r"/(apply|applymanually|useMyLastApplication)$", "", path.rstrip("/"), flags=re.I).rsplit("/", 1)[-1]
        r = re.search(r"_((?:[A-Za-z]{1,6}[-_]?)?\d[\w-]*)$", last)
        if "/job/" in path and r:
            return f"wd:{tenant}:{r.group(1).lower()}"
        return None
    m = re.search(r"smartrecruiters\.com/([\w-]+)/(\d{6,})", low)
    if m:
        return "sr:" + m.group(2)
    m = re.search(r"apply\.workable\.com/([\w-]+)/j/([0-9a-f]{6,})", low)
    if m:
        return "workable:" + m.group(2)
    m = re.search(r"oraclecloud\.com/hcmui/candidateexperience/[^?#]*?/job/(\w+)", low)
    if m:
        return f"oracle:{h}:{m.group(1)}"
    m = re.search(r"careers\.oracle\.com/[^?]*#[^?]*?/job/(\d+)", low)
    if m:
        return "oraclejobs:" + m.group(1)
    m = re.search(r"\.icims\.com/jobs/(\d+)", low)
    if m:
        return f"icims:{h}:{m.group(1)}"
    m = re.search(r"/careers/job/(\d{6,})", low)
    if m:
        return f"ef:{h}:{m.group(1)}"
    m = re.search(r"/jobdetail/(?:[^/?#]+/)?(\d+)", low)
    if m and ("avature" in h or "/careers/" in low):
        return f"avature:{h}:{m.group(1)}"
    m = re.search(r"amazon\.jobs/(?:[a-z_-]+/)?jobs/(\d+)", low)
    if m:
        return "amazon:" + m.group(1)
    m = re.search(r"jobs\.apple\.com/[\w-]+/details/([\w-]+)", low)
    if m:
        return "apple:" + m.group(1)
    m = re.search(r"google\.com/about/careers/applications/jobs/results/(\d+)", low)
    if m:
        return "google:" + m.group(1)
    m = re.search(r"metacareers\.com/(?:v2/)?jobs/(\d+)", low)
    if m:
        return "meta:" + m.group(1)
    m = re.search(r"higher\.gs\.com/roles/(\d+)", low)
    if m:
        return "gs:" + m.group(1)
    m = re.search(r"ats\.rippling\.com/[\w-]+/jobs/(" + _UUID + ")", low)
    if m:
        return "rippling:" + m.group(1)
    m = re.search(r"applytojob\.com/apply/(\w+)", low)
    if m:
        return f"jazz:{h}:{m.group(1).lower()}"
    m = re.search(r"tesla\.com/careers/search/job/[\w-]*?(\d{5,})", low)
    if m:
        return "tesla:" + m.group(1)
    m = re.search(r"/job/[^/?#]+/(\d{7,})/?(?:$|\?)", low)
    if m:
        return f"sf:{h}:{m.group(1)}"
    return None


def key_of(u):
    """Strong key when the link shows a requisition, otherwise the cleaned link itself. None for list links."""
    if is_indirect(u):
        return None
    return vkey(u) or "url:" + nurl(u)


def req_label(u):
    """The requisition number as an employer would quote it, when the link shows one."""
    k = vkey(u)
    if not k:
        return ""
    last = k.rsplit(":", 1)[-1]
    return last.upper() if k.startswith("wd:") else last if len(last) <= 14 else ""


def job_id(key):
    return hashlib.sha1(("v2|" + key).encode()).hexdigest()[:12]
