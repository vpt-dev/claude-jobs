#!/bin/sh
# Download every source list into the folder given as $1.
set -e
mkdir -p "$1"; cd "$1"
G=https://raw.githubusercontent.com
get() { curl -sSf -m 90 -L -o "$1" "$G/$2"; }
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
get negar.md negarprh/Canadian-Tech-Internships-2026/main/README.md
get euro.md LorenzoLaCorte/european-tech-internships-2026/main/README.md
get nu_quant.md northwesternfintech/2027QuantInternships/main/README.md
get zshah.md zshah101/Automated-List-Of-Summer-2027-and-Fall-2026-Tech-Internships/main/README.md
get sndsh.md sndsh404/summer-2027-internships/main/README.md
echo fetched
