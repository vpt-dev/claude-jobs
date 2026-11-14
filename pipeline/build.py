"""Normalise every downloaded job list into one deduplicated dataset.
Usage: python3 -I build.py <raw_dir> <out_json>
"""
import json, re, sys, html, time, datetime, collections, hashlib, os

RAW, OUT = sys.argv[1], sys.argv[2]
TODAY = datetime.date.today()

US_STATES = set("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split())
CA_PROV = set("ON BC QC AB MB SK NS NB NL PE".split())
CA_CITIES = ["toronto", "vancouver", "montreal", "montréal", "waterloo", "ottawa", "calgary", "edmonton", "mississauga", "kitchener", "winnipeg", "halifax", "kanata", "markham", "burnaby", "quebec", "québec", "ontario", "british columbia", "alberta"]
UK_WORDS = ["united kingdom", "england", "scotland", "wales", "northern ireland", "london", "manchester", "edinburgh", "glasgow", "belfast", "bristol", "leeds", "birmingham, uk"]
US_WORDS = ["united states", "usa", "nyc", "new york", "san francisco", "seattle", "bay area", "chicago", "boston", "austin", "los angeles", "remote in us"]


def country_of(loc, default):
    s = loc.strip()
    l = s.lower()
    toks = set(re.findall(r"\b[A-Z]{2}\b", s))
    if "canada" in l or (toks & CA_PROV and not toks & US_STATES) or any(c in l for c in CA_CITIES):
        if "london" in l and "ON" not in toks and "canada" not in l:
            return "UK"
        return "CA"
    if re.search(r"\bUK\b", s) or any(w in l for w in UK_WORDS):
        if "london" in l and "ON" in toks:
            return "CA"
        return "UK"
    if toks & US_STATES or any(w in l for w in US_WORDS) or re.search(r"\bUS\b", s) or l in ("sf", "remote"):
        return "US"
    return default


def classify(title):
    t = " " + title.lower() + " "
    if re.search(r"quant|trader|trading|algo(rithm)? dev|strats?\b|actuar", t):
        return "Quant"
    if re.search(r"machine learning|\bml\b|\bai\b|data scien|data analy|data engineer|analytics|statistic|research scientist|deep learning|\bnlp\b|computer vision|applied scien|\bllm|biostat|\bdata\b|genai|artificial intel", t):
        return "Data, AI & Stats"
    if re.search(r"hardware|fpga|asic|embedded|firmware|electrical|rtl|silicon|\bvlsi|circuit|analog|verification engineer|\bpcb|semiconductor|mechanical|robotics hardware|photonic|\brf\b", t):
        return "Hardware"
    if re.search(r"product manage|program manage|\bapm\b|\btpm\b|product owner|product analyst|project manage", t):
        return "Product"
    return "Software"


SIMPLIFY_CAT = {"Software": "Software", "Software Engineering": "Software", "AI/ML/Data": "Data, AI & Stats",
                "Data Science, AI & Machine Learning": "Data, AI & Stats", "Quant": "Quant", "Hardware": "Hardware",
                "Product": "Product", "Product Management": "Product"}

jobs = []
ALIAS = {"NYC": "New York, NY", "New York City, NY": "New York, NY", "SF": "San Francisco, CA", "United States (Remote)": "Remote in USA", "London, United Kingdom": "London, UK", "Toronto, Canada": "Toronto, ON, Canada", "LA": "Los Angeles, CA"}


def add(src, company, title, locs, url, typ, posted=None, cat=None, salary=None, tier="", default_country="US", sponsor="", degrees=(), terms=(), elig=None):
    company = html.unescape(re.sub(r"\s+", " ", company)).strip(" *")
    title = html.unescape(re.sub(r"\s+", " ", title)).replace("🆕", "").replace("🔥", "").strip(" *")
    if not company or not title or not url.startswith("http"):
        return
    locs = [re.sub(r"\s+", " ", html.unescape(x)).strip() for x in locs if x and x.strip()]
    locs = [ALIAS.get(x, x) for x in locs]
    locs = list(dict.fromkeys(locs))
    tl = title.lower()
    if re.search(r"new grad|graduate (program|scheme|software|engineer)|\bgrad\b 20|university grad|early career|entry.level", tl) and "intern" not in tl:
        typ = "New Grad"
    elif re.search(r"\bintern(ship)?s?\b|co-?op|placement|summer 20\d\d|working student|summer (analyst|associate)|off[- ]?cycle|year in industry", tl):
        typ = "Internship"
    deg = 0
    for g in degrees or ():
        deg |= 1 if g.startswith(("Bachelor", "Associate")) else 2 if g.startswith("Master") else 4 if g == "PhD" else 0
    if re.search(r"\bph\.?d\b|doctoral", tl):
        deg |= 4
    if re.search(r"\bmaster'?s?\b|\bm\.?s\b|\bmsc\b|\bmeng\b|bs/ms|postgraduate", tl):
        deg |= 2
    if re.search(r"\bbachelor'?s?\b|\bbs\b|bs/ms|undergrad", tl):
        deg |= 1
    ts = [t for t in (terms or ()) if t and t != "N/A"]
    for m in re.finditer(r"(summer|fall|autumn|winter|spring)\s*(20\d\d)", tl):
        t = f"{m.group(1).title().replace('Autumn', 'Fall')} {m.group(2)}"
        if t not in ts:
            ts.append(t)
    if not ts and typ == "New Grad":
        m = re.search(r"\b(20(?:26|27|28))\b", tl)
        if m:
            ts.append(f"{m.group(1)} start")
    jobs.append(dict(src=src, company=company, title=title, locs=locs, url=url.strip(), type=typ, posted=posted,
                     cat=cat or classify(title), salary=salary, tier=tier, dc=default_country, sponsor=sponsor, deg=deg, terms=ts, elig=elig))


def epoch_date(e):
    try:
        return datetime.datetime.fromtimestamp(int(e), datetime.timezone.utc).date().isoformat()
    except Exception:
        return None


# ---- Simplify + vanshb03 JSON ----
for fn, src, typ in [("simplify_intern.out", "SimplifyJobs", "Internship"), ("simplify_newgrad.out", "SimplifyJobs", "New Grad"),
                     ("vansh_intern.out", "vanshb03", "Internship"), ("vansh_newgrad.out", "vanshb03", "New Grad")]:
    for x in json.load(open(f"{RAW}/{fn}")):
        if not x.get("active") or not x.get("is_visible", True):
            continue
        sp = x.get("sponsorship", "")
        sponsor = {"Does Not Offer Sponsorship": "No sponsorship", "U.S. Citizenship is Required": "Citizens only", "Offers Sponsorship": "Sponsors"}.get(sp, "")
        add(src, x.get("company_name", ""), x.get("title", ""), x.get("locations", []), x.get("url", ""), typ,
            epoch_date(x.get("date_posted")), SIMPLIFY_CAT.get(x.get("category")), sponsor=sponsor,
            degrees=x.get("degrees") or (), terms=x.get("terms") or ())


# ---- markdown table helpers ----
def cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def first_url(s):
    m = re.search(r'href="([^"]+)"', s) or re.search(r"\]\((https?://[^)\s]+)\)", s)
    return m.group(1) if m else ""


def strip_md(s):
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    return s.strip()


def split_locs(s):
    s = strip_md(s.replace("<br>", ";").replace("</br>", ";").replace("<br/>", ";"))
    s = re.sub(r"\+\d+( more)?", "", s)
    return [p.strip() for p in re.split(r";|\s{2,}", s) if p.strip()]


def parse_salary(s):
    m = re.search(r"\$([\d,.]+)\s*(k)?\s*/\s*(hr|yr)", s)
    if not m:
        return None
    v = float(m.group(1).replace(",", ""))
    if m.group(2):
        v *= 1000
    if m.group(3) == "hr":
        return {"text": f"${v:g}/hr", "annual": round(v * 2080), "cur": "USD", "hourly": True}
    return {"text": f"${v/1000:g}k/yr", "annual": round(v), "cur": "USD", "hourly": False}


def age_date(s):
    m = re.match(r"(\d+)\s*d", s.strip())
    return (TODAY - datetime.timedelta(days=int(m.group(1)))).isoformat() if m else None


def nice_date(s):
    s = s.strip()
    for f in ("%b %d, %Y", "%Y-%m-%d", "%B %d, %Y"):
        try:
            return datetime.datetime.strptime(s, f).date().isoformat()
        except ValueError:
            pass
    return None


# ---- speedyapply ----
for fn, typ, dc in [("speedy_swe", "Internship", "US"), ("speedy_swe_ng", "New Grad", "US"), ("speedy_swe_intl", "Internship", "XX"),
                    ("speedy_swe_ng_intl", "New Grad", "XX"), ("speedy_ai", "Internship", "US"), ("speedy_ai_ng", "New Grad", "US"),
                    ("speedy_ai_intl", "Internship", "XX"), ("speedy_ai_ng_intl", "New Grad", "XX")]:
    tier = ""
    force = "Data, AI & Stats" if "_ai" in fn else None
    for line in open(f"{RAW}/{fn}.md", encoding="utf-8"):
        if line.startswith("### "):
            h = line[4:].strip()
            tier = "FAANG+" if h.startswith("FAANG") else "Quant firm" if h.startswith("Quant") else ""
            continue
        if not line.startswith("|") or "---" in line[:8]:
            continue
        c = cells(line)
        if len(c) < 5 or c[0] == "Company":
            continue
        has_sal = len(c) >= 6
        url = first_url(c[4] if has_sal else c[3])
        title = strip_md(c[1])
        cat = classify(title)
        if force and cat == "Software":
            cat = force
        add("speedyapply", strip_md(c[0]), title, split_locs(c[2]), url, typ, age_date(c[-1]), cat,
            parse_salary(c[3]) if has_sal else None, tier, dc)

# ---- negarprh (Canada) ----
prev = ""
for line in open(f"{RAW}/negar.md", encoding="utf-8"):
    if not line.startswith("|"):
        continue
    c = cells(line)
    if len(c) < 5 or c[0] in ("Company", "") or set(c[0]) <= set("-: "):
        continue
    comp = strip_md(c[0])
    if comp == "↳":
        comp = prev
    prev = comp
    add("negarprh", comp, strip_md(c[1]), split_locs(c[2]), first_url(c[3]), "Internship", nice_date(c[4]), default_country="CA")

# ---- sndsh404 ----
on = False
for line in open(f"{RAW}/sndsh.md", encoding="utf-8"):
    if line.startswith("## "):
        on = line.strip() == "## the list"
    if not on or not line.startswith("|"):
        continue
    c = cells(line)
    if len(c) < 5 or c[0] == "Company" or set(c[0]) <= set("-: "):
        continue
    add("sndsh404", strip_md(c[0]), strip_md(c[1]), split_locs(c[2]), first_url(c[3]), "Internship", nice_date(c[4]))

# ---- zshah101 ----
on = False
for line in open(f"{RAW}/zshah.md", encoding="utf-8"):
    if line.startswith("## "):
        on = line.startswith(("## Summer 2027", "## Fall 2026", "## Recently posted"))
    if not on or not line.startswith("|"):
        continue
    c = cells(line)
    if len(c) < 6 or c[0] == "Company" or set(c[0]) <= set("-: "):
        continue
    comp = re.sub(r"[🆁🛂✓]|🇺🇸", "", strip_md(c[0])).strip()
    add("zshah101", comp, strip_md(c[1]), split_locs(c[3]), first_url(c[2]), "Internship", nice_date(c[5]))

# ---- LorenzoLaCorte (Europe; UK kept later) ----
sec = None
for line in open(f"{RAW}/euro.md", encoding="utf-8"):
    if line.startswith("## "):
        h = line[3:].strip()
        sec = "New Grad" if h.startswith("New Grad") else "Internship" if "Internship" in h else None
        continue
    if not sec or not line.startswith("|"):
        continue
    c = cells(line)
    if len(c) < 4 or c[0] == "company" or set(c[0]) <= set("-: "):
        continue
    add("LorenzoLaCorte", c[0].title(), c[1].title().replace(" Ai ", " AI ").replace(" Ml ", " ML "), [c[2].title()], first_url(c[3]), sec, default_country="XX")

# ---- northwesternfintech quant ----
ROLE = {"QD": "Quantitative Developer", "QR": "Quantitative Researcher", "QT": "Quantitative Trader", "SWE": "Software Engineer", "HW": "Hardware Engineer"}
comp, locs = None, []
for line in open(f"{RAW}/nu_quant.md", encoding="utf-8"):
    if line.startswith("## "):
        comp, locs = line[3:].strip(), []
    elif line.startswith("**Locations**"):
        locs = [x.strip() for x in line.split(":", 1)[1].split(",") if x.strip()]
    elif line.startswith("|") and comp:
        c = cells(line)
        if len(c) < 2 or c[0] not in ROLE:
            continue
        for label, url in re.findall(r"\[([^\]]*)\]\((https?://[^)\s]+)\)", c[1]):
            if "✅" not in label:
                continue
            var = label.replace("✅", "").strip()
            add("northwesternfintech", comp, f"{ROLE[c[0]]} Intern" + (f" ({var})" if var else ""), locs, url, "Internship",
                cat="Quant" if c[0] in ("QD", "QR", "QT") else None, tier="Quant firm")

# ---- extra lists added Nov 2026 (skipped quietly when a file is missing) ----
def _rows(name):
    path = f"{RAW}/{name}"
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        yield line.rstrip("\n")


ISO3 = {"GBR": "UK", "CAN": "Canada", "USA": "USA"}
CITY_HINT = {"London": "London, UK", "Toronto": "Toronto, ON, Canada", "Montreal": "Montreal, QC, Canada", "Vancouver": "Vancouver, BC, Canada",
             "Waterloo": "Waterloo, ON, Canada", "Cambridge UK": "Cambridge, UK", "Edinburgh": "Edinburgh, UK", "Manchester": "Manchester, UK",
             "Bristol": "Bristol, UK", "Oxford": "Oxford, UK", "New York": "New York, NY", "Chicago": "Chicago, IL", "Austin": "Austin, TX",
             "Boston": "Boston, MA", "San Francisco": "San Francisco, CA", "Houston": "Houston, TX", "Miami": "Miami, FL", "Greenwich": "Greenwich, CT",
             "Philadelphia": "Philadelphia, PA", "Bala Cynwyd": "Bala Cynwyd, PA", "Seattle": "Seattle, WA", "Los Angeles": "Los Angeles, CA"}


def iso_loc(s):
    return re.sub(r",\s*([A-Z]{3})$", lambda m: ", " + ISO3.get(m.group(1), m.group(1)), s.strip())


# Emjumaev big-tech trackers: one "## Company" section per employer
for fn in ("emj_us.md", "emj_eu.md"):
    comp = ""
    for line in _rows(fn):
        if line.startswith("## "):
            comp = line[3:].strip()
            continue
        if not line.startswith("| [") or not comp:
            continue
        c = cells(line)
        if len(c) < 5:
            continue
        deg = c[2].lower()
        add("emjumaev", comp, strip_md(c[0]), [iso_loc(x) for x in split_locs(c[3])], first_url(c[0]), "Internship", nice_date(c[4]),
            default_country="XX", degrees=tuple(d for d, k in (("PhD", "phd"), ("Master's", "master"), ("Bachelor's", "bachelor")) if k in deg))

# frogg Canadian internships: Company | Role | Location | Apply | Date | Term
for line in _rows("frogg.md"):
    c = cells(line) if line.startswith("|") else []
    if len(c) < 6 or c[0] in ("Company", "") or set(c[0]) <= set("-: ") or not first_url(c[3]):
        continue
    term = c[5] if re.search(r"20\d\d", c[5]) else ""
    add("frogg", strip_md(c[0]), strip_md(c[1]), split_locs(c[2].replace(", Remote in Canada", "")), first_url(c[3]), "Internship", nice_date(c[4]),
        default_country="CA", terms=(term,) if term else ())

# Toronto AI/ML radar (MIT licence): Role | Company | Location | Term | Posted
for line in _rows("krishi.md"):
    c = cells(line) if line.startswith("| [") else []
    if len(c) < 5:
        continue
    term = c[3] if re.search(r"20\d\d", c[3]) else ""
    add("toronto-radar", strip_md(c[1]), strip_md(c[0]), split_locs(c[2]), first_url(c[0]), "Internship", age_date(c[4].replace(" days ago", "d").replace(" day ago", "d")),
        default_country="CA", terms=(term,) if term else ())

# Francklin Canada list: Company | Role | Location | Details | Posted | Apply
typ = "Internship"
for line in _rows("francklin.md"):
    if line.startswith("#"):
        typ = "New Grad" if "new-grad" in line.lower() or "new grad" in line.lower() else "Internship"
        continue
    c = cells(line) if line.startswith("|") else []
    if len(c) < 6 or c[0] in ("Company", "") or set(c[0]) <= set("-: ") or not first_url(c[5]):
        continue
    add("francklin", strip_md(c[0]), re.sub(r"^NEW\s+", "", strip_md(c[1])), split_locs(c[2]), first_url(c[5]), typ, nice_date(c[4].split("<")[0]), default_country="CA")

# QuantScraper student list: Company | Role | Location | (Focus) | Salary | Posted
typ, prev = "Internship", ""
for line in _rows("quantscraper.md"):
    if line.startswith("#"):
        low = line.lower()
        typ = "New Grad" if "graduate" in low or "new grad" in low else "Internship" if "intern" in low else typ
        continue
    c = cells(line) if line.startswith("|") else []
    if len(c) < 5 or "](http" not in c[1]:
        continue
    comp = strip_md(c[0])
    comp = prev if comp == "↳" else comp
    prev = comp
    locs = [CITY_HINT.get(x.strip(), x.strip()) for x in strip_md(c[2]).split(",")]
    add("quantscraper", comp, strip_md(c[1]), locs, first_url(c[1]), typ, None, cat="Quant", default_country="XX")

# aprameyak: Company | Role | Location | Education | Link | Date
prev = ""
for line in _rows("aprameyak.md"):
    c = cells(line) if line.startswith("|") else []
    if len(c) < 6 or c[0] in ("Company", "") or set(c[0]) <= set("-: ") or not first_url(c[4]):
        continue
    comp = strip_md(c[0]); comp = prev if comp == "↳" else comp; prev = comp
    edu = c[3].lower()
    add("aprameyak", comp, strip_md(c[1]), split_locs(c[2]), re.sub(r"[?&]utm_source=aprameyak", "", first_url(c[4])), "Internship", None,
        degrees=tuple(d for d, k in (("PhD", "phd"), ("Master's", "master"), ("Bachelor's", "undergrad")) if k in edu))

# michelleokolie Canada list: Company | Role | Location | Link | Date
_prev_mo = ""
for line in _rows("michelle.md"):
    c = cells(line) if line.startswith("|") else []
    if len(c) < 5 or c[0] in ("Company", "") or set(c[0]) <= set("-: ") or not first_url(c[3]):
        continue
    if strip_md(c[0]) == "↳":
        c[0] = _prev_mo
    _prev_mo = c[0]
    add("michelleokolie", strip_md(c[0]), strip_md(c[1]), split_locs(c[2]), first_url(c[3]), "Internship", nice_date(c[4]), default_country="CA")

# mazentalsam / csjobs.ca: Company | Role | Location | Apply | Posted
typ, _prev_cs = "Internship", ""
for line in _rows("mazen.md"):
    if line.startswith("#"):
        typ = "New Grad" if re.search(r"new.?grad|graduate|full.?time", line, re.I) else "Internship" if re.search(r"intern|co-?op", line, re.I) else typ
        continue
    c = cells(line) if line.startswith("|") else []
    if len(c) < 5 or not first_url(c[3]) or strip_md(c[0]) in ("Company", ""):
        continue
    if strip_md(c[0]) == "↳":
        c[0] = _prev_cs
    _prev_cs = c[0]
    add("csjobs", strip_md(c[0]), strip_md(c[1]), split_locs(c[2]), re.sub(r"\?utm_.*$", "", first_url(c[3])), typ, None, default_country="CA")

# dreamworkhq country pages: Company | Role | Location | Pay | Added
for fn, dc in (("dw_uk.md", "UK"), ("dw_ca.md", "CA")):
    for line in _rows(fn):
        c = cells(line) if line.startswith("| **") or line.startswith("| [") else []
        if len(c) < 4 or "](http" not in c[1]:
            continue
        loc = ", ".join(reversed([x.strip() for x in strip_md(c[2]).split(",")]))  # "Canada, Ottawa" -> "Ottawa, Canada"
        add("dreamworkhq", strip_md(c[0]), strip_md(c[1]), [loc], re.sub(r"\?utm_.*$", "", first_url(c[1])), "Internship", age_date(c[4]) if len(c) > 4 else None, default_country=dc)

# grind.fyi UK and Canada feeds:  | flag | Company | [Role](link) | Location | Extracted |
for fn, typ, dc in (("grind_uk.md", "Internship", "UK"), ("grind_ca.md", "Internship", "CA"), ("grind_uk_ng.md", "New Grad", "UK"), ("grind_ca_ng.md", "New Grad", "CA")):
    for line in _rows(fn):
        c = cells(line) if line.startswith("|") else []
        if len(c) < 5 or "](https://grind.fyi/j?" not in c[2]:
            continue
        comp = strip_md(c[1])
        comp = comp.title() if comp.islower() else comp  # some names are lower-case board names
        add("grind.fyi", comp, strip_md(c[2]), split_locs(c[3]), re.sub(r"&utm_.*$", "", first_url(c[2])), typ, nice_date(c[4]), default_country=dc)

# ---- employer boards crawled from the user's machine (crawl.py output) ----
for _fn in ("ats_jobs.json", "reed_jobs.json"):
    if not os.path.exists(f"{RAW}/{_fn}"):
        continue
    for x in json.load(open(f"{RAW}/{_fn}"))["jobs"]:
        pay, sal = x.get("pay"), None
        if pay and pay.get("cur") == "USD" and pay.get("min"):
            v = (pay["min"] + (pay.get("max") or pay["min"])) / 2
            if pay.get("period") == "hour" and 10 <= v <= 150:
                sal = {"text": f"${v:g}/hr", "annual": round(v * 2080), "cur": "USD", "hourly": True}
            elif pay.get("period") == "year" and 20000 <= v <= 600000:
                sal = {"text": f"${v/1000:g}k/yr", "annual": round(v), "cur": "USD", "hourly": False}
        read = bool(x.get("elig")) or x.get("ats") in ("greenhouse", "lever", "ashby", "reed")
        add("Reed" if x.get("ats") == "reed" else "employer-site", x["company"], x["title"], x.get("locations") or [], x["url"], x.get("type") or "Internship", (x.get("posted") or "")[:10] or None,
            salary=sal, default_country=(x.get("countries") or ["US"])[0], elig=(x.get("elig") or {}) if read else None)

# ---- collected by hand from employer career sites ----
import os
if os.path.exists(f"{RAW}/manual.json"):
    for x in json.load(open(f"{RAW}/manual.json")):
        add("Employer site", x["company"], x["title"], x["locs"], x["url"], x["type"], tier="FAANG+", default_country="XX")

# ---- country + dedupe ----
def nc(s):
    s = re.sub(r"[^a-z0-9 ]", "", s.lower())
    return re.sub(r"\b(inc|llc|ltd|corp|corporation|co|company|group|technologies|technology|the)\b", "", s).replace(" ", "")


def nt(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


_TRACK = re.compile(r"^(utm_.*|ref|referrer|source|src|gh_src|lever-.*|trk|trackingid|refid|s|campaign|jobboardid|codes|mode|lang|locale)$")


def nurl(u):
    """A posting's address without tracking tags. Query values that identify the job are kept."""
    u = u.lower().split("#")[0]
    base, _, query = u.partition("?")
    keep = sorted(p for p in query.split("&") if p and not _TRACK.match(p.split("=")[0]))
    base = re.sub(r"/(apply|application)$", "", base.rstrip("/"))
    return base + ("?" + "&".join(keep) if keep else "")


INDIRECT = r"go\.vansh\.nyc|linkedin\.com|dreamworkhq\.com|csjobs\.ca|simplify\.jobs|grind\.fyi"
ELIG_OUT = {}
merged, by_url = {}, {}
dropped = 0
for j in jobs:
    cs = []
    for l in j["locs"]:
        c = country_of(l, j["dc"])
        if c not in cs:
            cs.append(c)
    if not j["locs"]:
        cs = [j["dc"]]
    keep = [c for c in cs if c in ("US", "CA", "UK")]
    if not keep:
        dropped += 1
        continue
    j["countries"] = keep
    j["locs"] = [l for l in j["locs"] if country_of(l, j["dc"]) in keep][:8]
    key = (nc(j["company"]), nt(j["title"]), j["type"])
    k2 = by_url.get(nurl(j["url"]))
    tgt = merged.get(key) or (merged.get(k2) if k2 else None)
    if tgt is None:
        j["srcs"] = [j["src"]]
        merged[key] = j
        by_url[nurl(j["url"])] = key
        continue
    if j["src"] not in tgt["srcs"]:
        tgt["srcs"].append(j["src"])
    for l in j["locs"]:
        if l not in tgt["locs"] and len(tgt["locs"]) < 8:
            tgt["locs"].append(l)
    for c in j["countries"]:
        if c not in tgt["countries"]:
            tgt["countries"].append(c)
    if j["salary"] and not tgt["salary"]:
        tgt["salary"] = j["salary"]
    if j["tier"] and not tgt["tier"]:
        tgt["tier"] = j["tier"]
    if j["sponsor"] and not tgt["sponsor"]:
        tgt["sponsor"] = j["sponsor"]
    tgt["deg"] |= j["deg"]
    if j["elig"] is not None and tgt["elig"] is None:
        tgt["elig"] = j["elig"]
    for t in j["terms"]:
        if t not in tgt["terms"]:
            tgt["terms"].append(t)
    if j["posted"] and (not tgt["posted"] or j["posted"] < tgt["posted"]):
        tgt["posted"] = j["posted"]
    # prefer a direct employer link over a redirect/short link
    if re.search(INDIRECT, tgt["url"]) and not re.search(INDIRECT, j["url"]):
        tgt["url"] = j["url"]

BAR_US = 95000  # about 1.47x the US median, the same multiple as 60,000 pounds over the UK median
# Names are matched after nc(): lower case, no spaces or punctuation.
QUANT = re.compile(r"^(janestreet|citadel|citadelsecurities|hudsonrivertrading|jumptrading|twosigma|optiver|imc|imctrading|drw|susquehanna|sig$|deshaw|gresearch|xtx|towerresearch|fiverings|virtu|akuna|quberesearch|squarepoint|millennium|point72|cubist|man$|manahl|marshallwace|brevanhoward|schonfeld|dvtrading|wintermute|radixtrading|oldmission|belvedere|renaissance|pdtpartners|headlands|balyasny|capula|maven|flowtraders|tgsmanagement|voleon|aquatic|jainglobal|quantco|arrowstreet|chicagotrading|wolverine|geneva|3red|blackedge)")
TECH = re.compile(r"^(google|deepmind|meta$|metaplatforms|apple$|amazon|aws|microsoft|netflix|nvidia|openai|anthropic|stripe|databricks|snowflake|palantir|bloomberg|tiktok|bytedance|uber$|airbnb|doordash|figma|ramp$|roblox|snap$|twitch|pinterest|datadog|lyft|xai$|scaleai|anduril|waymo|cohere|mistral|rippling|notion|plaid|coinbase|robinhood|linkedin|salesforce|adobe)")
UK_CITED = re.compile(r"^(janestreet|citadel|citadelsecurities|gresearch|optiver)")
CA_CITED = re.compile(r"^(google|amazon|aws|stripe|airbnb|snowflake|shopify|databricks|meta$|metaplatforms|doordash|nvidia)")
CA_LIKELY = re.compile(r"^(wealthsimple|atlassian|veeva|okta|cohere)")
MEDIAN = {"US": 64064, "UK": 40911, "CA": 68640}
import statistics
# Pay estimates: the median of the same employer's stated pay for the same role type (US listings only).
pool = collections.defaultdict(list)
for j in merged.values():
    if j["salary"]:
        pool[(nc(j["company"]), j["type"])].append(j["salary"])
# ---- second pass: match roles known only through a list's own link to the employer's posting ----
_STOP = re.compile(r"\b(20\d\d|summer|winter|fall|autumn|spring|intern(ship)?s?|co-?op|student|months?|term|new|grad(uate)?|the|and|of|for|in|a|an|\d+)\b")


def _toks(t):
    return frozenset(re.findall(r"[a-z0-9+#]+", _STOP.sub(" ", t.lower())))


_direct = collections.defaultdict(list)
for _k, _j in merged.items():
    if not re.search(INDIRECT, _j["url"]):
        _direct[(_k[0], _j["type"])].append(_j)
folded = 0
for _k in list(merged):
    _j = merged[_k]
    if not re.search(INDIRECT, _j["url"]):
        continue
    _a, _best, _score = _toks(_j["title"]), None, 0
    for _d in _direct.get((_k[0], _j["type"]), ()):
        _b = _toks(_d["title"])
        _s = len(_a & _b) / max(1, len(_a | _b))
        if _s > _score and set(_d["countries"]) & set(_j["countries"]):
            _best, _score = _d, _s
    if _best is None or _score < 0.85 or not _a:
        continue
    for _src in _j["srcs"]:
        if _src not in _best["srcs"]:
            _best["srcs"].append(_src)
    for _l in _j["locs"]:
        if _l not in _best["locs"] and len(_best["locs"]) < 8:
            _best["locs"].append(_l)
    for _t in _j["terms"]:
        if _t not in _best["terms"]:
            _best["terms"].append(_t)
    _best["deg"] |= _j["deg"]
    if _j["posted"] and (not _best["posted"] or _j["posted"] < _best["posted"]):
        _best["posted"] = _j["posted"]
    del merged[_k]
    folded += 1
print("list-only roles matched to an employer posting:", folded)

out = []
for j in merged.values():
    s, est = j["salary"], 0
    if not s and "US" in j["countries"]:
        ps = pool.get((nc(j["company"]), j["type"]))
        if ps:
            a = round(statistics.median(p["annual"] for p in ps))
            hourly = all(p["hourly"] for p in ps)
            s = {"text": f"${round(a/2080)}/hr" if hourly else f"${round(a/1000)}k/yr", "annual": a}
            est = len(ps)
    above = bool(s) and "US" in j["countries"] and s["annual"] > MEDIAN["US"]
    # Pay bar: 2 = evidence it clears the bar, 1 = likely (firm type or estimate), 0 = no evidence.
    cn, vs = nc(j["company"]), []
    for c in j["countries"]:
        v = 0
        if c == "US":
            if s and s["annual"] >= BAR_US:
                v = 1 if est else 2
            elif not s and (QUANT.search(cn) or TECH.search(cn)):
                v = 1
        elif c == "UK":
            v = 2 if UK_CITED.search(cn) else 1 if (QUANT.search(cn) or TECH.search(cn)) else 0
        elif c == "CA":
            v = 2 if CA_CITED.search(cn) else 1 if (QUANT.search(cn) or TECH.search(cn) or CA_LIKELY.search(cn)) else 0
        vs.append(v)
    # Evidence in one country does not prove another: only call it confirmed if every country is.
    hp = 2 if vs and min(vs) == 2 else 1 if vs and max(vs) >= 1 else 0
    out.append([j["company"], j["title"], j["locs"], j["countries"], j["type"], j["cat"], j["url"], j["posted"] or "",
                s["text"] if s else "", s["annual"] if s else 0, j["tier"], j["sponsor"], j["srcs"],
                1 if above else 0, est, hp, j["deg"], j["terms"][:4],
                hashlib.sha1(f"{cn}|{nt(j['title'])}|{j['type']}".encode()).hexdigest()[:12]])
    if j.get("elig") is not None:
        ELIG_OUT[out[-1][18]] = {"s": sorted(j["elig"]), "x": {k: v[:170] for k, v in j["elig"].items()}}
out.sort(key=lambda r: r[7], reverse=True)
json.dump(out, open(OUT, "w"), ensure_ascii=False, separators=(",", ":"))
json.dump({"checked": TODAY.isoformat(), "total": len(ELIG_OUT), "read": ELIG_OUT}, open(os.path.join(os.path.dirname(OUT) or ".", "elig_crawl.json"), "w"), ensure_ascii=False)

C = collections.Counter
print("raw rows", len(jobs), "| outside US/CA/UK dropped", dropped, "| unique jobs", len(out))
print("country", C(c for r in out for c in r[3]))
print("type", C(r[4] for r in out))
print("cat", C(r[5] for r in out))
print("stated pay", sum(1 for r in out if r[9] and not r[14]), "estimated", sum(1 for r in out if r[14]), "above US median", sum(r[13] for r in out))
print("pay bar", {c: C(r[15] for r in out if c in r[3]) for c in ("US","UK","CA")})
print("sources", C(s for r in out for s in r[12]))
print("multi-source", sum(1 for r in out if len(r[12]) > 1))
print("deg", C(r[16] for r in out)); print("terms", C(t for r in out for t in r[17]).most_common(12)); print("sponsor", C(r[11] for r in out)); print("unique ids", len(set(r[18] for r in out)))
print("no date", sum(1 for r in out if not r[7]))
