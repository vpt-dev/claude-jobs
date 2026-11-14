"""Normalise every downloaded job list into one deduplicated dataset.
Usage: python3 -I build.py <raw_dir> <out_json>
"""
import json, re, sys, html, time, datetime, collections, hashlib, os

RAW, OUT = sys.argv[1], sys.argv[2]
TODAY = datetime.date.today()

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import eligibility as E  # noqa: E402
import identity as ID  # noqa: E402
import places as PL  # noqa: E402

DATA = sys.argv[3] if len(sys.argv) > 3 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")


def stored(name, default):
    path = os.path.join(DATA, name)
    try:
        return json.load(open(path)) if os.path.exists(path) else default
    except ValueError:
        return default


# Short links (go.vansh.nyc, grind.fyi) that an earlier run followed to the employer's posting.
LINKS = stored("links.json", {})
PARSED = collections.Counter()  # listings read from each source, before any merging


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
    if re.search(r"software|developer|engineer|programm|full.?stack|front.?end|back.?end|\bweb\b|mobile|\bios\b|android|devops|\bsre\b|cloud|platform|"
                 r"security|cyber|\bqa\b|\btest|infrastructure|systems?\b|\bit\b|technolog|technical|\bswe\b|\bsde\b|comput|automation|network|digital|"
                 r"d[ée]veloppeu|logiciel", t):
        return "Software"
    return "Other"  # not guessed: a title that names no field is left unclassified


SIMPLIFY_CAT = {"Software": "Software", "Software Engineering": "Software", "AI/ML/Data": "Data, AI & Stats",
                "Data Science, AI & Machine Learning": "Data, AI & Stats", "Quant": "Quant", "Hardware": "Hardware",
                "Product": "Product", "Product Management": "Product"}

jobs = []
ALIAS = {"NYC": "New York, NY", "New York City, NY": "New York, NY", "SF": "San Francisco, CA", "United States (Remote)": "Remote in USA", "London, United Kingdom": "London, UK", "Toronto, Canada": "Toronto, ON, Canada", "LA": "Los Angeles, CA"}


def add(src, company, title, locs, url, typ, posted=None, cat=None, salary=None, tier="", default_country="US", sponsor="", degrees=(), terms=(), evidence=None, countries=None, deadline="", local=None):
    company = html.unescape(re.sub(r"\s+", " ", company)).strip(" *")
    title = html.unescape(re.sub(r"\s+", " ", title)).replace("🆕", "").replace("🔥", "").strip(" *")
    if not company or not title or not url.startswith("http"):
        return
    PARSED[src] += 1
    url = LINKS.get(ID.nurl(url), url)
    locs = [re.sub(r"\s+", " ", html.unescape(x)).strip() for x in locs if x and x.strip()]
    locs = [ALIAS.get(x, x) for x in locs]
    locs = list(dict.fromkeys(locs))
    tl = title.lower()
    if re.search(r"full[- ]?time (analyst|associate)", tl) or (
            re.search(r"new grad|graduate (program|scheme|software|engineer)|\bgrad\b 20|university grad|early career|entry.level", tl) and "intern" not in tl):
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
    for season, year in E.seasons_in(title):  # "Summer 2027", "Winter Co-op 2027", "2027 Summer", "Summer/Fall 2027"
        t = f"{season.title()} {year}"
        if t not in ts:
            ts.append(t)
    if not ts and typ == "New Grad":
        m = re.search(r"\b(20(?:26|27|28))\b", tl)
        if m:
            ts.append(f"{m.group(1)} start")
    jobs.append(dict(src=src, company=company, title=title, locs=locs, url=url.strip(), type=typ, posted=posted,
                     cat=cat or classify(title), salary=salary, tier=tier, dc=default_country, sponsor=sponsor, deg=deg, terms=ts, ev=evidence, fixed=countries, deadline=deadline or "",
                     local=default_country in ("UK", "CA") if local is None else local))


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
    """The link a table cell points to. A badge image inside the link ("[![Apply](badge.svg)](real link)") is not the link."""
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)
    s = re.sub(r"<img\b[^>]*>", "", s)
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


FX = {"USD": 1.0, "GBP": 1.27, "CAD": 0.73}  # rough conversion, used only to sort and filter mixed currencies
SYMBOL = {"USD": "$", "GBP": "£", "CAD": "C$"}


def pay_from(pay):
    """Pay as stated by an employer system, kept in its own currency and period."""
    if not pay or pay.get("cur") not in FX or not pay.get("min"):
        return None
    v = (pay["min"] + (pay.get("max") or pay["min"])) / 2
    sym, per = SYMBOL[pay["cur"]], pay.get("period")
    if per == "hour" and 8 <= v <= 200:
        return {"text": f"{sym}{v:g}/hr", "annual": round(v * 2080), "cur": pay["cur"], "hourly": True}
    if per == "year" and 12000 <= v <= 900000:
        return {"text": f"{sym}{v/1000:g}k/yr", "annual": round(v), "cur": pay["cur"], "hourly": False}
    if per == "month" and 800 <= v <= 30000:
        return {"text": f"{sym}{round(v):,}/month", "annual": round(v * 12), "cur": pay["cur"], "hourly": False}
    if per == "day" and 60 <= v <= 1500:
        return {"text": f"{sym}{round(v)}/day", "annual": round(v * 230), "cur": pay["cur"], "hourly": False}
    return None


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
        if force and cat in ("Software", "Other"):
            cat = force
        # The plain lists are the US edition, so "Remote" there means remote in the US; the others cover everywhere else.
        add("speedyapply", strip_md(c[0]), title, split_locs(c[2]), url, typ, age_date(c[-1]), cat,
            parse_salary(c[3]) if has_sal else None, tier, dc, local=dc == "US")

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
        typ = "New Grad" if "graduate" in low or "new grad" in low else "Internship" if re.search(r"intern|programme|insight", low) else typ
        continue
    c = cells(line) if line.startswith("|") else []
    if len(c) < 5 or "](http" not in c[1] or "quant-scraper.com/quant?" in c[1]:
        continue
    comp = strip_md(c[0])
    comp = prev if comp == "↳" else comp
    prev = comp
    if re.search(r"·\s*[A-Z][a-z]{2} \d{1,2}, 20\d\d\s*\]|/events?/|#event-", c[1]):
        continue  # a dated talk or coffee chat, not a vacancy
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
    _doc = json.load(open(f"{RAW}/{_fn}"))
    _when = (_doc.get("fetched_at") or TODAY.isoformat())[:10]
    for x in _doc["jobs"]:
        if "quality" in x:
            ev = None if x["quality"] == "none" else {
                "url": x["url"], "req": x.get("req") or [], "deadline": x.get("deadline") or "", "rolling": bool(x.get("rolling")),
                "quality": x["quality"], "hash": x.get("hash") or "", "lang": x.get("lang") or "", "checked": x.get("seen") or _when, "v": E.EXTRACT_VERSION}
        else:  # written before whole requirement sentences were stored: only short fragments survive
            read = bool(x.get("elig")) or x.get("ats") in ("greenhouse", "lever", "ashby")
            ev = {"url": x["url"], "legacy": x.get("elig") or {}, "quality": "partial", "checked": _when, "v": 1} if read else None
        reed = x.get("ats") == "reed"
        # The crawler works countries out from the employer system's own fields. Rows written by the earlier crawler assumed
        # the US whenever a location was unclear, so those are read again from their location text.
        add("Reed" if reed else "employer-site", x["company"], x["title"], x.get("locations") or [], x["url"],
            x.get("type") or "Internship", (x.get("posted") or "")[:10] or None, salary=pay_from(x.get("pay")),
            default_country="UK" if reed else "??", evidence=ev, deadline=x.get("deadline") or "",
            countries=(x.get("countries") or ["??"]) if "quality" in x and not reed else None)

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


_STOP = re.compile(r"\b(20\d\d|summer|winter|fall|autumn|spring|intern(ship)?s?|co-?op|student|months?|term|new|grad(uate)?|the|and|of|for|in|a|an|\d+|"
                   r"uk|usa|us|canada|england|london|toronto|remote|hybrid|office|onsite)\b")


def _toks(t):
    return frozenset(re.findall(r"[a-z0-9+#]+", _STOP.sub(" ", t.lower())))


def better(a, b):
    """The more useful of two evidence records: newer extraction, then a full read, then the more recent."""
    if not a or not b:
        return a or b
    rank = lambda e: (e.get("v", 1), e.get("quality") == "full", e.get("checked", ""))
    return b if rank(b) > rank(a) else a


# 1. Countries. A location that cannot be worked out is kept as unknown ("??"), never guessed.
def title_places(title):
    """Fragments of a title that may name a place: "Software Engineer Intern - London", "Graduate Developer (Manchester)"."""
    return [f.strip() for f in re.split(r"\s+[-–—|@]\s+|[,():/]|\s+in\s+", re.sub(r"\b20\d\d\b", " ", title)) if f.strip()][1:]


LONDON = re.compile(r"london|canary wharf|croydon|uxbridge|hounslow|wembley|ealing|kingston upon thames|westminster|shoreditch|paddington|"
                    r"king'?s cross|hammersmith|greenwich|stratford|richmond upon thames|twickenham|bromley|harrow|ilford|romford", re.I)
TORONTO = re.compile(r"toronto|mississauga|markham|brampton|vaughan|richmond hill|oakville|scarborough|north york|etobicoke|pickering|\bajax\b|whitby|"
                     r"oshawa|burlington|milton|newmarket|aurora|thornhill|concord|woodbridge|\bgta\b", re.I)
REMOTE = re.compile(r"remote|home[- ]based|work from home|t[ée]l[ée]travail|anywhere in", re.I)


def scope_of(j, default, local):
    """Where a role sits for the shortlist's place chips: lon, gta, remote, uk (elsewhere in the UK), ca (elsewhere in Canada), unk."""
    cs, out = j["countries"], []

    def add(x):
        if x not in out:
            out.append(x)

    if "??" in cs:
        add("unk")
    for l in j["locs"]:
        codes = PL.codes_of(l, default, local, known=cs)
        remote = bool(REMOTE.search(l))
        named = [c for c in codes if c in ("UK", "CA")] or ([c for c in cs if c in ("UK", "CA")] if codes == ["??"] and len(cs) == 1 else [])
        for c in named:
            if remote:
                add("remote")
            if c == "UK" and LONDON.search(l):
                add("lon")
            elif c == "CA" and TORONTO.search(l):
                add("gta")
            elif not remote:
                add("uk" if c == "UK" else "ca")
    # A country with no usable location behind it ("UK" from the source list alone) is shown under "elsewhere".
    if "UK" in cs and not ({"lon", "uk", "remote"} & set(out)):
        add("uk")
    if "CA" in cs and not ({"gta", "ca", "remote"} & set(out)):
        add("ca")
    return out


rows, dropped, from_link, from_title = [], 0, 0, 0
for j in jobs:
    default = j["dc"] if j["dc"] in ("US", "UK", "CA", "XX") else None
    local = bool(j.get("local")) and default in ("US", "UK", "CA")  # a list that covers one country only
    if j.get("fixed"):
        cs = list(j["fixed"])
    else:
        cs = PL.countries(j["locs"], (), default, local)
    if cs == ["??"]:
        # The location column did not say. A Workday link carries the place in its path; failing that, the title may name it.
        place = PL.url_place(j["url"])
        got = PL.from_text([place]) if place else None
        if got is not None:
            from_link += 1
        else:
            got = PL.from_text(title_places(j["title"]))
            from_title += got is not None
        if got is not None:
            cs = got
            if place and got and not j["locs"]:
                j["locs"] = [place]
    if not cs:
        dropped += 1  # recognisably somewhere else
        continue
    j["countries"] = cs
    # Show only the locations that belong to the kept countries (a posting may also list Berlin or Singapore).
    mine = [l for l in j["locs"] if set(PL.codes_of(l, default, local, known=cs)) & (set(cs) | {"??"})]
    j["locs"] = [l for l in (mine or j["locs"]) if re.search(r"[A-Za-zÀ-ÿ]", l)][:8]  # a dash or a bare number is not a place
    # The town, for telling apart same-titled roles. A title such as "... Intern - London, UK" supplies it when the location does not.
    j["cities"] = PL.city_keys(j["locs"]) or PL.city_keys([f for f in title_places(j["title"]) if PL.classify(f)[0][0] in ("US", "UK", "CA")])
    j["scope"] = scope_of(j, default, local)
    rows.append(j)
print("country taken from the link:", from_link, "| from the title:", from_title)

# 2. Identity. A vacancy is its requisition on its employer system (see identity.py). Listings are merged
#    only when their links name the same requisition; a shared title is not enough.
groups, by_key = [], {}


def start(j, key):
    j["key"], j["srcs"], j["alts"] = key, [j["src"]], []
    groups.append(j)
    by_key[key] = j
    return j


def also(g, url):
    """Remember another application link for the same vacancy."""
    if url and url != g["url"] and url not in g["alts"] and ID.nurl(url) != ID.nurl(g["url"]) and len(g["alts"]) < 4:
        g["alts"].append(url)


def overlap(a, b):
    """Whether two country lists can describe the same job; an unknown location does not rule it out."""
    return bool(set(a) & set(b)) or "??" in a or "??" in b


def absorb(g, j, same_posting):
    """Fold listing j into vacancy g. Locations are only combined when both links name the same requisition."""
    if j["src"] not in g["srcs"]:
        g["srcs"].append(j["src"])
    if same_posting or not g["locs"]:
        for l in j["locs"]:
            if l not in g["locs"] and len(g["locs"]) < 8:
                g["locs"].append(l)
        for c in j["countries"]:
            if c not in g["countries"] and c != "??":
                g["countries"].append(c)
        if len(g["countries"]) > 1 and "??" in g["countries"]:
            g["countries"].remove("??")
        g["cities"] = g["cities"] | j["cities"]
        g["scope"] = [x for x in g["scope"] if x != "unk" or "??" in g["countries"]] + [x for x in j["scope"] if x not in g["scope"] and (x != "unk" or "??" in g["countries"])]
    for k in ("salary", "tier", "sponsor", "deadline"):
        if j.get(k) and not g.get(k):
            g[k] = j[k]
    g["deg"] |= j["deg"]
    for t in j["terms"]:
        if t not in g["terms"]:
            g["terms"].append(t)
    if j["posted"] and (not g["posted"] or j["posted"] < g["posted"]):
        g["posted"] = j["posted"]
    g["ev"] = better(g.get("ev"), j.get("ev"))
    if same_posting and j["src"] == "employer-site" and g["src"] != "employer-site" and not g.get("own_title"):
        g["title"], g["own_title"] = j["title"], True  # the employer's own wording, over a list's version of it


def likeness(a, b):
    """How alike two titles are, from 0 to 1, ignoring season and year words."""
    if nt(a) == nt(b):
        return 1.0
    ta, tb = _toks(a), _toks(b)
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def link_kind(key):
    """How much a plain web link says on its own: "id" (carries a job number), "slug" (a descriptive page name) or "page"."""
    path = re.sub(r"^url:https?://[^/]+", "", key)
    if re.search(r"\d{5,}|[0-9a-f]{8}-[0-9a-f]{4}-", path):
        return "id"
    last = [x for x in re.split(r"[/?#=&]", path) if x][-1:] or [""]
    return "slug" if len([w for w in re.split(r"[-_+.]", last[0]) if w]) >= 3 else "page"


later, weak = [], []
for j in rows:
    key = ID.key_of(j["url"])
    if key is None:
        later.append(j)  # a link through a list site: it does not show the requisition
    elif key.startswith("url:"):
        weak.append((key, "-".join(sorted(_toks(j["title"]))) or nt(j["title"]), j))
    elif key in by_key:
        absorb(by_key[key], j, True)
    else:
        start(j, key)
# A plain web link with a job number in it is one vacancy. Without one, the title has to agree as well: some employers
# send every role to one general page ("/careers/apply"), and those roles must stay separate.
NEED = {"id": 0.0, "slug": 0.3, "page": 0.7}
by_link = collections.defaultdict(list)
for key, sig, j in sorted(weak, key=lambda w: (w[0], w[1])):
    kind = link_kind(key)
    twin = next((g for g in by_link[key] if likeness(g["title"], j["title"]) >= NEED[kind]), None)
    if twin is not None:
        absorb(twin, j, True)
    else:
        k = key if kind == "id" else key + "|" + sig
        while k in by_key:
            k += "+"
        by_link[key].append(start(j, k))

# 3. Listings whose link does not show a requisition are attached to an employer posting only when the
#    employer, title, type and place all agree and there is no doubt which posting is meant.
def ncx(s):
    """A looser employer key, for lists that write an employer's name as one run-together word."""
    return re.sub(r"and|s$", "", re.sub(r"[^a-z0-9]", "", s.lower()))


index, loose = collections.defaultdict(list), collections.defaultdict(list)
for g in groups:
    index[(nc(g["company"]), g["type"])].append(g)
    loose[(ncx(g["company"])[:8], g["type"])].append(g)


def pool_for(j):
    """Employer postings that could be the same role as list entry j: the same employer name, or one name starting with the other."""
    exact = index.get((nc(j["company"]), j["type"]), [])
    if exact:
        return exact
    me = ncx(j["company"])
    if len(me) < 10:
        return []
    return [g for g in loose.get((me[:8], j["type"]), []) if ncx(g["company"]).startswith(me) or me.startswith(ncx(g["company"]))]


def match(j, pool):
    scored = []
    ta, exact = _toks(j["title"]), nt(j["title"])
    for g in pool:
        if g is j:
            continue
        s = 1.0 if nt(g["title"]) == exact else (len(ta & _toks(g["title"])) / max(1, len(ta | _toks(g["title"]))) if ta else 0)
        if s < 0.85 or not overlap(g["countries"], j["countries"]):
            continue
        scored.append((len(j["cities"] & g["cities"]), s, g))
    if not scored:
        return None
    sure = [x for x in scored if set(x[2]["countries"]) & set(j["countries"])]
    scored = sure or scored  # a posting known to be in the same country, before one whose country is unknown
    most = max(x[0] for x in scored)
    if most:
        return sorted([x for x in scored if x[0] == most], key=lambda x: -x[1])[0][2]
    if j["cities"]:  # it names a town that none of the candidates names: treat as a different vacancy
        blank = [x[2] for x in scored if not x[2]["cities"]]
        return blank[0] if len(blank) == 1 else None
    return scored[0][2] if len(scored) == 1 else None


folded = 0
lists = collections.defaultdict(list)
# Listings that name a town go first, so a group is keyed by its town whenever any of its listings gives one.
for j in sorted(later, key=lambda r: (not r["cities"], sorted(r["cities"]))):
    g = match(j, pool_for(j))
    if g is not None:
        absorb(g, j, False)
        folded += 1
        continue
    # Known only through lists: one vacancy per employer, title, type and town.
    base = "list:" + "|".join([nc(j["company"]), nt(j["title"]), j["type"]])
    same = [x for x in lists[base] if overlap(x["countries"], j["countries"]) and (not j["cities"] or x["cities"] & j["cities"])]
    twin = same[0] if same and (j["cities"] or len(same) == 1) else None  # a listing with no town joins a group only when there is one
    if twin is not None:
        absorb(twin, j, True)
        also(twin, j["url"])
    else:
        key = base + "|" + ",".join(sorted(j["cities"])[:3])
        while key in by_key:  # same employer, title and town, but countries that cannot be the same job
            key += "+"
        lists[base].append(start(j, key))

# 4. A posting reached by a plain web link and the same posting on an employer board: fold the first into the
#    second when exactly one board posting matches, and keep the web link so no application link is lost.
strong = collections.defaultdict(list)
for g in groups:
    if not g["key"].startswith(("url:", "list:")):
        strong[(nc(g["company"]), g["type"])].append(g)
gone = set()
for g in groups:
    if g["key"].startswith("url:"):
        cands = [x for x in strong.get((nc(g["company"]), g["type"]), ()) if nt(x["title"]) == nt(g["title"])
                 and (x["cities"] & g["cities"] or (not x["cities"] and not g["cities"])) and overlap(x["countries"], g["countries"])]
        if len(cands) == 1:
            absorb(cands[0], g, False)
            for s_ in g["srcs"]:
                if s_ not in cands[0]["srcs"]:
                    cands[0]["srcs"].append(s_)
            also(cands[0], g["url"])
            for u in g["alts"]:
                also(cands[0], u)
            gone.add(id(g))
groups = [g for g in groups if id(g) not in gone]
print("list-only roles matched to an employer posting:", folded, "| web-link duplicates folded:", len(gone))
merged = {g["key"]: g for g in groups}

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
    if j["salary"] and j["salary"].get("cur", "USD") == "USD":
        pool[(nc(j["company"]), j["type"])].append(j["salary"])
BAR = {"US": ("USD", BAR_US), "UK": ("GBP", 60000), "CA": ("CAD", 100000)}
SEEN_PATH = os.path.join(DATA, "first_seen.json")
first_seen = stored("first_seen.json", None)
seeding = first_seen is None  # first run with this store: use the posting date so that not everything looks new
first_seen = first_seen or {"ids": {}, "roles": {}}
ELIG_OUT, URL_INDEX = {}, {}
DAY = datetime.timedelta(days=1)
out = []
for j in merged.values():
    s, est = j["salary"], 0
    if not s and "US" in j["countries"]:
        ps = pool.get((nc(j["company"]), j["type"]))
        if ps:
            a = round(statistics.median(p["annual"] for p in ps))
            hourly = all(p["hourly"] for p in ps)
            s = {"text": f"${round(a/2080)}/hr" if hourly else f"${round(a/1000)}k/yr", "annual": a, "cur": "USD"}
            est = len(ps)
    cur = s.get("cur", "USD") if s else ""
    above = bool(s) and any(BAR[c][0] == cur and s["annual"] > MEDIAN[c] for c in j["countries"] if c in BAR)
    # Pay bar (graduate starting pay of about £60k or its equivalent), per country:
    #   3 = this posting states pay at or above it, in that country's currency
    #   2 = the employer's graduate pay is documented at or above it (a statement about the firm, not this role)
    #   1 = likely from the kind of firm (an estimate)      0 = no evidence
    cn, vs = nc(j["company"]), []
    for c in j["countries"]:
        bar_cur, bar = BAR.get(c, ("", 0))
        if s and not est and cur == bar_cur and s["annual"] >= bar:
            v = 3
        elif c == "US":
            v = 1 if (est and s["annual"] >= BAR_US) or (not s and (QUANT.search(cn) or TECH.search(cn))) else 0
        elif c == "UK":
            v = 2 if UK_CITED.search(cn) else 1 if (QUANT.search(cn) or TECH.search(cn)) else 0
        elif c == "CA":
            v = 2 if CA_CITED.search(cn) else 1 if (QUANT.search(cn) or TECH.search(cn) or CA_LIKELY.search(cn)) else 0
        else:
            v = 1 if (QUANT.search(cn) or TECH.search(cn)) else 0
        vs.append(v)
    # Evidence in one country does not prove another: the weakest country decides.
    hp = min(vs) if vs and min(vs) >= 2 else 1 if vs and max(vs) >= 1 else 0
    jid = ID.job_id(j["key"])
    posted = j["posted"] or ""
    # When this role was first seen here. Remembered by role as well as by id, so that a role whose link changes
    # (a list link later traced to the employer's posting) does not look new again.
    role = hashlib.sha1("|".join([cn, nt(j["title"]), j["type"], ",".join(sorted(j["cities"])[:3])]).encode()).hexdigest()[:12]
    since = first_seen["ids"].get(jid) or first_seen["roles"].get(role)
    if not since:
        since = (posted if posted and posted <= TODAY.isoformat() else (TODAY - DAY).isoformat()) if seeding else TODAY.isoformat()
    first_seen["ids"][jid] = since
    first_seen["roles"][role] = min(since, first_seen["roles"].get(role, since))
    j["role"] = role
    ev = j.get("ev")
    out.append([j["company"], j["title"], j["locs"], j["countries"], j["type"], j["cat"], j["url"], posted,
                s["text"] if s else "", round(s["annual"] * FX.get(cur, 1)) if s else 0, j["tier"], j["sponsor"], j["srcs"],
                1 if above else 0, est, hp, j["deg"], j["terms"][:4], jid,
                since, j.get("deadline") or (ev or {}).get("deadline") or "", ID.req_label(j["url"]), j["alts"], cur,
                j["scope"] if j["type"] == "Internship" and set(j["countries"]) & {"UK", "CA", "??"} else []])
    if ev is not None:
        ELIG_OUT[jid] = ev
    for u in [j["url"]] + j["alts"]:
        URL_INDEX[ID.nurl(u)] = jid
out.sort(key=lambda r: r[7] or r[19], reverse=True)
json.dump(out, open(OUT, "w"), ensure_ascii=False, separators=(",", ":"))
_dir = os.path.dirname(OUT) or "."
json.dump({"checked": TODAY.isoformat(), "total": len(ELIG_OUT), "read": ELIG_OUT}, open(os.path.join(_dir, "elig_crawl.json"), "w"), ensure_ascii=False)
json.dump(URL_INDEX, open(os.path.join(_dir, "url_index.json"), "w"))
current, roles, keep_from = {r[18] for r in out}, {j["role"] for j in merged.values()}, (TODAY - 120 * DAY).isoformat()
first_seen = {"ids": {k: v for k, v in first_seen["ids"].items() if k in current or v >= keep_from},
              "roles": {k: v for k, v in first_seen["roles"].items() if k in roles or v >= keep_from}}
os.makedirs(DATA, exist_ok=True)
json.dump(first_seen, open(SEEN_PATH, "w"), separators=(",", ":"), sort_keys=True)

# ---- health: what was read, and what looks wrong ----
usual = stored("sources.json", {})
health = {"date": TODAY.isoformat(), "sources": {}, "files": {}, "crawl": {}, "reed": {}}
for src in sorted(set(PARSED) | set(usual)):
    n, was = PARSED.get(src, 0), (usual.get(src) or {}).get("rows", 0)
    state = "ok" if n and n >= 0.4 * was else "low" if n else "none"
    health["sources"][src] = {"rows": n, "usual": was, "state": state, "last_ok": TODAY.isoformat() if state == "ok" else (usual.get(src) or {}).get("date", "")}
    if state == "ok":
        usual[src] = {"rows": n, "date": TODAY.isoformat()}
json.dump(usual, open(os.path.join(DATA, "sources.json"), "w"), indent=0, sort_keys=True)
if os.path.exists(f"{RAW}/fetch_status.tsv"):
    for line in open(f"{RAW}/fetch_status.tsv"):
        f, _, st = line.strip().partition("\t")
        if f and st and st != "ok":
            health["files"][f] = st
for name, fn in (("crawl", "ats_jobs.json"), ("reed", "reed_jobs.json")):
    if os.path.exists(f"{RAW}/{fn}"):
        d = json.load(open(f"{RAW}/{fn}"))
        health[name] = {"date": (d.get("fetched_at") or "")[:10], "boards": d.get("boards", 0), "failed": len(d.get("errors") or {}),
                        "carried": d.get("stale_rows", 0), "rows": len(d.get("jobs") or []), "version": d.get("version", 1)}
json.dump(health, open(os.path.join(_dir, "health.json"), "w"), indent=0)

C = collections.Counter
print("raw rows", len(jobs), "| outside US/CA/UK dropped", dropped, "| unique jobs", len(out))
print("country", C(c for r in out for c in r[3]))
print("type", C(r[4] for r in out))
print("cat", C(r[5] for r in out))
print("stated pay", sum(1 for r in out if r[9] and not r[14]), "by currency", C(r[23] for r in out if r[23]), "estimated", sum(1 for r in out if r[14]))
print("pay bar", {c: C(r[15] for r in out if c in r[3]) for c in ("US","UK","CA")})
print("sources", C(s for r in out for s in r[12]))
print("multi-source", sum(1 for r in out if len(r[12]) > 1))
print("deg", C(r[16] for r in out)); print("terms", C(t for r in out for t in r[17]).most_common(12)); print("sponsor", C(r[11] for r in out)); print("unique ids", len(set(r[18] for r in out)))
print("no date", sum(1 for r in out if not r[7]))
