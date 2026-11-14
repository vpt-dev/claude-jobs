"""Derive the employer seed list (ATS + board id) from job URLs. Usage: seeds.py jobs.json seeds.json"""
import json, re, sys, collections
d = json.load(open(sys.argv[1]))
PAT = [
 ("greenhouse", r"(?:job-boards|boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_app\?for=)?([A-Za-z0-9_-]+)"),
 ("lever", r"jobs(?:\.eu)?\.lever\.co/([A-Za-z0-9_.-]+)"),
 ("ashby", r"jobs\.ashbyhq\.com/([A-Za-z0-9_.%-]+)"),
 ("smartrecruiters", r"jobs\.smartrecruiters\.com/([A-Za-z0-9_-]+)"),
 ("workable", r"apply\.workable\.com/([A-Za-z0-9_-]+)"),
 ("workday", r"https?://([a-z0-9_-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([A-Za-z0-9_-]+)"),
]
seeds, hosts = {}, collections.Counter()
for r in d:
    u = r[6]
    hit = False
    for ats, p in PAT:
        m = re.search(p, u)
        if not m: continue
        if ats == "workday":
            key = (ats, f"{m.group(1)}.{m.group(2)}/{m.group(3)}")
        else:
            slug = m.group(1)
            if slug.lower() in ("embed", "jobs", "j") or re.fullmatch(r"[0-9a-f-]{36}", slug): break
            key = (ats, slug if ats != "greenhouse" else slug.lower())
        s = seeds.setdefault(key, {"ats": key[0], "board": key[1], "company": r[0], "roles_seen": 0, "countries": set()})
        s["roles_seen"] += 1; s["countries"].update(r[3]); hit = True
        break
    if not hit:
        hosts[re.sub(r"^https?://([^/]+).*", r"\1", u)] += 1
out = sorted(seeds.values(), key=lambda s: (-s["roles_seen"], s["company"]))
for s in out: s["countries"] = sorted(s["countries"])
json.dump(out, open(sys.argv[2], "w"), indent=1)
print("seed boards", len(out), collections.Counter(s["ats"] for s in out))
print("roles covered by seeds", sum(s["roles_seen"] for s in out), "of", len(d))
print("UK/CA boards", sum(1 for s in out if set(s["countries"]) & {"UK","CA"}))
print("top unmatched hosts", hosts.most_common(25))
