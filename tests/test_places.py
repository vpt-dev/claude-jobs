import places as P

# One location on its own. "??" = vague, kept as unknown. "~" = a name the module does not know.
ONE = {
    # explicit countries
    "London, UK": "UK", "London, England, United Kingdom": "UK", "Remote - UK": "UK", "United Kingdom (Remote)": "UK", "Edinburgh, Scotland": "UK",
    "Cardiff, Wales": "UK", "Belfast, Northern Ireland": "UK", "GB": "UK", "London UK": "UK", "Remote in United Kingdom": "UK",
    "Toronto, ON": "CA", "Toronto, Ontario, Canada": "CA", "Remote (Canada)": "CA", "Vancouver, BC": "CA", "Montréal, QC": "CA",
    "London, ON, Canada": "CA", "London, Ontario": "CA", "Cambridge, Ontario": "CA", "Toronto, CA": "CA", "CA-Toronto": "CA", "Sydney, NS": "CA",
    "St. John's, NL": "CA", "Toronto ON": "CA", "Remote in Canada": "CA",
    "New York, NY": "US", "Remote - US": "US", "San Francisco Bay Area": "US", "Remote, USA": "US", "United States": "US", "Austin, Texas": "US",
    "Plano TX": "US", "NJ - Hamilton": "US", "WI-Milwaukee": "US", "MA Needham 117 Kendrick St": "US", "Boston-MA": "US", "FL": "US",
    # the same name in more than one country
    "Cambridge, MA": "US", "Cambridge, UK": "UK", "Reading, PA": "US", "Birmingham, AL": "US", "Manchester, NH": "US", "Vancouver, WA": "US",
    "Ontario, CA": "US", "London, KY": "US", "Dublin, OH": "US", "Dublin, CA": "US", "Melbourne, FL": "US", "Vienna, VA": "US", "Warsaw, IN": "US",
    "Paris, TX": "US", "Lebanon, NH": "US", "Peru, IL": "US", "West Jordan, UT": "US", "Jersey City, NJ": "US", "Wilmington, DE": "US",
    "San Juan Capistrano, CA": "US", "Halifax, West Yorkshire": "UK", "Waterloo, London": "UK", "Guildford, Surrey": "UK",
    # elsewhere
    "New South Wales": "XX", "Newcastle, New South Wales": "XX", "Sydney, Australia": "XX", "Dublin, Ireland": "XX", "Dublin": "XX",
    "Berlin, DE": "XX", "Walldorf, DE": "XX", "Bengaluru": "XX", "Bangalore, IN": "XX", "Tel Aviv, IL": "XX", "Amsterdam, NL": "XX",
    "Singapore": "XX", "SGP": "XX", "HKG": "XX", "Turin, Piedmont, ITA": "XX", "Iasi, ROU": "XX", "Amancio, Cuba": "XX", "Kingston, Jamaica": "XX",
    "Remote in Russia": "XX", "Remote in Jersey": "XX", "Remote in Isle of Man": "XX", "Remote in Holy See (Vatican City State)": "XX",
    "Remote in Lebanon": "XX", "Munich, Germany": "XX", "Milan, IT": "XX", "Phra Nakhon Si Ayutthaya,, BangPa-in, TH": "XX", "Paris": "XX", "Tbilisi, Georgia": "XX", "Mexico City": "XX", "Lima, Peru": "XX",
    # bare towns (guesses)
    "London": "UK", "London +1": "UK", "LDN": "UK", "Central London": "UK", "London Wall": "UK", "Greater London": "UK", "City of London": "UK",
    "Hybrid - London": "UK", "London (Hybrid)": "UK", "Glasgow Campus (Hybrid)": "UK", "Reading": "UK", "Chippenham": "UK", "Welwyn": "UK",
    "Toronto": "CA", "Greater Toronto Area": "CA", "Toronto Headquarters": "CA", "Montreal +3": "CA", "Calgary Headquarters": "CA", "YOW B": "CA",
    "Kitchener/Waterloo": "CA", "Remote or Mississauga": "CA", "Mississauga Milverton Drive": "CA", "Greater Edmonton Metropolitan Area": "CA",
    "New York": "US", "NYC": "US", "South SF": "US", "Houston +2": "US", "Bala Cynwyd": "US", "Jersey City": "US", "San Francisco Office": "US",
    # cannot tell
    "Remote": "??", "": "??", "3 Locations": "??", "8 Locations (Hybrid)": "??", "In-Office": "??", "Hybrid": "??", "Multiple Cities": "??",
    "—": "??", "— (Hybrid)": "??", "EMEA": "??", "Europe": "??", "Remote - Multiple Locations": "??", "not listed": "??", "Worldwide": "??",
    "Lebanon": "~", "Georgia": "US", "Remote in Georgia": "~", "CA": "~", "DE": "~", "Saguenay": "CA", "Zug": "~", "Leamington Spa": "UK",
    "Hamilton": "~", "Richmond": "~",
}
for loc, want in ONE.items():
    got = P.classify(loc)[0]
    check(got[0] == want, f"places: {loc!r}", f"-> {got}, wanted {want}")

check(P.classify("Remote, US or Canada")[0] == ["CA", "US"], "places: one location naming two countries")
check(P.classify("London")[1] == "london" and P.classify("London, UK")[1] is None, "places: a bare town is marked as a guess")
check(P.classify("Halifax")[0] == ["CA", "UK"] and P.classify("Halifax, NS")[0] == ["CA"], "places: Halifax alone is a toss-up")
check(P.url_place("https://lseg.wd3.myworkdayjobs.com/Graduate_Careers/job/London-United-Kingdom/Software-Engineer-Intern_R0124267") == "London United Kingdom"
      and P.from_text([P.url_place("https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/US-CA-Santa-Clara/Intern_JR1")]) == ["US"]
      and P.from_text([P.url_place("https://x.wd1.myworkdayjobs.com/en-US/jobs/job/Bangalore-Karnataka-India/Intern_R1")]) == []
      and P.from_text(["Getafe"]) is None and P.url_place("https://boards.greenhouse.io/x/jobs/1") == "", "places: the place in a Workday link")
check(P.from_text(["London", "UK"]) == ["UK"] and P.from_text(["Lyon"]) == [] and P.from_text(["Platform Team"]) is None, "places: places named in a title")

# A whole job: locations, the employer system's structured data, and what the source is known to cover.
JOBS = [
    (dict(locs=["Reading"]), ["UK"]), (dict(locs=["Reading, PA"]), ["US"]), (dict(locs=["3 Locations"]), ["??"]),
    (dict(locs=["Remote"]), ["??"]), (dict(locs=[]), ["??"]), (dict(locs=["New South Wales"]), []), (dict(locs=["Zug"]), ["??"]),
    (dict(locs=["Berlin", "Remote"]), []), (dict(locs=["Berlin", "Zug"]), ["??"]), (dict(locs=["London", "New York"]), ["UK", "US"]),
    # the employer's own country field settles a bare town
    (dict(locs=["Cambridge"], hints=["iso:US"]), ["US"]), (dict(locs=["Cambridge"], hints=["iso:GB"]), ["UK"]),
    (dict(locs=["Cambridge"], hints=["United States of America"]), ["US"]), (dict(locs=["London"], hints=["iso:CA"]), ["CA"]),
    (dict(locs=["Halifax"], hints=["iso:GB"]), ["UK"]), (dict(locs=["Halifax"], hints=["iso:CA"]), ["CA"]),
    (dict(locs=["Remote"], hints=["iso:gb"]), ["UK"]), (dict(locs=["3 Locations"], hints=["United Kingdom"]), ["UK"]),
    (dict(locs=["Chippenham"], hints=["iso:GB"]), ["UK"]), (dict(locs=["Remote"], hints=["iso:DE"]), []), (dict(locs=["Zug"], hints=["iso:CH"]), []),
    # but a second, distinctive location is not lost
    (dict(locs=["New York", "London"], hints=["iso:US"]), ["US", "UK"]), (dict(locs=["London", "Toronto"], hints=["iso:GB"]), ["UK", "CA"]),
    (dict(locs=["Munich", "London, UK"], hints=["iso:DE"]), ["UK"]),
    # an office name is not a country code
    (dict(locs=["Remote"], hints=["NYC"]), ["US"]), (dict(locs=["Remote"], hints=["SF", "London"]), ["US", "UK"]),
    (dict(locs=["Cambridge, MA"], hints=["Cambridge"]), ["US"]), (dict(locs=["In-Office"], hints=["London, United Kingdom"]), ["UK"]),
    # single-country lists
    (dict(locs=["Remote"], default="CA", local=True), ["CA"]), (dict(locs=["In-Office"], default="UK", local=True), ["UK"]),
    (dict(locs=["London"], default="CA", local=True), ["CA"]), (dict(locs=["Halifax"], default="UK", local=True), ["UK"]),
    (dict(locs=["Dawson Hall"], default="CA", local=True), ["CA"]), (dict(locs=["Munich, Germany"], default="CA", local=True), []),
    (dict(locs=["Seattle, WA"], default="CA", local=True), ["US"]), (dict(locs=[], default="UK", local=True), ["UK"]),
    # general lists: a default settles unknown names only
    (dict(locs=["Remote"], default="US"), ["??"]), (dict(locs=["Los Altos Hills"], default="US"), ["US"]), (dict(locs=["London"], default="US"), ["UK"]),
    (dict(locs=["Manchester"], default="US"), ["UK"]), (dict(locs=["Remote"], default="XX"), ["??"]), (dict(locs=["Zug"], default="XX"), []),
    (dict(locs=["London +1"], default="XX"), ["UK"]), (dict(locs=["2 Locations"], default="XX"), ["??"]), (dict(locs=["Montreal +1"], default="XX"), ["CA"]),
    (dict(locs=["Remote in Russia", "Remote in United Kingdom", "Remote in Jersey"], default="US"), ["UK"]),
]
for kw, want in JOBS:
    got = P.countries(kw.get("locs"), kw.get("hints", ()), kw.get("default"), kw.get("local", False))
    check(got == want, f"places: job {kw}", f"-> {got}, wanted {want}")

check(P.city_keys(["London, UK", "In-Office", "London (Hybrid)", "Greater Toronto Area", "NYC", "Plano TX", "Remote"]) ==
      {"london", "toronto", "new york", "plano"}, "places: city keys", str(P.city_keys(["London, UK", "In-Office", "London (Hybrid)", "Greater Toronto Area", "NYC", "Plano TX", "Remote"])))
