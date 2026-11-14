import datetime
import eligibility as E

HTML = """<div><h2>About the role</h2><p>Join our platform team in London. You will build services used by millions.</p>
<ul><li>Currently pursuing a B.Sc. or M.Sc. in Computer Science</li><li>Open to penultimate and final-year students</li>
<li>Available for 12 weeks from June 2027</li><li>Experience with Python, e.g. Django or Flask</li></ul>
<p>Applications close on 30 November 2026. We review applications on a rolling basis and may close early.</p>
<script>var x = "must be enrolled in a co-op program";</script></div>"""
req, info = E.requirements(HTML)
check(any("penultimate and final-year" in s for s in req), "text: bullet kept as its own sentence", str(req))
check(any(s.startswith("Currently pursuing a B.Sc. or M.Sc.") for s in req), "text: abbreviations do not split a sentence", str(req))
check(not any("co-op" in s for s in req), "text: script contents ignored")
check(not any("Django" in s for s in req), "text: unrelated bullet left out")
check(info["len"] > 200 and len(info["hash"]) == 12 and info["lang"] == "", "text: info fields")
d, rolling = E.find_deadline(req, datetime.date(2026, 11, 14))
check(d == "2026-11-30" and rolling, "text: deadline and rolling flag", f"{d} {rolling}")
r = E.evaluate("Software Engineer Intern", [], req, E.DEFAULT_PROFILE, "full")
check(r["state"] == "M" and "final-year" in r["evidence"], "text: end to end match", str(r))
check(E.find_deadline(["Apply by January 5."], datetime.date(2026, 11, 14))[0] == "2027-01-05", "text: deadline year rolls forward")
check(E.find_deadline(["The deadline for applications is March 3rd, 2027."], datetime.date(2026, 11, 14))[0] == "2027-03-03", "text: month-first date")
fr = "<p>" + " ".join(["Nous recherchons un stagiaire pour notre équipe de développement. Vous êtes aux études et vous avez de l'expérience avec les outils du poste."] * 6) + "</p>"
check(E.requirements(fr)[1]["lang"] == "fr", "text: French posting detected")
check(E.grad_window("Graduate Programme 2027: Applied AI Engineer") is None, "text: programme name is not a graduation window")
w = E.grad_window("Students graduating in 2028 who are available from June 2027 to August 2027")
check(w and w[0] == 2028 * 12 and w[1] == 2028 * 12 + 11, "text: graduation window stops before availability dates", str(w))
