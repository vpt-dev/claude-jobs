#!/bin/sh
# Download every source list into the folder given as $1.
mkdir -p "$1"; cd "$1"
G=https://raw.githubusercontent.com
# A list that fails to download keeps its previous copy, so one missing source never stops a refresh.
STATUS=fetch_status.tsv; : > "$STATUS.new"
# A download much smaller than the copy from the last few days is treated as cut short and not used.
get() {
  old=0; [ -f "$1" ] && old=$(wc -c < "$1" | tr -d ' ')
  if curl -sSf -m 90 -L -o "$1.new" "$G/$2" && [ -s "$1.new" ]; then
    new=$(wc -c < "$1.new" | tr -d ' ')
    if [ "$old" -gt 20000 ] && [ "$new" -lt $((old / 2)) ] && [ -z "$(find "$1" -mtime +3 2>/dev/null)" ]; then
      rm -f "$1.new"; echo "  $2 came back much smaller than before (kept the last copy)"; printf '%s\tshrunk\n' "$1" >> "$STATUS.new"
    else mv "$1.new" "$1"; printf '%s\tok\n' "$1" >> "$STATUS.new"; fi
  else rm -f "$1.new"; echo "  could not fetch $2 (kept the last copy)"; [ -f "$1" ] || : > "$1"; printf '%s\tfailed\n' "$1" >> "$STATUS.new"; fi
}
get simplify_intern.out SimplifyJobs/Summer2027-Internships/dev/.github/scripts/listings.json
get simplify_newgrad.out SimplifyJobs/New-Grad-Positions/dev/.github/scripts/listings.json
get vansh_intern.out vanshb03/Summer2027-Internships/dev/.github/scripts/listings.json
get vansh_newgrad.out vanshb03/New-Grad-2027/dev/.github/scripts/listings.json
for r in SWE AI; do l=$(echo $r | tr A-Z a-z)
  get speedy_${l}.md speedyapply/2027-$r-College-Jobs/main/README.md
  get speedy_${l}_ng.md speedyapply/2027-$r-College-Jobs/main/NEW_GRAD_USA.md
  get speedy_${l}_intl.md speedyapply/2027-$r-College-Jobs/main/INTERN_INTL.md
  get speedy_${l}_ng_intl.md speedyapply/2027-$r-College-Jobs/main/NEW_GRAD_INTL.md
done
get negar.md negarprh/Canadian-Tech-Internships-2027/HEAD/README.md
get euro.md LorenzoLaCorte/european-tech-internships-2026/main/README.md
get nu_quant.md northwesternfintech/2027QuantInternships/main/README.md
get zshah.md zshah101/Automated-List-Of-Summer-2027-and-Fall-2026-Tech-Internships/main/README.md
get sndsh.md sndsh404/summer-2027-internships/main/README.md
get emj_us.md Emjumaev/FAANG-2027-Internships-Tracker/HEAD/README.md
get emj_eu.md Emjumaev/FAANG-2027-Internships-Tracker-Europe/HEAD/README.md
get frogg.md seun-ipaye/frogg-canadian-internships/HEAD/README.md
get krishi.md krishi-shah/Toronto-AI-ML-internship-radar/HEAD/README.md
get francklin.md Francklin9999/canada-internship/HEAD/README.md
get quantscraper.md quant-scraper/Quant-Internships-New-Grad-2027/HEAD/README.md
get aprameyak.md aprameyak/2027-tech-jobs/HEAD/README.md
get bobwillrule.md Bobwillrule/Canadian-Internship-List/HEAD/README.md
get ottawa.md Bhadri-Air/ottawa-internship/HEAD/README.md
get eurotech.md jordan-belfort-ai/European-Tech-Internships-2027/HEAD/README.md
get nihal.md nihalmohammed18/New-Grad-and-Internships-2027/HEAD/README.md
get babbling.md babblinglabs/Internships-2027/HEAD/README.md
get michelle.md michelleokolie/canada-tech-internships-summer-2027/HEAD/README.md
get mazen.md mazentalsam/Canada-CS-Internships-New-Grad/HEAD/README.md
get dw_uk.md dreamworkhq/Tech-Internships-2027/main/international/united-kingdom.md
get dw_ca.md dreamworkhq/Tech-Internships-2027/main/international/canada.md
get grind_uk.md grind-fyi/Software-Internships-UK/HEAD/README.md
get grind_ca.md grind-fyi/Software-Internships-Canada/HEAD/README.md
get grind_uk_ng.md grind-fyi/Software-NewGrad-UK/HEAD/README.md
get grind_ca_ng.md grind-fyi/Software-NewGrad-Canada/HEAD/README.md
echo fetched
mv "$STATUS.new" "$STATUS"
