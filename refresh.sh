#!/bin/bash
# Refresh the job board from this computer and publish it.
#   refresh.sh quick   source lists + Reed + posting checks (a few minutes)
#   refresh.sh full    the above plus the employer-board crawl (about an hour)
# Run from inside a clone of the repository. Scratch files go in ../work.
MODE="${1:-quick}"
cd "$(dirname "$0")" || exit 1
WORK="../work"; RAW="$WORK/raw"; mkdir -p "$RAW"
step() { echo; echo "== $1"; }
fail() { echo; echo "STOPPED: $1"; echo "Nothing was published. The live site is unchanged."; exit 1; }

step "Getting the latest code"
git pull --rebase --autostash -q || fail "could not update from GitHub (check your internet connection)"

step "Downloading the source lists"
sh pipeline/fetch.sh "$RAW"
cp data/manual.json "$RAW/manual.json"

if [ "$MODE" = "full" ]; then
  step "Crawling employer job boards (about an hour)"
  if python3 crawl.py seeds.json "$WORK/ats_jobs.json"; then cp "$WORK/ats_jobs.json" data/ats_jobs.json
  else echo "The crawl did not finish cleanly, so the previous crawl results are kept."; fi
fi
cp data/ats_jobs.json "$RAW/ats_jobs.json"

KEY="${REED_KEY_FILE:-../reed_key.txt}"
if [ -s "$KEY" ]; then
  step "Fetching UK roles from Reed"
  if REED_API_KEY="$(cat "$KEY")" python3 reed.py "$WORK/reed_jobs.json"; then cp "$WORK/reed_jobs.json" data/reed_jobs.json; fi
fi
[ -f data/reed_jobs.json ] && cp data/reed_jobs.json "$RAW/reed_jobs.json"

step "Building the dataset"
rm -f "$WORK/jobs.json"
python3 pipeline/build.py "$RAW" "$WORK/jobs.json" | tail -3
[ -s "$WORK/jobs.json" ] || fail "the build produced no data"
cp "$WORK/elig_crawl.json" data/elig_crawl.json

step "Reading postings for year-of-study wording"
python3 pipeline/targets.py make "$WORK/jobs.json" data "$WORK/targets.json"
python3 check_postings.py "$WORK/targets.json" "$WORK/elig_new.json" && python3 pipeline/targets.py merge "$WORK/elig_new.json" data "$WORK/targets.json"

step "Assembling the site"
python3 pipeline/elig_build.py data/elig_crawl.json data/elig.json site/elig.js || fail "could not write the eligibility scores"
python3 pipeline/assemble.py pipeline/template.html "$WORK/jobs.json" site || fail "the dataset looked too small, so it was not published"

step "Publishing"
git add -A
if git diff --cached --quiet; then echo "Nothing changed since the last refresh."; exit 0; fi
git -c user.name="vpt-dev" -c user.email="vpt-dev@users.noreply.github.com" commit -q -m "Refresh listings $(date +%Y-%m-%d)" || fail "could not save the changes"
git push -q || fail "could not publish to GitHub. If it asked for a password, use a GitHub access token, not your account password."
echo; echo "Published. The live site updates in about a minute."
