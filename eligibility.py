"""Read what a posting says about who can apply, and compare it with one candidate's facts.

Two steps, kept apart on purpose:

  requirements(description)   picks out the whole sentences that state a requirement
  evaluate(title, ...)        compares those sentences with profile.json

The result is one of four states, with the sentence it rests on:

  M  match        the posting supports this candidate's route and nothing in it conflicts
  C  conditional  it depends on something not settled (a master's place, dates, an unclear rule)
  U  unknown      nothing relevant was found, or the posting has not been read
  X  mismatch     a stated requirement conflicts with a fact in the profile

Unknown stays unknown: a posting is never excluded on a guess, and a positive sentence never
cancels a different mandatory requirement.
"""
import datetime
import hashlib
import html
import json
import os
import re

EXTRACT_VERSION = 2

DEFAULT_PROFILE = {
    "degree": {"level": "bachelor", "field": "computer science", "study_ends": "2027-06", "award": "2027-07"},
    "masters": {"status": "applied", "countries": ["US", "CA"], "starts": "2027-09", "ends_earliest": "2028-05", "ends_latest": "2029-06"},
    "coop_registered": False,
    "work_rights": ["UK", "CA"],
    "available": {"from": "2027-06", "to": "2027-09"},
    "languages": ["en"],
    "target": {"season": "summer", "year": 2027},
}


def load_profile(path=None):
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "profile.json")
    prof = json.loads(json.dumps(DEFAULT_PROFILE))
    if os.path.exists(path):
        for k, v in json.load(open(path)).items():
            if isinstance(v, dict) and isinstance(prof.get(k), dict):
                prof[k].update(v)
            else:
                prof[k] = v
    return prof


# ---------------------------------------------------------------- text

_ABBR = re.compile(r"\b(Ph\.D|B\.Sc|M\.Sc|B\.S|M\.S|B\.A|M\.A|B\.Eng|M\.Eng|U\.S|U\.K|e\.g|i\.e|etc|Inc|Ltd|Sr|Jr|No|approx|incl|vs)\.", re.I)


def blocks(desc):
    """Split a description (HTML or plain text) into sentences and bullet items."""
    s = desc or ""
    s = re.sub(r"(?is)<(script|style|noscript|template|svg)\b.*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</(p|div|li|ul|ol|h[1-6]|tr|td|th|section|article|blockquote|dd|dt)>|<li\b[^>]*>", "\n", s)
    s = html.unescape(html.unescape(re.sub(r"<[^>]+>", " ", s)))
    s = s.replace(" ", " ").replace("​", "").replace("’", "'").replace("‘", "'")
    out = []
    for line in re.split(r"[\r\n]+|\s[•·▪●■◦]\s", s):
        line = re.sub(r"\s+", " ", line).strip(" -–—*•·\t")
        if len(line) < 3:
            continue
        line = _ABBR.sub(lambda m: m.group(0).replace(".", "․"), line)
        for sent in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9“\"(])", line):
            sent = sent.replace("․", ".").strip()
            if len(sent) >= 3:
                out.append(sent)
    return out


_STRONG = re.compile(
    r"penultimate|final[- ]year|last year of|finalist|(first|second|third|fourth|1st|2nd|3rd|4th)[- ]year|sophomore|freshm[ae]n|rising (junior|senior)|"
    r"juniors? (and|or) seniors?|all years|any year|year groups?|graduating|graduation|will graduate|to graduate|graduate (in|by|between|before|after|no)|"
    r"graduated|class of 20\d\d|20\d\d (graduates?|grads?)\b|recent(ly)? graduat|conferral|enrol+ed|enrol+ment|registered (in|with|on|as)|"
    r"currently (pursuing|studying|completing|working toward|attending|undertaking|a )|pursuing (a|an|your)|must be (a )?(current )?(full[- ]time )?student|"
    r"return(ing)? (to|for)|remaining|co-?op|work term|placement year|industrial placement|year in industry|sandwich|"
    r"deadline|closing date|applications? (close|will close|are due|must be|accepted until)|apply by|rolling basis|close early", re.I)
_SOFT = re.compile(
    r"ph\.?d|doctora|master'?s|\bm\.?sc\b|\bmeng\b|postgraduate|undergraduate|bachelor|\b\d{1,2}[- ]?(weeks?|months?)\b|year[- ]long|"
    r"(start|begin|commenc)\w* (date|in|on|from)|available (to|from|for)|duration|french|fran[cç]ais|bilingu|right to work|work authori[sz]|"
    r"eligible to work|sponsorship", re.I)
_FRENCH = re.compile(r"\b(le|la|les|des|et|vous|nous|pour|avec|dans|une|est|votre|notre|sur|aux|du|qui|sont|être|poste)\b", re.I)


def requirements(desc, max_items=12, max_len=320):
    """Pick out the sentences of a posting that state who can apply, when, and for how long.

    Returns (sentences, info) where info has the text length, a hash for change detection and the language.
    """
    sents = blocks(desc)
    full = " ".join(sents)
    picked = []
    for i, s in enumerate(sents):
        strong = bool(_STRONG.search(s))
        if strong or _SOFT.search(s):
            if len(s) > max_len:
                m = _STRONG.search(s) or _SOFT.search(s)
                a = max(0, m.start() - max_len // 2)
                s = ("…" if a else "") + s[a:a + max_len].strip() + "…"
            picked.append((0 if strong else 1, i, s))
    picked = sorted(sorted(picked)[:max_items], key=lambda t: t[1])
    words = re.findall(r"[A-Za-zÀ-ÿ']+", full[:6000])
    french = len(words) > 80 and sum(1 for w in words if _FRENCH.fullmatch(w)) / len(words) > 0.12
    info = {"len": len(full), "hash": hashlib.sha1(re.sub(r"\W+", "", full.lower()).encode()).hexdigest()[:12], "lang": "fr" if french else ""}
    return [s for _, _, s in picked], info


# ---------------------------------------------------------------- dates

_MONTHS = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
_SEASON = {"spring": (4, 6), "summer": (6, 9), "fall": (9, 12), "autumn": (9, 12)}
_DATE = re.compile(r"(?:\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|"
                   r"nov(?:ember)?|dec(?:ember)?|spring|summer|fall|autumn|winter)\.?,?\s+(?:of\s+)?)?\b(20\d\d)\b", re.I)


def ym(s):
    y, m = s.split("-")
    return int(y) * 12 + int(m) - 1


def ym_text(n):
    return f"{'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split()[n % 12]} {n // 12}"


def _span(word, year):
    """(first month, last month) covered by a date word such as 'December 2027' or 'Summer 2028'."""
    w = (word or "").lower()
    if not w:
        return year * 12, year * 12 + 11
    if w == "winter":  # end of the autumn term, as in "graduating between Winter 2027 and Summer 2028"
        return year * 12 + 11, (year + 1) * 12 + 2
    if w in _SEASON:
        a, b = _SEASON[w]
        return year * 12 + a - 1, year * 12 + b - 1
    m = _MONTHS[w[:3]]
    return year * 12 + m - 1, year * 12 + m - 1


_GRAD = re.compile(r"graduating|graduation|will graduate|to graduate|graduates? (in|by|between|from|on|before|after|no|during|within|of 20)|"
                   r"graduated (in|by|between|before|after)|class of|conferral|complet\w+ (your|their|a|an) (degree|studies|bachelor\S*|master\S*|undergraduate)[^.;]{0,30}\b(in|by|between|before|after)\b|"
                   r"finish\w* (your|their) (degree|studies)[^.;]{0,20}\b(in|by|between)\b|\b20\d\d(\s?(/|or|and|-|–|to)\s?20\d\d)? (graduates?|grads?)\b", re.I)
_GRAD_STOP = re.compile(r"\b(available|availability|internship|placement|start(ing|s)?|begin\w*|join\w*|to work|who (are|can|have|will be able)|"
                        r"and (are|have|be|must|can|able)|with (a|an|strong|experience)|must (be|have)|experience|term|duration|commit\w*|ability|"
                        r"location|deadline|appl(y|ication)\w*|cv|resume)\b", re.I)
_JOIN = re.compile(r"^\W*((and|or|to|through|until|till|and/or)\W+)?(the\W+)?(end of\W+|early\W+|late\W+|mid\W+)?$", re.I)
_OPEN_END = re.compile(r"^\W{0,3}(or|and) (later|after|beyond|thereafter)|^\W{0,3}onwards?|^\W{0,3}at the earliest|^\W{0,2}\+", re.I)
_BACH = re.compile(r"bachelor|undergrad|post-?secondary|college diploma", re.I)
_BACH_CS = re.compile(r"\b(B\.?S\.?|BSc|B\.?A\.?|BEng|BASc)\b")
_MAST = re.compile(r"(?<!scrum )\bmaster(?:'s|’s|s)?\b(?!\s+(data|class|classes|branch|node|plan|schedule|file|list|record|key|copy|agreement|services?)\b)|"
                   r"postgrad|(?<![a-z])graduate (student|degree|school|studies|level|coursework)|"
                   r"(enrol+ed (in|on)|pursuing|attending|completing|accredited) (a |an |your |their )?(accredited |full[- ]time )?graduate program|\bmeng\b|\bmsc\b", re.I)
_MAST_CS = re.compile(r"\b(M\.S\.?|MSc|MEng|MASc|MBA)\b")
_MS = re.compile(r"\bMS\b")
_MS_SOFTWARE = re.compile(r"^\W*(office|excel|word|teams|access|project|sql|powerpoint|power\b|windows|dynamics|azure|365|outlook|visio|suite|tools|products|"
                          r"applications|apps|stack|copilot|fabric|\.net|visual|sharepoint|planner|forms|…|$)", re.I)
_SKILL_BEFORE = re.compile(r"(proficien\w+|skills?|knowledge|experience|familiar\w*|competen\w+|command|literate|literacy|user|use)\W+((in|with|of|using)\W+)?(the\W+)?$", re.I)


def _names_ms(s):
    """Whether "MS" in the text means a master's degree, not Microsoft software ("proficient in MS Excel")."""
    for m in _MS.finditer(s):
        if _MS_SOFTWARE.search(s[m.end():m.end() + 14]) or _SKILL_BEFORE.search(s[max(0, m.start() - 30):m.start()]):
            continue
        return True
    return False
_PHD = re.compile(r"ph\.?\s?d\b|doctora", re.I)


def _levels(s):
    out = set()
    if _BACH.search(s) or _BACH_CS.search(s):
        out.add("bachelor")
    if _MAST.search(s) or _MAST_CS.search(s) or _names_ms(s):
        out.add("master")
    if _PHD.search(s):
        out.add("phd")
    return out


def grad_window(sentence):
    """(first month, last month, degree levels named) of a stated graduation window, or None. None bounds are open."""
    m = _GRAD.search(sentence)
    if not m:
        return None
    lead = re.match(r"\b(20\d\d)(?:\s?(?:/|or|and|-|–|to)\s?(20\d\d))? (?:graduates?|grads?)\b", m.group(0), re.I)
    if lead:
        a, b = int(lead.group(1)), int(lead.group(2) or lead.group(1))
        return a * 12, b * 12 + 11, _levels(sentence)
    tail = sentence[m.start():m.start() + 170]
    stop = _GRAD_STOP.search(tail, len(m.group(0)))
    if stop:
        tail = tail[:stop.start()]
    dates = list(_DATE.finditer(tail))
    if not dates:
        return None
    # Dates joined by "and", "or", "to" or a dash belong to one window ("between December 2027 and July 2028").
    # A date after any other wording ("... Term: January 2027 to April 2027") is about something else.
    run = [dates[0]]
    for d in dates[1:]:
        if len(run) < 4 and _JOIN.match(tail[run[-1].end():d.start()]):
            run.append(d)
        else:
            break
    spans = [_span(d.group(1), int(d.group(2))) for d in run]
    lo, hi = min(x[0] for x in spans), max(x[1] for x in spans)
    low = tail.lower()
    before, after = low[:run[0].start()], low[run[-1].end():]
    if _OPEN_END.search(after) or (len(run) == 1 and re.search(r"no earlier than|not before|earliest|on or after|from\s*$", before)):
        hi = None
    elif len(run) == 1:
        if re.search(r"\bafter\s*$|\bafter (the )?(end of )?$", before):
            lo, hi = spans[0][1] + 1, None
        elif re.search(r"^\W{0,3}(or earlier|or before|or sooner|at the latest)", after) or re.search(r"\b(by|before|no later than|prior to|until)\s*(the )?(end of )?$", before):
            lo = None
    return lo, hi, _levels(sentence)


def _window_text(lo, hi):
    if lo is None:
        return f"by {ym_text(hi)}"
    if hi is None:
        return f"{ym_text(lo)} or later"
    return ym_text(lo) if lo == hi else f"{ym_text(lo)} to {ym_text(hi)}"


# ---------------------------------------------------------------- findings

def F(kind, verdict, why, text, sub=""):
    """One finding. `sub` tells date findings apart: "length" (how long it runs) or "when" (which season or month)."""
    return {"kind": kind, "verdict": verdict, "why": why, "text": text, "sub": sub, "src": "posting"}


_PEN = re.compile(r"penultimate|second[- ]to[- ]last year|next[- ]to[- ]last year", re.I)
_FIN = re.compile(r"final[- ]year (student|undergrad|bachelor|master|msc|ph\.?d|doctoral|university|degree|candidate|computer|engineering|stem|or|and)|"
                  r"\b(in|completing|are in|be in|currently in|within) (your|their|his|her) (final|last)[- ]year|"
                  r"(final|last)[- ]year(s)? of (your |their |a |an |the )?(study|studies|degree|undergraduate|bachelor\S*|master\S*|msc|ph\.?d|university|course|college|education)|(penultimate|final)[- ]?\s?(/|or|and|&|,)\s?(the |a |your |their )?(penultimate|final)|"
                  r"or final[- ]year|and final[- ]year|open to final|for final[- ]year|accept\w* final|final[- ]year[^.;]{0,25}(welcome|eligible|encouraged|may apply|can apply)|"
                  r"final[- ]year (internship|placement|programme|program|intern|scheme|opportunit)|\bfinalists?\b", re.I)
_NOT_FIN = re.compile(r"non[- ]?\s?final[- ]year|not (be )?in (your|their|the) (final|last)[- ]year|"
                      r"final[- ]year[^.;]{0,60}\b(not|cannot|can't|unable|ineligible|aren't|isn't)\b|"
                      r"\b(not|isn't|aren't) (open|available|suitable|intended) (to|for) final[- ]year|exclud\w+ final[- ]year|other than final[- ]year", re.I)
_NOT_PEN = re.compile(r"(do(es)? not|don't|need not|no need to|not required to|not necessary to|not have to)[^.;]{0,30}penultimate|"
                      r"not (only|limited to|restricted to|just)[^.;]{0,15}penultimate|penultimate[^.;]{0,40}(isn't|is not|not) (required|necessary|essential)", re.I)
_ANY_YEAR = re.compile(r"all years|any year( of study| group)?\b|all year groups|regardless of (your |their )?year|any stage of (your |their )?(degree|studies)|students of all years|all levels of study", re.I)
_PG_SCOPE = re.compile(r"(final|last|penultimate)[- ]year (ph\.?d|doctoral|master'?s?|msc|meng|postgrad\w*)|"
                       r"(final|last|penultimate)( or (final|last|penultimate))?[- ]year of (a |an |your |their |the )?(ph\.?d|doctora\w+|master'?s?|msc|postgrad\w*)", re.I)
_PG_BEFORE = re.compile(r"(ph\.?d|doctoral|master'?s?|msc|postgrad\w*)s?\W{1,4}(students? )?\(?(in |who are in )?(their |the |your )?(penultimate|final|last)", re.I)
_ROUTE_OK = re.compile(r"(intend|plan|planning|going|continu\w+|progress\w+|proceed\w+|return\w*)[^.;]{0,70}(master|msc|postgraduate|further study)[^.;]{0,70}(eligible|welcome|can apply|may apply|consider|accept)|"
                       r"(eligible|welcome|open|consider\w*|accept\w*)[^.;]{0,60}(continu\w+|going on|progress\w+|intend\w*|plan\w*|proceed\w+)[^.;]{0,40}(master|msc|postgraduate)", re.I)
_MASTERS_NEXT = re.compile(r"(plan|planning|intend|intending|going|continu\w+|progress\w+|proceed\w+|go on|moving)[^.;]{0,45}(master|postgraduate|further study|msc|graduate school)", re.I)
_PEN_LEVELS = re.compile(r"penultimate[- ]year\s*\((can be|whether|either|including|undergraduate|bachelor|master|ph)|"
                         r"penultimate[- ]year of (an? |your |their |the )?(undergraduate|bachelor\S*|master\S*|ph\.?d|degree)[^.;]{0,30}(\bor\b|,|/)\s*(a |an )?(master|ph\.?d|undergrad|bachelor)", re.I)
_REQ_CUE = re.compile(r"\b(must|should|need|require|currently|you are|you're|be in|open to|eligible|aimed at|designed for|for students|applicants|candidates|"
                      r"looking for|we welcome|to apply|studying|in (your|their)|students?|undergraduates?|eligibility)\b", re.I)
_ALT_MASTERS = re.compile(r"\b(or|and|/)\s+(a\s+|an\s+|current\s+|first[- ]year\s+|1st[- ]year\s+)?(master|msc|meng|postgrad|ph\.?d|graduate student)", re.I)
_EARLY_YEARS = re.compile(r"\b(first|1st|second|2nd)[- ]year\b|sophomore|freshm[ae]n", re.I)
_STUDENT_CUE = re.compile(r"student|undergraduate|degree|university|stud(y|ies)\b", re.I)
_RISING = re.compile(r"rising (junior|senior)s?", re.I)
# "Will be entering their final year", "returning for your final year after the summer": the final year comes after the internship.
_ENTER_FIN = re.compile(r"(entering|enter|going into|go into|returning (to|for)|return (to|for)|about to (start|begin|enter)|starting|commencing|progressing (in)?to|"
                        r"moving into|heading into|due to (start|begin|enter)|approaching|into) (the |your |their |his |her |a |an )?(final|last|senior)[- ]year", re.I)
_PREFER = re.compile(r"(prefer\w*|ideal\w*|depend\w+ (up)?on|based on|according to|varies (by|with)|typically|usually|generally|normally|most suited|best suited|well suited|suited to|aimed primarily|primarily)\W+(\w+\W+){0,4}$", re.I)
_PREFER_AFTER = re.compile(r"^[^.;]{0,30}\b(preferred|ideal|is a plus|desirable|but not (essential|required)|though|although)\b", re.I)


def _soft(s, m):
    """Whether the wording around a match makes it a preference rather than a rule ("preferably a rising senior")."""
    return bool(_PREFER.search(s[max(0, m.start() - 45):m.start()]) or _PREFER_AFTER.search(s[m.end():m.end() + 45]))
_CLASS_YEARS = re.compile(r"juniors? (and|or) seniors?|junior or senior|(current )?(juniors?|seniors?) (standing|status|year|level)", re.I)


def _year(s, final_started=None):
    pen, fin = _PEN.search(s), _FIN.search(s)
    final_started = final_started or datetime.date.today().year
    if _NOT_FIN.search(s):
        return [F("year", "fail", "says final-year students cannot apply, and you are in your final year", s)]
    if _ANY_YEAR.search(s) and _STUDENT_CUE.search(s):
        return [F("year", "ok", "open to students in any year", s)]
    if _ROUTE_OK.search(s):
        return [F("year", "route", "is open to students going on to a master's, which is your plan", s)]
    ent = _ENTER_FIN.search(s)
    if ent and not (pen and fin):
        when = re.search(r"\b(20\d\d)\b", s[ent.end():ent.end() + 60])
        if when and int(when.group(1)) <= final_started and not re.search(r"after|following", s[ent.start():ent.end() + 60], re.I):
            return [F("year", "ok", "names students who entered their final year this academic year", s)]
        if _soft(s, ent):
            return [F("year", "cond", "prefers students who still have their final year to come; yours ends before the internship", s)]
        if re.search(r"undergraduate|bachelor", s[ent.end():ent.end() + 50], re.I) or "master" not in _levels(s) and re.search(r"undergraduate|bachelor", s, re.I):
            return [F("year", "fail", "asks for students who start their final undergraduate year after the internship, and yours ends before it", s)]
        return [F("year", "cond", "asks for students who start the final year of a course after the internship; that fits only if your master's counts", s)]
    if fin:
        if (_PG_SCOPE.search(s) or _PG_BEFORE.search(s)) and "bachelor" not in _levels(s):
            return [F("degree", "fail", "asks for students near the end of a master's or PhD, and you are finishing a bachelor's", s)]
        if _MASTERS_NEXT.search(s):
            return [F("year", "ok", "names final-year students who are going on to a master's, which is your plan", s)]
        return [F("year", "ok", "names final-year students", s)]
    if pen:
        if _NOT_PEN.search(s):
            return [F("year", "note", "says penultimate-year status is not required", s)]
        if re.search(r"penultimate[- ]year[^.;:]{0,30}\bor\b[^.;:]{0,25}(recent(ly)? graduat|graduated?\b)", s, re.I):
            return []  # "penultimate-year or recently graduated": the graduate half is judged on its own
        if _soft(s, pen):
            return [F("year", "cond", "prefers penultimate-year students without ruling out others", s)]
        if _PG_SCOPE.search(s) and "bachelor" not in _levels(s):
            return [F("degree", "fail", "asks for students part-way through a master's or PhD, and you are finishing a bachelor's", s)]
        if _PEN_LEVELS.search(s):
            return [F("year", "fail", "asks for students in the penultimate year of their degree at any level, and you are in your final year", s)]
        if _ALT_MASTERS.search(s):
            return [F("year", "cond", "asks for penultimate-year students or master's students; you would be between the two", s)]
        if _REQ_CUE.search(s):
            return [F("year", "fail", "asks for penultimate-year students, and you are in your final year", s)]
        return [F("year", "cond", "mentions penultimate-year students without saying whether finalists can apply", s)]
    if _RISING.search(s):
        if re.search(r"\bor\b[^.;]{0,25}recent(ly)? graduat", s, re.I):
            return []  # "rising senior or recent graduate": the graduate half is judged on its own
        if re.search(r"\bor\b[^.;]{0,25}(graduate student|master)", s, re.I):
            return [F("year", "cond", "asks for students with a year still to come, or graduate students; you would be an incoming master's student", s)]
        if _soft(s, _RISING.search(s)):
            return [F("year", "cond", "prefers students with a year of their degree still to come, without ruling out others", s)]
        return [F("year", "fail", "asks for students with a year of their degree still to come, and your bachelor's ends before the internship", s)]
    if _CLASS_YEARS.search(s):
        return [F("year", "cond", "uses US class-year wording; seniors usually means students returning to finish", s)]
    if _EARLY_YEARS.search(s) and _STUDENT_CUE.search(s) and not (_MAST.search(s) or _PHD.search(s)) \
            and re.search(r"\b(must|open to|for|aimed at|designed for|eligible|currently in|be in|students in)\b", s, re.I):
        return [F("year", "fail", "is for first- or second-year students, and you are in your final year", s)]
    return []


def _grad(s, prof):
    w = grad_window(s)
    if not w:
        return []
    lo, hi, levels = w
    ends, award = ym(prof["degree"]["study_ends"]), ym(prof["degree"]["award"])
    text = _window_text(lo, hi)
    if (lo is None or lo <= award) and (hi is None or hi >= ends):
        return [F("grad", "ok", f"asks for graduation {text}, and your bachelor's finishes {ym_text(award)}", s)]
    if hi is not None and hi < ends:
        return [F("grad", "fail", f"asks for graduation {text}, and your bachelor's finishes {ym_text(award)}", s)]
    if levels and levels <= {"bachelor"}:
        if re.search(r"or (an? )?(equivalent|related|similar|higher|above|advanced)", s, re.I):
            return [F("grad", "cond", f"asks for graduation {text} with a bachelor's or equivalent: your bachelor's finishes {ym_text(award)}, so this fits only through your master's ({prof['masters']['status']}, not confirmed)", s)]
        return [F("grad", "fail", f"asks for bachelor's students graduating {text}, and your bachelor's finishes {ym_text(award)}", s)]
    if levels == {"phd"}:
        return [F("degree", "fail", f"asks for PhD students graduating {text}", s)]
    m_lo, m_hi = ym(prof["masters"]["ends_earliest"]), ym(prof["masters"]["ends_latest"])
    if (lo is None or lo <= m_hi) and (hi is None or hi >= m_lo):
        return [F("grad", "cond", f"asks for graduation {text}: your bachelor's finishes first, so this fits only through your master's ({prof['masters']['status']}, not confirmed)", s)]
    return [F("grad", "fail", f"asks for graduation {text}, which fits neither your bachelor's nor a master's ending {ym_text(m_lo)} to {ym_text(m_hi)}", s)]


_ENR = re.compile(r"(currently |presently |actively )?(enrol+ed|registered|matriculated) (in|on|at|with|as)\b|currently (pursuing|studying|completing|working towards?|attending|undertaking|reading for)|"
                  r"(must|should|need to) be (a |an )?(current |active )?(full[- ]time )?(university |college )?students?\b|current(ly)? (a |an )?(full[- ]time )?(university |college )?students?\b|"
                  r"active(ly)? (student|enrol+ment)|pursuing (a|an|your) [^.;]{0,40}(degree|bachelor|master|ph\.?d|diploma)|student status", re.I)
_DURING = re.compile(r"(during|throughout|for the duration of|at the time of|while (on|completing|undertaking)|at the start of|for the length of) (the |your |their )?(internship|placement|co-?op|work term|program\w*|term)", re.I)
_BEFORE_TERM = re.compile(r"(term|semester|quarter|academic (year|term))[^.;]{0,25}(immediately )?(before|prior to|preceding)[^.;]{0,25}(internship|placement|work term|co-?op)", re.I)
_RETURN = re.compile(r"return(ing)? to (school|university|college|campus|class(es)?|stud(y|ies)|education|(your|their|a|an|the) (studies|degree\S*|program\w*|course|university|school|academic\w*)|full[- ]time (study|studies|education|school))|"
                     r"must be returning|returning students?|return for (at least )?(one|1|a|an|another)|continu\w+ (your |their )?(studies|education|degree|enrol+ment) (after|following|upon)|"
                     r"(at least )?(one|1|two|2|a|an) (more |additional |full )?(semester|term|quarter|year)s? (of (school|study|studies|coursework|classes|university) )?(left|remaining)|"
                     r"(semester|term|quarter|year)s? (of [a-z ]{0,20})?remaining|(coursework|studies|classes) remaining|not (be )?graduating (before|until|prior)|graduat\w+ after the (internship|co-?op|placement|program\w*)", re.I)
_NO_RETURN = re.compile(r"(not|no) (need|required|necessary|have)[^.;]{0,25}return|need not return|without (needing|having) to return", re.I)
_SAME_DEGREE = re.compile(r"(current|same|undergraduate|bachelor'?s?) (degree|program\w*|course|studies)", re.I)
_RG_OK = re.compile(r"recent(ly)? graduat\w*[^.;]{0,70}(welcome|eligible|encouraged|may apply|can apply|considered|accepted|also|as well)|(open|available) to[^.;]{0,40}recent graduates|"
                    r"students (and|or) (recent )?graduates|graduates and students", re.I)
_RG_ALT = re.compile(r"\b(or|and) (a )?recent(ly)? graduat|\b(or|and) (have )?recently (graduated|completed|finished|obtained)", re.I)
_RG_CUE = re.compile(r"student|degree|pursuing|enrol|eligib|appl(y|icant)|candidate|open to|looking for|seeking|requirement|qualif|\bmust\b|\bshould\b", re.I)
_RG_NO = re.compile(r"recent(ly)? graduat\w*[^.;]{0,40}\b(not|ineligible|cannot|can't)\b|not (open|available) to[^.;]{0,20}graduates|graduates are not", re.I)


def _enrol(s, prof):
    out = []
    levels = _levels(s)
    if _RG_NO.search(s):
        out.append(F("enrol", "cond", "says graduates cannot apply, so you would need to count as a continuing student through your master's", s))
    elif (_RG_OK.search(s) or (_RG_ALT.search(s) and _RG_CUE.search(s))) and not (levels and "bachelor" not in levels and re.search(r"graduated from", s, re.I)):
        out.append(F("grad", "ok", "accepts recent graduates, which you will be", s))
    excluded = re.search(r"\b(not|in)eligible\b|\bnot (be )?eligible|cannot apply|can't apply|not (be )?considered|are excluded|will not be accepted", s, re.I)
    if _ENR.search(s) and excluded and levels and "bachelor" not in levels:
        # "Students enrolled in PhD, MBA or JD programs are not eligible": this shuts those students out, not you.
        out.append(F("enrol", "note", "rules out students on other degrees, not bachelor's students", s))
    elif _ENR.search(s) and not re.search(r"co-?op", s, re.I):
        if levels and "bachelor" not in levels and re.search(r"\bor\b[^.;]{0,20}recent(ly)? graduat\w*\b(?! from)", s, re.I):
            out.append(F("enrol", "cond", "asks for master's or PhD students or recent graduates; whether a new bachelor's graduate counts is not stated", s))
        elif levels == {"phd"}:
            out.append(F("degree", "fail", "asks for students currently on a PhD", s))
        elif levels and "bachelor" not in levels:
            out.append(F("enrol", "fail", "asks for students currently on a master's or PhD; yours would not have started", s))
        elif _DURING.search(s) and not _BEFORE_TERM.search(s):
            out.append(F("enrol", "cond", "asks you to be enrolled during the internship; you would be between your bachelor's and your master's", s))
        else:
            out.append(F("enrol", "weak", "asks for a current student, which you are when you apply", s))
    if _RETURN.search(s) and not _NO_RETURN.search(s):
        if _SAME_DEGREE.search(s) and "master" not in levels:
            out.append(F("return", "fail", "asks you to go back to your current degree afterwards, and your bachelor's ends before the internship", s))
        else:
            out.append(F("return", "cond", f"asks you to return to study afterwards; whether a new master's counts is the employer's call, and your place is {prof['masters']['status']}, not confirmed", s))
    return out


_COOP_NEG = re.compile(r"co-?op[^.;]{0,80}\b(not|isn't|aren't)\b[^.;]{0,15}(required|mandatory|necessary|needed|a requirement)|"
                       r"\b(not|no) (need|required|necessary)[^.;]{0,40}co-?op|do(es)? not (need|have) to be[^.;]{0,30}co-?op", re.I)
_COOP_MAND = re.compile(r"(must|need to|needs to|required to|have to|should|shall) be[^.;]{0,50}(enrol+ed|registered|participating)[^.;]{0,40}co-?op|"
                        r"(enrol+ed|registered|participating) in (a|an|the|your)[^.;]{0,50}co-?op\W*(program|programme|education|stream|option|placement)|"
                        r"co-?op (program|programme)? ?(enrol+ment|registration|eligibility|status)[^.;]{0,30}(is |are )?(required|mandatory|necessary)|"
                        r"must be (a |an )?(current |active )?co-?op student|"
                        r"eligible for (a |an )?(co-?op|work term)[^.;]{0,40}(through|via|by|with) (your|their) (school|university|institution|college)|"
                        r"approved by (your|their) (co-?op|school|university)[^.;]{0,30}(office|program|coordinator)", re.I)


_COOP_OTHER = re.compile(r"\bco-?ops? (are|is|roles?|positions?|terms?|placements?|opportunities|students?)[^.;]{0,25}(only|exclusively|solely)\b|"
                         r"(only|exclusively) (for|available to|open to)[^.;]{0,30}co-?op (students|program)", re.I)


def _coop(s, prof, coop_role=True):
    if not re.search(r"co-?op", s, re.I):
        return []
    if _COOP_NEG.search(s):
        return [F("coop", "note", "says co-op registration is not required", s)]
    if _COOP_MAND.search(s) and not prof.get("coop_registered"):
        if not coop_role and _COOP_OTHER.search(s):
            # "This is a 12-week internship. Co-ops are only available to students enrolled in a co-op program."
            return [F("coop", "note", "says its co-op roles need co-op registration; this role is not titled as a co-op", s)]
        return [F("coop", "fail", "requires registration in a university co-op programme, which you do not have", s)]
    return []


_PG_ONLY = re.compile(r"\b(must|should|need|require\w*|looking for|seeking|open to|for|are a|be a|as a|current)\b[^.;]{0,40}(ph\.?d|doctoral) (student|candidate|researcher)s?", re.I)


def _degree(s):
    levels = _levels(s)
    if _PG_ONLY.search(s) and "bachelor" not in levels and "master" not in levels and not _ENR.search(s):
        return [F("degree", "fail", "asks for PhD students", s)]
    return []


_DUR = re.compile(r"(\d{1,2})\s?(?:-|–|to|or|/)\s?(\d{1,2})[- ]?\s?(month|week)s?\b|(\d{1,2})[- ]?\s?(month|week)s?\b", re.I)
_DUR_CUE = re.compile(r"internship|placement|co-?op|work term|\bterm\b|contract|program(me)?|duration|assignment|position|role|opportunity|scheme|length|lasting|lasts|"
                      r"runs for|full[- ]time for|\bfor \d", re.I)
_DUR_NOT = re.compile(r"^\s?(of |'|’)?\s?(experience|notice|probation|of graduation|since graduat|old\b|prior|previous|or more of)|^[^.;]{0,12}\bexperience\b|"
                      r"^\s?of (\w+ ){0,3}(support|mentor\w*|training|coaching|access|membership|subscription|onboarding|development|benefits?|cover|leave)\b", re.I)
_YEAR_LONG = re.compile(r"year[- ]long|one[- ]year (placement|internship|contract|program)|placement year|year in industry|industrial placement|sandwich (year|placement|course)|year[- ]out", re.I)
_YEAR_LONG_HERE = re.compile(r"\b(this|our|the) (\w+ ){0,3}(placement year|year in industry|industrial placement|sandwich placement|year[- ]long|one[- ]year)|"
                             r"(placement year|year in industry|industrial placement|year[- ]long (internship|placement))[^.;]{0,40}(start|begin|commenc|from|run|last|opportunit|programme|program|scheme|role)", re.I)
_EXPERIENCE_TALK = re.compile(r"experience[^.;]{0,40}(for example|such as|e\.g|through|via|gained|from)|previous|prior", re.I)
_START = re.compile(r"(start\w*|begin\w*|commenc\w+)[^.;]{0,30}?\b(january|february|march|april|may|june|july|august|september|october|november|december)\b,?\s?(20\d\d)", re.I)


def _months_available(prof):
    return ym(prof["available"]["to"]) - ym(prof["available"]["from"]) + 1


def _durations(s):
    out = []
    for m in _DUR.finditer(s):
        if _DUR_NOT.search(s[m.end():m.end() + 30]):
            continue
        if re.search(r"(last|past|within|minimum of|at least)\s*$", s[:m.start()], re.I) and re.search(r"experience|graduat", s[m.end():m.end() + 40], re.I):
            continue
        unit = (m.group(3) or m.group(5)).lower()
        nums = [int(x) for x in (m.group(1), m.group(2), m.group(4)) if x]
        out += [n if unit == "month" else n / 4.345 for n in nums]
    return [d for d in out if 0.5 <= d <= 24]


_SEASON_NAME = r"(summer|fall|autumn|winter|spring)"
_TERM_WORD = r"(?:co-?op|intern(?:ship)?s?|work[- ]term|term|session|semester|placement|analyst|associate|student|programme|program|cohort|class)"
_SEASONS = [
    re.compile(_SEASON_NAME + r"\s*(?:/|,|or|and|&|-|–)\s*" + _SEASON_NAME + r"\s*'?(20\d\d)\b", re.I),          # Summer/Fall 2027
    re.compile(_SEASON_NAME + r"\s*'?(20\d\d)\b", re.I),                                                       # Summer 2027
    re.compile(_SEASON_NAME + r"\s+(?:" + _TERM_WORD + r"\s+){1,2}'?(20\d\d)\b", re.I),                          # Winter Co-op 2027
    re.compile(_SEASON_NAME + r"\s*'(\d\d)\b", re.I),                                                           # Summer '27
    re.compile(r"\b(20\d\d)\s+" + _SEASON_NAME + r"\b", re.I),                                                  # 2027 Summer
]


def seasons_in(text):
    """Every season and year named in a piece of text, as ("summer", 2027) pairs."""
    out = []

    def note(season, year):
        year = int(year)
        pair = (season.lower().replace("autumn", "fall"), year + 2000 if year < 100 else year)
        if pair not in out:
            out.append(pair)

    t = text or ""
    for m in _SEASONS[0].finditer(t):
        note(m.group(1), m.group(3))
        note(m.group(2), m.group(3))
    for rx in _SEASONS[1:4]:
        for m in rx.finditer(t):
            note(m.group(1), m.group(2))
    for m in _SEASONS[4].finditer(t):
        if not re.match(r"\s*'?\s*20\d\d", t[m.end():]):  # "2026 Summer 2027" is not "Summer 2026"
            note(m.group(2), m.group(1))
    return out


_MON = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_MON_ALT = r"(?:\s*(?:/|or)\s*" + _MON + r")?"
# "January - April 2027", "May/June 2027 - August/September 2028", "December 2026 to April 2027"
_RANGE = re.compile(r"\b" + _MON + r"\.?" + _MON_ALT + r"\.?,?\s*(20\d\d)?\s*(?:-|–|—|to|through|until|till)\s*" + _MON + r"\.?" + _MON_ALT + r"\.?,?\s*(20\d\d)", re.I)
_RANGE_CUE = re.compile(r"available|availability|term|internship|co-?op|placement|program|duration|dates?|runs?|commit|work|from|start|\(", re.I)
_BACK_BY = re.compile(r"return(?:ing)? to (?:full[- ]time )?(?:education|university|stud(?:y|ies)|school|college|your (?:degree|studies|course))[^.;]{0,25}\b(?:in|by|for)\s+(?:the\s+)?"
                      r"(?P<when>autumn|fall|september|october|january|spring|summer|winter)?\s*(?P<year>20\d\d)", re.I)
_SEASON_ROLE = re.compile(r"(internship|intern|co-?op|work[- ]term|placement|cohort|position|role|program(?:me)?|opportunit\w+|term)", re.I)


def _ranges(s):
    """(first month, last month) of each month range in the text, as month counts."""
    out = []
    for m in _RANGE.finditer(s):
        y2 = int(m.group(6))
        y1 = int(m.group(3) or y2)
        a = y1 * 12 + _MONTHS[m.group(1)[:3].lower()] - 1
        b = y2 * 12 + _MONTHS[(m.group(5) or m.group(4))[:3].lower()] - 1
        if not m.group(3) and a > b:
            a -= 12  # "November - February 2027" starts the year before
        if 0 <= b - a <= 30:
            out.append((a, b, m))
    return out


def _dates(s, prof, is_title=False):
    out = []
    free = _months_available(prof)
    lo, hi = ym(prof["available"]["from"]), ym(prof["available"]["to"])
    year = prof["target"]["year"]
    if is_title or _DUR_CUE.search(s):
        ds = _durations(s)
        if _YEAR_LONG.search(s) and (is_title or (_YEAR_LONG_HERE.search(s) and not _EXPERIENCE_TALK.search(s))):
            ds.append(12)
        if ds:
            shortest = min(ds)
            if shortest <= free - 0.4:
                out.append(F("dates", "weak", f"runs about {round(shortest * 4.345) if shortest < 3.9 else round(shortest)} {'weeks' if shortest < 3.9 else 'months'}, which fits a summer", s, "length"))
            elif shortest <= free + 0.6:
                out.append(F("dates", "cond", f"runs about {round(shortest)} months; check its start and end dates against the start of your master's", s, "length"))
            else:
                out.append(F("dates", "fail", f"runs {round(shortest)} months, and you are free for about {free} months in summer {year}", s, "length"))
    # Stated working dates: "must be available May 2027 - August 2028", "(January - April 2027)".
    for a, b, m in _ranges(s):
        if not (is_title or _RANGE_CUE.search(s[max(0, m.start() - 60):m.start()])) or re.search(r"graduat|appl(y|ication)|deadline", s[max(0, m.start() - 40):m.start()], re.I):
            continue
        span = f"{ym_text(a)} to {ym_text(b)}"
        if a >= lo - 1 and b <= hi:
            out.append(F("dates", "weak", f"runs {span}, which fits your summer", s, "length"))
        elif a >= lo - 1 and b <= hi + 1:
            out.append(F("dates", "cond", f"runs {span}; check the end date against the start of your master's", s, "length"))
        else:
            out.append(F("dates", "fail", f"runs {span}, and you are free {ym_text(lo)} to {ym_text(hi)}", s, "length"))
    m = _START.search(s)
    if m and not _ranges(s) and not re.search(r"application|applications|recruit|hiring|interview", s[:m.start()], re.I):
        when = int(m.group(3)) * 12 + _MONTHS[m.group(2)[:3].lower()] - 1
        if not (lo - 1 <= when <= lo + 1):
            out.append(F("dates", "fail", f"starts in {m.group(2).title()} {m.group(3)}, and you are free from {ym_text(lo)}", s, "when"))
    m = _BACK_BY.search(s)
    if m and int(m.group("year")) * 12 > hi + 3:
        out.append(F("dates", "fail", f"expects you back at university in {(m.group('when') or '').title()} {m.group('year')}, which means a placement far longer than your summer".replace("  ", " "), s, "length"))
    if any(f["verdict"] == "weak" and f["why"].startswith("runs ") and " to " in f["why"] for f in out):
        # The stated dates fit, so a bare "4 months" beside them needs no further check.
        out = [f for f in out if not (f["verdict"] == "cond" and f["sub"] == "length")]
    # Which season the role itself is for, when the sentence says so ("our Winter 2027 internship cohort").
    if not is_title:
        named = [(se, yr, mm) for rx in _SEASONS[1:2] for mm in rx.finditer(s) for se, yr in [(mm.group(1).lower().replace("autumn", "fall"), int(mm.group(2)))]]
        role = [(se, yr) for se, yr, mm in named
                if _SEASON_ROLE.search(s[mm.end():mm.end() + 25]) or re.search(r"(internship|co-?op|work[- ]term|placement|role|position|program(?:me)?)s?\W+(\w+\W+){0,3}(for|in|during|starting|beginning)\W+(the\W+)?$", s[max(0, mm.start() - 60):mm.start()], re.I)]
        role = [p for p in role if not re.search(r"graduat", s[max(0, s.lower().find(p[0]) - 40):s.lower().find(p[0])], re.I)]
        want = (prof["target"]["season"].lower(), int(year))
        if role and want not in [(se, yr) for se, yr, _ in named]:
            label = ", ".join(sorted({f"{se.title()} {yr}" for se, yr in role}))
            out.append(F("dates", "fail", f"is for {label}, not {want[0]} {want[1]}", s, "when"))
    return out


_FR_REQ = re.compile(r"(fluent|fluency|proficien\w+|bilingu\w+|ma[iî]trise|command of|excellent|advanced|working knowledge)[^.;]{0,50}(french|fran[cç]ais)|"
                     r"(french|fran[cç]ais)[^.;]{0,40}(required|mandatory|essential|is a must|obligatoire|requis)|"
                     r"bilingu\w+ \(?(english|anglais)\s?(/|and|&|et)\s?(french|fran[cç]ais)", re.I)
_FR_SOFT = re.compile(r"asset|nice to have|preferred|\bplus\b|bonus|atout|advantage|desirable|beneficial", re.I)


def _language(s, prof):
    if "fr" not in prof.get("languages", []) and _FR_REQ.search(s) and not _FR_SOFT.search(s):
        return [F("language", "fail", "requires French", s)]
    return []


_FORM = re.compile(r"-- ?No answer ?--|\bSelect\.\.\.|\bSelect an option\b|\* ?\*|\?\s*\*|\(required\)\s*$|^\W*(are|do|did|have|will|would|can|is|what|when|which|where|how|please (select|indicate|confirm))\b[^.]{0,200}\?\s*$", re.I)


def sentence_findings(s, prof, coop_role=True):
    if _FORM.search(s):
        return []  # a question or drop-down from the application form, not a statement of who can apply
    final_started = int(prof["degree"]["study_ends"][:4]) - 1
    out = _year(s, final_started) + _grad(s, prof) + _enrol(s, prof) + _coop(s, prof, coop_role) + _degree(s) + _dates(s, prof) + _language(s, prof)
    oks = [f for f in out if f["verdict"] in ("ok", "route")]
    if any(f["verdict"] == "route" for f in out):
        # "If you intend to return to university for an MSc you are also eligible" is permission, not a hurdle.
        out = [f for f in out if not (f["kind"] == "return" and f["verdict"] == "cond")]
    if oks:
        # Alternatives inside one sentence ("rising senior or recent graduate"): the restrictive half is not a bar.
        for f in out:
            if f["kind"] == "year" and f["verdict"] == "fail" and not _NOT_FIN.search(s):
                f["verdict"], f["why"] = "cond", "gives alternatives in one sentence: " + f["why"]
    return out


def title_findings(title, terms, prof):
    """What the title and the listing's own term labels state outright."""
    t = title or ""
    out = []
    levels = _levels(t)
    if _PHD.search(t) and "bachelor" not in levels and not re.search(r"undergrad|\bBS\b", t):
        if "master" in levels:
            out.append(F("degree", "cond", "the title names master's or PhD students; you would be an incoming master's student", t))
        else:
            out.append(F("degree", "fail", "the title names PhD students", t))
    if re.search(r"\bmba\b", t, re.I):
        out.append(F("degree", "fail", "the title names MBA students", t))
    if re.search(r"apprentice|school[- ]leaver|high[- ]school|degree apprenticeship|sixth form|year 1[0-3]\b|work experience week", t, re.I):
        out.append(F("programme", "fail", "is an apprenticeship or school-leaver programme, not a university internship", t))
    if re.search(r"\b(first|1st)[- ]year\b|spring week|spring insight|insight (week|day|programme|program)|discovery (day|programme|program)|freshm[ae]n|sophomore", t, re.I):
        out.append(F("year", "fail", "the title names a programme for first- or second-year students", t))
    if _PEN.search(t) and not re.search(r"final", t, re.I):
        out.append(F("year", "fail", "the title names penultimate-year students, and you are in your final year", t))
    want = (prof["target"]["season"].lower(), int(prof["target"]["year"]))
    in_title = seasons_in(t)
    seasons = list(in_title)
    for term in terms or ():
        seasons += [p for p in seasons_in(term) if p not in seasons]
    if seasons:
        if want in seasons:
            out.append(F("dates", "weak", f"listed for {want[0]} {want[1]}", t, "when"))
        else:
            named = ", ".join(sorted({f"{a.title()} {b}" for a, b in seasons}))
            where = "the title says" if in_title else "the list it came from labels it"
            out.append(F("dates", "fail", f"{where} {named}, not {want[0]} {want[1]}", t if in_title else named, "when"))
    if re.search(r"off[- ]?cycle", t, re.I) and want not in seasons:
        out.append(F("dates", "cond", "is an off-cycle internship; check its dates against your summer", t, "when"))
    out += [f for f in _dates(t, prof, is_title=True) if f["verdict"] != "weak"]
    for f in out:
        f["src"] = "title"
    return out


# ---------------------------------------------------------------- deadline

_DL = re.compile(r"(deadline|closing date|clos(e|es|ed|ing)( on| at)?|apply by|apply before|applications? (must be (received|submitted)|are due|due)( by| on)?|"
                 r"accepted until|open until|last day to apply|submit\w* (your application )?by)", re.I)
_DMY = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?\s*(20\d\d)?", re.I)
_MDY = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b,?\s*(20\d\d)?", re.I)
_ROLLING = re.compile(r"rolling basis|reviewed on a rolling|rolling (recruitment|applications|admissions)|may close (early|earlier|before)|close early|first[- ]come", re.I)


def find_deadline(sentences, today=None):
    """(ISO date or '', whether applications are reviewed as they arrive)."""
    today = today or datetime.date.today()
    rolling = any(_ROLLING.search(s) for s in sentences)
    for s in sentences:
        m = _DL.search(s)
        if not m:
            continue
        tail = s[m.start():m.start() + 110]
        d = _DMY.search(tail)
        day = mon = year = None
        if d:
            day, mon, year = int(d.group(1)), _MONTHS[d.group(2).lower()], d.group(3)
        else:
            d = _MDY.search(tail)
            if d:
                mon, day, year = _MONTHS[d.group(1).lower()], int(d.group(2)), d.group(3)
        if not d or not (1 <= day <= 31):
            continue
        try:
            y = int(year) if year else today.year
            date = datetime.date(y, mon, day)
            if not year and (today - date).days > 45:
                date = datetime.date(y + 1, mon, day)
        except ValueError:
            continue
        return date.isoformat(), rolling
    return "", rolling


# ---------------------------------------------------------------- verdict

_ORDER = ["year", "grad", "return", "enrol", "coop", "degree", "programme", "dates", "language"]


def evaluate(title, terms, req, prof=None, quality="none", lang=""):
    """Compare a posting with the profile. `quality` is 'full', 'partial' or 'none' (not read)."""
    prof = prof or DEFAULT_PROFILE
    found = title_findings(title, terms, prof)
    coop_role = bool(re.search(r"co-?op", title or "", re.I))
    for s in req or ():
        found += sentence_findings(html.unescape(s), prof, coop_role)
    if lang == "fr" and "fr" not in prof.get("languages", []) and not any(f["kind"] == "language" for f in found):
        found.append(F("language", "cond", "the posting is written in French and may need French", ""))

    # The posting names this candidate's own route (finalist going on to a master's): other year groups it lists are alternatives.
    if any(f["verdict"] == "route" for f in found):
        found = [f for f in found if not (f["kind"] == "year" and f["verdict"] in ("fail", "cond") and f["src"] != "title")]
    for f in found:
        if f["verdict"] == "route":
            f["verdict"] = "ok"
    # A positive and a negative statement about the same thing do not cancel: the posting is unclear on it.
    for kind in ("year", "grad"):
        oks = [f for f in found if f["kind"] == kind and f["verdict"] == "ok"]
        fails = [f for f in found if f["kind"] == kind and f["verdict"] == "fail" and f["src"] != "title"]
        if oks and fails:
            for f in fails:
                f["verdict"], f["why"] = "cond", "says two different things about this: " + f["why"]
    # Several lengths or sets of dates are options ("4, 8 or 12 months"): one that fits is enough.
    lengths = [f for f in found if f["kind"] == "dates" and f["sub"] == "length"]
    if any(f["verdict"] in ("weak", "cond") for f in lengths):
        for f in lengths:
            if f["verdict"] == "fail":
                f["verdict"], f["why"] = "note", "also offers a longer option: " + f["why"]
    if any(f["verdict"] == "weak" and " to " in f["why"] for f in lengths):
        for f in lengths:
            if f["verdict"] == "cond":
                f["verdict"] = "note"  # stated dates that fit settle a bare "about 4 months"
    rank = lambda f: _ORDER.index(f["kind"]) if f["kind"] in _ORDER else 99
    fails = sorted([f for f in found if f["verdict"] == "fail"], key=rank)
    conds = sorted([f for f in found if f["verdict"] == "cond"], key=rank)
    oks = sorted([f for f in found if f["verdict"] == "ok"], key=rank)
    weak = [f for f in found if f["verdict"] == "weak"]
    notes = [f["why"] for f in found if f["verdict"] in ("note", "weak")]

    if fails:
        f = fails[0]
        return {"state": "X", "kind": f["kind"], "reason": _cap(f["why"]), "evidence": f["text"], "quality": quality, "notes": notes, "from": f["src"]}
    if conds:
        why = _cap(conds[0]["why"])
        more = [c for c in conds[1:] if c["kind"] != conds[0]["kind"]]
        if more:
            why += " Also: " + more[0]["why"] + "."
        return {"state": "C", "kind": conds[0]["kind"], "reason": why, "evidence": conds[0]["text"], "quality": quality, "notes": notes, "from": conds[0]["src"]}
    if oks:
        f = oks[0]
        return {"state": "M", "kind": f["kind"], "reason": _cap(f["why"]), "evidence": f["text"], "quality": quality, "notes": notes, "from": f["src"]}
    if quality == "full":
        why = "Read in full: nothing about year of study, graduation date or enrolment."
        if weak:
            why = "Read in full: no year-of-study rule. It " + weak[0]["why"] + "."
    elif quality == "partial":
        why = "Only partly read: no rule found in the part that was read."
    else:
        why = "Not read yet."
    return {"state": "U", "kind": "", "reason": why, "evidence": weak[0]["text"] if weak and quality == "full" else "", "quality": quality, "notes": notes, "from": ""}


def _cap(s):
    s = s.strip()
    s = s[0].upper() + s[1:] if s else s
    return s if s.endswith(".") else s + "."
