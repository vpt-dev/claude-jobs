"""Work out which country a job location is in.

One place for this logic, used by the crawler and the build. A location resolves to one or more of:
  "UK", "CA", "US"   recognised
  "XX"               recognised as somewhere else
  "??"               cannot tell (for example "Remote" or "3 Locations"); kept and shown as unknown

Nothing is assumed silently. A bare town such as "Cambridge" is a guess, so structured data from the
employer's system (`hints`) or a single-country source (`default` with `local`) overrides it.
"""
import re

US_STATES = set("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND "
                "OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split())
CA_PROV = set("ON BC QC AB MB SK NS NB NL PE".split())
CA_PROV_UNSURE = {"NL", "PE", "SK"}  # also the country codes of the Netherlands, Peru and Slovakia
ISO = {"GB": "UK", "UK": "UK", "GBR": "UK", "CA": "CA", "CAN": "CA", "US": "US", "USA": "US"}
ISO3_ELSEWHERE = set("AUS DEU FRA IND SGP HKG IRL NLD ESP ITA JPN CHN BRA MEX POL CHE SWE ISR AUT BEL DNK NOR FIN PRT ROU CZE HUN TWN KOR "
                     "ARE ZAF TUR NZL LUX GRC BGR HRV SRB UKR SVK SVN LTU LVA EST MYS THA VNM PHL IDN ARG CHL COL EGY SAU QAT NGA KEN NSW QLD".split())
ALIAS = {"ldn": "UK", "nyc": "US", "sf": "US", "south sf": "US", "dc": "US", "gta": "CA", "sgp": "XX", "hkg": "XX"}
AIRPORT = re.compile(r"^(YYZ|YVR|YUL|YOW|YYC|YEG|YWG|YHZ|YKF)\b")  # some Canadian employers label sites by airport code

UK_WORDS = re.compile(r"united kingdom|great britain|\bengland\b|\bscotland\b|northern ireland|(?<!new south )\bwales\b", re.I)
CA_WORDS = re.compile(r"\bcanada\b|\bontario\b|qu[ée]bec|british columbia|\balberta\b|manitoba|saskatchewan|nova scotia|new brunswick|newfoundland", re.I)
US_WORDS = re.compile(r"united states|\bu\.s\.a?\.?(?=\W|$)|\busa\b|bay area|washington,? d\.?c|silicon valley", re.I)
US_STATE_NAMES = re.compile(r"\b(alabama|alaska|arizona|arkansas|california|colorado|connecticut|delaware|florida|georgia|hawaii|idaho|"
                            r"illinois|indiana|iowa|kansas|kentucky|louisiana|maine|maryland|massachusetts|michigan|minnesota|mississippi|missouri|"
                            r"montana|nebraska|nevada|new hampshire|new jersey|new mexico|new york|north carolina|north dakota|ohio|oklahoma|oregon|"
                            r"pennsylvania|rhode island|south carolina|south dakota|tennessee|texas|utah|vermont|virginia|washington|west virginia|"
                            r"wisconsin|wyoming)\b", re.I)

# Country names. A few are also American town names ("Lebanon, NH", "Peru, IL"), so a US state in the
# same location wins, and a bare ambiguous name is left to the source's default.
_COUNTRIES = """afghanistan|albania|algeria|andorra|angola|anguilla|antigua|argentina|armenia|aruba|australia|austria|azerbaijan|bahamas|bahrain|
bangladesh|barbados|belarus|belgium|belize|benin|bermuda|bhutan|bolivia|bonaire|bosnia|botswana|bouvet island|brazil|brasil|brunei|bulgaria|
burkina faso|burundi|cambodia|cameroon|cape verde|cabo verde|cayman islands|central african republic|chad|chile|china|colombia|comoros|congo|
costa rica|croatia|cuba|cura[cç]ao|cyprus|czechia|czech republic|denmark|djibouti|dominica|dominican republic|ecuador|egypt|el salvador|
equatorial guinea|eritrea|estonia|eswatini|ethiopia|falkland islands|faroe islands|fiji|finland|france|french guiana|gabon|gambia|germany|
deutschland|ghana|gibraltar|greece|greenland|grenada|guadeloupe|guatemala|guernsey|guinea|guyana|haiti|holy see|honduras|hong kong|hungary|
iceland|india|indonesia|iran|iraq|ireland|isle of man|israel|italy|ivory coast|c[oô]te d'ivoire|jamaica|japan|jersey|jordan|kazakhstan|kenya|
kosovo|kuwait|kyrgyzstan|laos|latvia|lebanon|lesotho|liberia|libya|liechtenstein|lithuania|luxembourg|macau|macao|madagascar|malawi|malaysia|
maldives|mali|malta|martinique|mauritania|mauritius|mexico|micronesia|moldova|monaco|mongolia|montenegro|montserrat|morocco|mozambique|myanmar|
namibia|nepal|netherlands|new caledonia|new zealand|nicaragua|niger|nigeria|north macedonia|macedonia|norway|oman|pakistan|palestine|panama|
papua new guinea|paraguay|peru|philippines|poland|portugal|puerto rico|qatar|romania|russia|rwanda|saint barth[ée]lemy|saint kitts|
saint lucia|saint martin|saint vincent|saint helena|samoa|san marino|saudi arabia|saudi|senegal|serbia|seychelles|sierra leone|singapore|
sint maarten|slovakia|slovenia|somalia|south africa|south korea|korea|south sudan|spain|sri lanka|sudan|suriname|svalbard|sweden|switzerland|
syria|taiwan|tajikistan|tanzania|thailand|togo|tonga|trinidad|tunisia|turkey|t[uü]rkiye|turkmenistan|turks and caicos|uganda|ukraine|
united arab emirates|uae|uruguay|uzbekistan|vanuatu|vatican|venezuela|vietnam|virgin islands|yemen|zambia|zimbabwe|[aå]land islands|
new south wales|queensland|western australia|bavaria|catalonia|lombardy|piedmont|[iî]le-de-france|north holland|apac|latam""".replace("\n", "")
ELSE_COUNTRY = re.compile(r"\b(" + _COUNTRIES + r")\b", re.I)
AMBIG_COUNTRY = {"lebanon", "jordan", "peru", "cuba", "georgia", "mexico", "panama", "china", "poland", "malta", "jamaica", "norway",
                 "turkey", "chad", "greece", "jersey", "denmark", "sweden", "italy", "brazil", "egypt", "cyprus"}
# Foreign cities with no American namesake that matters: these settle the country even next to a two-letter code ("Berlin, DE" is below).
ELSE_CITY = re.compile(r"\b(bengaluru|bangalore|hyderabad|pune|mumbai|chennai|gurgaon|gurugram|noida|kolkata|new delhi|ahmedabad|tokyo|osaka|"
                       r"munich|m[uü]nchen|frankfurt|stuttgart|d[uü]sseldorf|cologne|k[oö]ln|amsterdam|rotterdam|eindhoven|utrecht|the hague|"
                       r"brisbane|auckland|shanghai|beijing|shenzhen|hangzhou|guangzhou|tel aviv|haifa|herzliya|z[uü]rich|lausanne|basel|"
                       r"stockholm|gothenburg|barcelona|krak[oó]w|wroc[lł]aw|gda[nń]sk|budapest|bucharest|cluj|seoul|taipei|hsinchu|kuala lumpur|"
                       r"bangkok|jakarta|s[aã]o paulo|mexico city|guadalajara|monterrey|buenos aires|bogot[aá]|medell[ií]n|johannesburg|cape town|"
                       r"nairobi|riyadh|abu dhabi|dubai|istanbul|tallinn|vilnius|kyiv|bratislava|tbilisi|yerevan|ho chi minh|hanoi|"
                       r"aarhus|aachen|brno|ljubljana)\b", re.I)
# A shared-name city next to the two-letter code of its own country, which is also a US state code ("Berlin, DE").
SHARED_ISO = {"berlin": "DE", "hamburg": "DE", "delhi": "IN", "casablanca": "MA", "rabat": "MA", "baku": "AZ", "tirana": "AL"}
DELAWARE = set("wilmington newark dover middletown lewes georgetown milford smyrna seaford claymont bear".split()) | {"new castle"}
# Lone two-letter codes that are both a US state and another country: left to the source's default.
STATE_OR_COUNTRY = set("CA DE IN IL CO AR ID MA PA AL AZ GA LA MD ME MN MO MS MT NC NE SC SD TN VA KY".split())
# Foreign cities that share a name with American towns ("Dublin, OH", "Melbourne, FL"): a US state in the location wins.
ELSE_CITY_SHARED = re.compile(r"\b(berlin|hamburg|paris|lyon|toulouse|grenoble|dublin|cork|limerick|galway|sydney|melbourne|perth|adelaide|"
                              r"geneva|madrid|valencia|seville|warsaw|prague|lisbon|porto|milan|rome|turin|naples|florence|vienna|brussels|"
                              r"antwerp|copenhagen|oslo|helsinki|manila|delhi|santiago|lima|cairo|lagos|doha|sofia|belgrade|zagreb|riga|"
                              r"athens|canberra|wellington|christchurch|casablanca|rabat|accra|dakar|almaty|baku|tirana)\b", re.I)
_VAGUE_WORD = (r"(fully |100% )?(remote|hybrid|flexible|various|multiple|several|anywhere|worldwide|global|europe|emea|uki|americas|north america|"
               r"nationwide|tbc|tbd|n/?a|none|not listed|not specified|unspecified|see (job )?description|multiple (locations?|cities|sites)"
               r"( available)?|remote[- ]first|work from home|home[- ]based|virtual|telecommut\w*|in[- ]office|on[- ]?site|office[- ]based|"
               r"headquarters|head office|hq|field|distributed|location flexible|\d+ locations?)")
VAGUE = re.compile(r"^\W*(?:" + _VAGUE_WORD + r"(?:\W+(?:(?:or|and)\W+)?)?)*$", re.I)

# Town names, lower case. A bare town is a guess, never proof (see NAMESAKE).
UK_TOWNS = {t.strip() for t in """london,manchester,edinburgh,glasgow,belfast,bristol,leeds,birmingham,cambridge,oxford,reading,cardiff,newcastle,
newcastle upon tyne,sheffield,nottingham,liverpool,southampton,portsmouth,milton keynes,swindon,cheltenham,guildford,warwick,coventry,leicester,
aberdeen,dundee,bath,brighton,luton,slough,basingstoke,farnborough,stevenage,derby,gloucester,norwich,ipswich,exeter,plymouth,harwell,didcot,
crawley,woking,maidenhead,bracknell,hursley,winchester,salford,bolton,warrington,telford,solihull,redhill,croydon,uxbridge,watford,st albans,
welwyn garden city,welwyn,hatfield,chester,lancaster,durham,sunderland,hull,wolverhampton,stoke-on-trent,peterborough,northampton,bedford,
malvern,daresbury,bournemouth,poole,cranfield,york,canary wharf,wembley,ealing,hounslow,kingston upon thames,staines,egham,weybridge,
leatherhead,epsom,dorking,newbury,abingdon,banbury,bicester,filton,yeovil,taunton,barrow-in-furness,preston,blackpool,lincoln,stirling,
inverness,livingston,swansea,wrexham,londonderry,lisburn,shirebrook,mansfield,chelmsford,colchester,harlow,romford,ilford,greenwich,
hammersmith,chippenham,leamington spa,royal leamington spa,harrogate,knutsford,macclesfield,crewe,gaydon,whitley,warton,samlesbury,chertsey,
sunbury-on-thames,hemel hempstead,high wycombe,marlow,theale,dunfermline,paisley,east kilbride,motherwell,runcorn,wilmslow,cheadle,
stockport,oldham,rochdale,huddersfield,bradford,wakefield,doncaster,rotherham,barnsley,middlesbrough,stockton-on-tees,gateshead,carlisle,
hereford,shrewsbury,stafford,burton upon trent,loughborough,kettering,corby,nuneaton,tamworth,lichfield,walsall,west bromwich,oxfordshire,
berkshire,hampshire,hertfordshire,buckinghamshire,west midlands,greater manchester,west yorkshire,south yorkshire,merseyside,tyne and wear,
city of london,westminster,shoreditch,paddington,kings cross,king's cross,stratford-upon-avon,fareham,gosport,havant,eastleigh,horsham,
haywards heath,tunbridge wells,maidstone,dartford,gravesend,basildon,southend-on-sea,cambourne,huntingdon,st neots,king's lynn,lowestoft,
great yarmouth,bury st edmunds,felixstowe,martlesham,adastral park,goonhilly,culham,sellafield,aldermaston,porton down,farnham,camberley,
aldershot,bagshot,wokingham,thatcham,cirencester,tewkesbury""".replace("\n", "").split(",")}
CA_TOWNS = {t.strip() for t in """toronto,vancouver,montreal,montréal,ottawa,waterloo,calgary,edmonton,mississauga,kitchener,winnipeg,halifax,
kanata,markham,burnaby,brampton,vaughan,richmond hill,oakville,scarborough,north york,etobicoke,pickering,ajax,whitby,oshawa,guelph,
saskatoon,regina,gatineau,laval,kelowna,fredericton,moncton,st. john's,thornhill,north vancouver,quebec city,québec city,longueuil,
stouffville,caledon,orangeville,barrie,thunder bay,st. catharines,st catharines,sherbrooke,trois-rivières,saguenay,lévis,brossard,dorval,
pointe-claire,saint-laurent,mirabel,coquitlam,kitchener-waterloo,west vancouver,abbotsford,nanaimo,kamloops,red deer,lethbridge,fort mcmurray,charlottetown,mount pearl,
waterdown,chalk river,toronto area,vancouver area,montreal area,edmonton metropolitan area,nepean,stittsville,east york,downsview,
don mills""".replace("\n", "").split(",")}
US_TOWNS = {t.strip() for t in """new york,new york city,san francisco,south san francisco,seattle,chicago,boston,austin,los angeles,san jose,
san diego,palo alto,mountain view,sunnyvale,menlo park,redmond,bellevue,denver,atlanta,dallas,houston,miami,philadelphia,pittsburgh,washington,
arlington,santa clara,cupertino,irvine,portland,phoenix,detroit,minneapolis,raleigh,nashville,salt lake city,brooklyn,manhattan,jersey city,
bala cynwyd,cincinnati,cleveland,columbus,indianapolis,milwaukee,kansas city,st. louis,st louis,charlotte,tampa,orlando,sacramento,oakland,
san mateo,redwood city,foster city,santa monica,culver city,el segundo,pasadena,boulder,plano,irving,fort worth,san antonio,las vegas,
tucson,albuquerque,omaha,madison,ann arbor,princeton,hoboken,stamford,hartford,baltimore,reston,mclean,tysons,herndon,bethesda,
state college,los gatos,huntington beach,eden prairie,farmington hills,westport,berkeley,scottsdale,tempe,chandler,boise,provo,lehi,
draper,kirkland,bothell,everett,tacoma,spokane,honolulu,anchorage,buffalo,rochester,albany,syracuse,newark,wilmington,providence,
new haven,lowell,waltham,framingham,quincy,somerville,chapel hill,cary,morrisville,research triangle park,huntsville,knoxville,memphis,
louisville,lexington,new orleans,baton rouge,oklahoma city,tulsa,des moines,sioux falls,fargo,green bay,grand rapids,fort lauderdale,
boca raton,west palm beach,jacksonville,charleston,savannah,norfolk,virginia beach,chantilly,fairfax,alexandria,annapolis,rockville,
gaithersburg""".replace("\n", "").split(",")}
# Towns that also exist, as real job locations, in another of the three countries. When the employer's own data or a
# single-country source names that other country, it is believed over the guess.
NAMESAKE = {
    "US": set("cambridge manchester birmingham reading bristol lancaster lincoln plymouth portsmouth durham york greenwich bedford warwick "
              "chester norwich gloucester mansfield chelmsford livingston winchester northampton brighton exeter bath hull newcastle derby "
              "preston aberdeen stafford oxford ipswich taunton swansea epsom colchester abingdon croydon warrington malvern telford "
              "cheltenham bolton stockport bradford wakefield carlisle hereford shrewsbury kettering".split())
          | {"st albans"},
    "CA": set("london cambridge peterborough bolton brighton uxbridge bedford gloucester".split()),
    "UK": set("halifax waterloo scarborough whitby pickering brampton ajax".split()),
}
TOSS_UP = {"halifax"}  # a real centre of employment in both Nova Scotia and West Yorkshire
_NOISE = re.compile(r"\s*\((hybrid|remote|on-?site|in-?office|flexible|hq|headquarters)\)|\s*\+\s*\d+(\s*(more|others?))?\s*$|[​‌‍﻿]|"
                    r"\s+(office|headquarters|hq|campus|metropolitan area|metro area|region)\s*$", re.I)
_REMOTE_IN = re.compile(r"^\s*(?:(?:fully\s+)?remote|hybrid|home[- ]based)\s*(?:\b(?:in|within|from|or)\b|[-–:,/(])\s*(?=\w)|^\s*(?:greater|city of)\s+", re.I)
_PREFIX_TOWN = re.compile(r"(?:(?:central|north|south|east|west|downtown|inner|outer)\s+)?(london|toronto|mississauga|vancouver|montreal|montréal|ottawa|calgary|edmonton|winnipeg|glasgow|edinburgh|"
                          r"liverpool|belfast|cardiff|leeds|san francisco|seattle|chicago|los angeles)\b")


def tidy(loc):
    """A location with work-mode notes, "+2", office labels and the like removed. Returns (text, had a "Remote in" prefix)."""
    s = (loc or "").strip()
    for _ in range(3):
        s = _NOISE.sub("", s).strip(" -–,;/")
    m = _REMOTE_IN.match(s)
    if m and not VAGUE.match(s):
        rest = s[m.end():].strip(" -–,;/()")
        if rest:
            return rest, bool(re.match(r"\s*(fully\s+)?remote", s, re.I))
    return s, False


def classify(loc):
    """Read one location on its own.

    Returns (codes, town): codes is a list from "UK", "CA", "US", "XX"; or ["??"] for a vague location;
    or ["~"] for a place name this module does not know. `town` is set when the answer rests only on a
    bare town name, which is a guess.
    """
    raw = (loc or "").strip()
    if VAGUE.match(raw):
        return ["??"], None
    s, remote_in = tidy(raw)
    if not s or VAGUE.match(s) or not re.search(r"[A-Za-zÀ-ÿ]", s):
        return ["??"], None
    low = s.lower()
    if low in ALIAS:
        return [ALIAS[low]], None
    if AIRPORT.match(s):
        return ["CA"], None
    if s.upper() in ISO and s.upper() != "CA":
        return [ISO[s.upper()]], None
    # "Plano TX", "NJ - Hamilton", "WI-Milwaukee", "MA Needham ..." carry a state code without a comma.
    s2 = re.sub(r"^([A-Z]{2})\s*[-–]\s*(?=[A-Za-z])", r"\1, ", s)
    s2 = re.sub(r"^([A-Z]{2}) (?=[A-Z][a-z])", r"\1, ", s2)
    s2 = re.sub(r"(?<=[a-z]) ([A-Z]{2})$", r", \1", s2)
    s2 = re.sub(r"(?<=[a-z])-([A-Z]{2})$", r", \1", s2)
    parts = [p.strip() for p in re.split(r"\s+[-–]\s+|[,/|;()]|\s+(?:or|and|&)\s+", s2) if p.strip()]
    names = [p.lower() for p in parts]
    tokens = set(re.findall(r"\b[A-Z]{2,3}\b", s2))

    if re.match(r"ontario,\s*(ca|california)\b", low):
        return ["US"], None  # the city in California
    ca_town = next((n for n in names if n in CA_TOWNS), None)
    explicit = []
    if UK_WORDS.search(low) or tokens & {"UK", "GB", "GBR"}:
        explicit.append("UK")
    prov = tokens & CA_PROV
    if CA_WORDS.search(low) or "CAN" in tokens or prov - CA_PROV_UNSURE or (prov and ca_town):
        explicit.append("CA")
    if US_WORDS.search(s) or "USA" in tokens or re.search(r"\bUS\b", s):
        explicit.append("US")
    if explicit:
        # "London, ON, Canada" and "Cambridge, UK" are settled by the stated country, not the town.
        return explicit, None
    if ELSE_CITY.search(low) or tokens & ISO3_ELSEWHERE:
        return ["XX"], None
    codes = {p for p in parts if len(p) == 2 and p.isupper() and p in US_STATES} if len(parts) > 1 else set()
    shared = ELSE_CITY_SHARED.search(low)
    if shared and codes == {SHARED_ISO.get(shared.group(1).lower())}:
        return ["XX"], None
    if codes == {"DE"} and not any(n in DELAWARE for n in names):
        return ["XX"], None  # ", DE" is far more often Germany than Delaware
    state_name = bool(US_STATE_NAMES.search(low)) and not (low == "georgia" and remote_in)
    if ca_town and codes <= {"CA"} and not state_name:
        if ca_town in NAMESAKE["UK"] and any(n in UK_TOWNS for n in names):
            return ["UK"], None  # "Waterloo, London", "Halifax, West Yorkshire"
        if ca_town in TOSS_UP and not codes:
            return ["CA", "UK"], ca_town  # shown under both until something settles it
        return ["CA"], (None if codes else ca_town)  # "Toronto, CA" uses the country code
    if codes or state_name:
        return ["US"], None
    if len(s) == 2 and s.isupper() and s in US_STATES:
        return (["~"] if s in STATE_OR_COUNTRY else ["US"]), None
    if len(parts) > 1 and re.fullmatch(r"[A-Z]{2}", parts[-1]) and parts[-1] not in US_STATES | CA_PROV | set(ISO):
        return ["XX"], None  # a two-letter country code other than the three ("Milan, IT", "Ayutthaya, TH")
    m = ELSE_COUNTRY.search(low)
    if m and not (m.group(1).lower() == "jersey" and low != "jersey"):
        if m.group(1).lower() in AMBIG_COUNTRY and len(parts) == 1 and not remote_in:
            return ["~"], None
        return ["XX"], None
    for n in names:
        for towns, code in ((UK_TOWNS, "UK"), (US_TOWNS, "US")):
            if n in towns:
                return [code], n
        # "London Wall", "Central London", "Toronto Headquarters": a distinctive town with an address or label around it.
        first = _PREFIX_TOWN.match(n)
        if first:
            t = first.group(1)
            return ["CA" if t in CA_TOWNS else "UK" if t in UK_TOWNS else "US"], t
    if shared or (remote_in and prov):
        return ["XX"], None
    if re.search(r"\b(remote|hybrid)\b", low) and len(parts) <= 1:
        return ["??"], None
    return ["~"], None


def _settle(loc, default, local, known):
    """(codes, kind) for one location; kind is "ok", "vague" or "unknown"."""
    cs, town = classify(loc)
    if cs == ["~"]:
        return ([default], "ok") if default in ("US", "UK", "CA", "XX") else (["??"], "unknown")
    if cs == ["??"]:
        return ([default], "ok") if local and default in ("US", "UK", "CA") else (["??"], "vague")
    if town:
        for k in list(known) + ([default] if local and default in ("US", "UK", "CA") else []):
            if len(cs) > 1 and k in cs:
                return [k], "ok"  # a toss-up settled by what else is known
            if k in NAMESAKE and k not in cs and town in NAMESAKE[k]:
                return [k], "ok"
    return cs, "ok"


def codes_of(loc, default=None, local=False, known=()):
    """Countries for one location, using what else is known.

    default  the country a source mostly covers; settles place names this module does not know
    local    the source covers only that country (a UK-only or Canada-only list): vague locations
             and towns with a namesake there are taken to be in it too
    known    countries already established from the employer's structured data
    """
    return _settle(loc, default, local, known)[0]


def country_of(loc, default=None, local=False):
    """The first country for one location: "UK", "CA", "US", "XX" (elsewhere) or "??" (cannot tell)."""
    return codes_of(loc, default, local)[0]


def countries(locs, hints=(), default=None, local=False):
    """Countries for a job.

    `hints` come from the employer's system: "iso:GB" for a country-code field, or a plain name such as
    "United Kingdom" or an office called "London". Code fields and explicit names are believed over
    bare town names in `locs`.

    Returns a list drawn from US, UK, CA. An empty list means the job is somewhere else.
    ["??"] means the location could not be worked out.
    """
    known, extra = [], []
    for h in hints or ():
        h = (h or "").strip()
        if h.lower().startswith("iso:"):
            code = h[4:].strip().upper()
            got = [ISO.get(code, "XX")] if code else []
        else:
            cs, town = classify(h) if h else (["??"], None)
            if town or cs[0] in ("??", "~"):
                if h:
                    extra.append(h)  # an office called "Cambridge" is no better than a location called "Cambridge"
                continue
            got = cs
        for c in got:
            if c not in known:
                known.append(c)
    seen = [c for c in known if c != "XX"]
    elsewhere, vague, unknown = "XX" in known, False, False
    every = list(locs or ()) + extra
    # Locations that state their country outright are read first, so that they can settle the bare towns beside them
    # ("Cambridge" next to "Boston, MA").
    stated = list(known)
    for loc in every:
        cs, town = classify(loc)
        if not town:
            stated += [c for c in cs if c in ("US", "UK", "CA") and c not in stated]
    for loc in every:
        cs, kind = _settle(loc, default, local, stated)
        vague = vague or kind == "vague"
        unknown = unknown or (kind == "unknown" and not known)  # the employer's country field covers a name we do not know
        for c in cs:
            if c in ("US", "UK", "CA"):
                if c not in seen:
                    seen.append(c)
            elif c == "XX":
                elsewhere = True
    if seen:
        return seen
    if unknown:
        return ["??"]  # a place name nobody recognised: it may be in one of the three countries
    if elsewhere:
        return []  # "Berlin; Remote" is treated as Berlin
    if vague or not (locs or hints):
        return [default] if local and default in ("US", "UK", "CA") else ["??"]
    return []


def from_text(fragments):
    """Countries named in free text such as a job title or a link ("... Intern - London", ".../job/London-United-Kingdom/...").

    Only fragments that are exactly a known place count. Returns a list from US, UK, CA; [] when the
    text names somewhere else; None when it names no place at all.
    """
    seen, elsewhere = [], False
    for f in fragments or ():
        cs, _ = classify(f)
        for c in cs:
            if c in ("US", "UK", "CA") and c not in seen:
                seen.append(c)
            elsewhere = elsewhere or c == "XX"
    return seen if seen else [] if elsewhere else None


def url_place(url):
    """The location a Workday link carries in its path (".../job/London-United-Kingdom/Title_R123"), as text."""
    m = re.search(r"myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?[^/]+/job/([^/?#]+)/[^/?#]+", url or "")
    if not m:
        return ""
    slug = m.group(1)
    # "US-CA-Santa-Clara" and "UK-Reading" lead with codes; the rest are hyphenated names.
    lead = re.match(r"^((?:[A-Z]{2,3}-)+)(.*)$", slug)
    if lead:
        return ", ".join(lead.group(1).strip("-").split("-")) + ", " + lead.group(2).replace("-", " ")
    return slug.replace("---", ", ").replace("-", " ")


_CITY_ALIAS = {"nyc": "new york", "new york city": "new york", "ldn": "london", "sf": "san francisco", "south sf": "south san francisco",
               "toronto area": "toronto", "gta": "toronto", "montréal": "montreal", "city of london": "london", "canary wharf": "london"}
_NOT_A_CITY = {"united kingdom", "uk", "canada", "usa", "united states", "england", "scotland", "wales", "ontario", "us", "remote",
               "great britain", "quebec", "british columbia", "alberta"}


def city_keys(locs):
    """Town-level names in a job's locations, for deciding whether two listings are the same vacancy."""
    out = set()
    for loc in locs or ():
        s, _ = tidy(loc)
        s = re.sub(r"^([A-Z]{2})\s*[-–]\s*(?=[A-Za-z])", "", s)
        s = re.sub(r"(?<=[a-z])[ -]([A-Z]{2})$", "", s)
        # The town is usually the first part ("London, UK"), but some lists lead with the country ("UK, Bristol").
        for part in re.split(r"[,/|;(]|\s+[-–]\s+", s)[:3]:
            name = re.sub(r"[^a-zà-ÿ .'-]", "", part.strip().lower()).strip()
            name = _CITY_ALIAS.get(name, name)
            if not name or VAGUE.match(name) or name in _NOT_A_CITY or (len(name) == 2 and name.upper() in US_STATES | CA_PROV):
                continue
            out.add(name)
            break
    return out
