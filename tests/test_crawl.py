import datetime
import json
import os
import tempfile
import crawl

keep = ["Software Engineer Intern - 4 months", "Product Manager Intern", "IT Support Intern", "QA Intern", "UX Design Intern",
        "Data Science Summer Student", "Stagiaire en développement logiciel", "2027 Summer Analyst Programme - Technology",
        "Software Engineering Industrial Placement", "Graduate Software Engineer 2027", "Junior Data Analyst", "Associate Product Manager",
        "Quantitative Researcher - Off-Cycle Internship", "Student Researcher, Machine Learning"]
drop = ["Senior Software Engineer", "Software Engineer II", "Engineering Manager", "Staff Data Scientist", "Internal Tools Engineer",
        "Student Success Manager, Data", "Marketing Intern", "Software Engineer", "Graduate Recruiter"]
for t in keep:
    check(crawl.wanted(t), "crawl: keeps " + t)
for t in drop:
    check(not crawl.wanted(t), "crawl: drops " + t)
check(bool(crawl.INTERN.search("Product Manager Intern")) and not crawl.INTERN.search("Graduate Software Engineer"), "crawl: intern vs graduate type")

DESC = "<p>About us.</p><ul><li>Open to penultimate and final-year students</li><li>12 weeks from June 2027</li></ul><p>Applications close 30 November 2026.</p>" + "<p>filler text for length.</p>" * 30


def fake_board(seed):
    a = crawl.job(seed, "Software Engineer Intern", ["3 Locations"], "https://x.wd1.myworkdayjobs.com/S/job/a_R1")
    a["_detail"] = ("workday", "detail-a")
    b = crawl.job(seed, "Data Analyst Intern", ["Austin, TX"], "https://x.wd1.myworkdayjobs.com/S/job/b_R2")
    b["_detail"] = ("workday", "detail-b")
    c = crawl.job(seed, "Platform Engineer Intern", ["Singapore"], "https://x.wd1.myworkdayjobs.com/S/job/c_R3")
    d = crawl.job(seed, "Cloud Engineer Intern", ["Remote"], "https://x.wd1.myworkdayjobs.com/S/job/d_R4")
    e = crawl.job(seed, "Senior Engineer", ["London, UK"], "https://x.wd1.myworkdayjobs.com/S/job/e_R5")
    return [a, b, c, d, e]


calls = []


def fake_get(url, body=None, tries=3):
    calls.append(url)
    return {"jobPostingInfo": {"location": "London", "additionalLocations": ["Manchester"], "country": {"descriptor": "United Kingdom"}, "jobDescription": DESC, "startDate": "2026-11-01"}}


real_fetch, real_get, real_pause = dict(crawl.FETCH), crawl.get, crawl.PAUSE
crawl.FETCH["workday"], crawl.get, crawl.PAUSE = fake_board, fake_get, 0
seed, rows, err = crawl.run({"ats": "workday", "board": "x.wd1/S", "company": "X Corp"})
by = {r["title"]: r for r in rows}
check(err == "" and set(by) == {"Software Engineer Intern", "Data Analyst Intern", "Cloud Engineer Intern"}, "crawl: keeps right rows", str(list(by)))
a = by.get("Software Engineer Intern", {})
check(a.get("countries") == ["UK"] and a.get("locations") == ["London", "Manchester"], "crawl: '3 Locations' resolved from the posting", str(a.get("countries")))
check(a.get("quality") == "full" and any("final-year" in s for s in a.get("req", [])) and a.get("deadline") == "2026-11-30", "crawl: requirement sentences and deadline stored", str(a.get("req")))
check(calls == ["detail-a"], "crawl: US-only role not fetched again", str(calls))
check(by.get("Cloud Engineer Intern", {}).get("countries") == ["??"], "crawl: bare Remote kept as unknown, not US")
check(by.get("Data Analyst Intern", {}).get("req") == [] and "_desc" not in a, "crawl: no requirement text stored for US-only rows")

prev = {"fetched_at": "2026-11-10T00:00:00Z", "jobs": [{"ats": "lever", "board": "down", "title": "T", "url": "u1", "pay": None, "countries": ["UK"], "seen": "2026-11-10"},
                                                      {"ats": "lever", "board": "old", "title": "T", "url": "u2", "pay": None, "countries": ["UK"], "seen": "2026-10-01", "stale": "2026-10-20"}]}
cf = crawl.carry_forward(prev, {"lever:down": "HTTP 503", "lever:old": "HTTP 503"}, "2026-11-14")
check([r["url"] for r in cf] == ["u1"] and cf[0]["stale"] == "2026-11-10", "crawl: failed board keeps recent rows, drops long-stale ones", str(cf))
crawl.FETCH.update(real_fetch)
crawl.get, crawl.PAUSE = real_get, real_pause
