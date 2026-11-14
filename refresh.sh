#!/bin/bash
# Refresh the job board from this computer and publish it.
#   refresh.sh quick   source lists + Reed + board discovery + posting checks (several minutes)
#   refresh.sh full    the above plus the employer-board crawl (about an hour)
#   refresh.sh auto    full when the last crawl is over six days old or the crawler changed, otherwise quick
# Run from inside a clone of the repository. Scratch files go in ../work.
MODE="${1:-quick}"
cd "$(dirname "$0")" || exit 1
WORK="../work"; RAW="$WORK/raw"; mkdir -p "$RAW"
step() { echo; echo "== $1"; }
fail() { echo; echo "STOPPED: $1"; echo "Nothing was published. The live site is unchanged."; exit 1; }

# Only one refresh at a time on this computer.
LOCK="${TMPDIR:-/tmp}/claude-jobs-refresh.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +360 2>/dev/null)" ]; then rmdir "$LOCK" 2>/dev/null; mkdir "$LOCK" 2>/dev/null || exit 1
  else echo "Another refresh is already running. Try again when it finishes."; exit 0; fi
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

step "Getting the latest code"
git pull --rebase --autostash -q || fail "could not update from GitHub (check your internet connection)"

if [ "$MODE" = "auto" ]; then
  MODE=$(python3 - <<'PY'
import json, datetime
try:
    import re
    d = json.load(open("data/ats_jobs.json"))
    want = int(re.search(r"^CRAWL_VERSION = (\d+)", open("crawl.py").read(), re.M).group(1))
    old = (datetime.date.today() - datetime.date.fromisoformat(d.get("fetched_at", "")[:10])).days > 6 or d.get("version", 1) != want
except Exception:
    old = True
print("full" if old else "quick")
PY
)
  echo "Automatic run: doing a $MODE refresh."
fi

step "Checking the code"
python3 tests/run.py >"$WORK/tests.log" 2>&1 || { tail -5 "$WORK/tests.log"; fail "the built-in checks did not pass"; }

step "Downloading the source lists"
sh pipeline/fetch.sh "$RAW"
cp data/manual.json "$RAW/manual.json"

if [ "$MODE" = "full" ]; then
  step "Crawling employer job boards (about an hour)"
  if python3 crawl.py seeds.json "$WORK/ats_jobs.json" --previous data/ats_jobs.json; then cp "$WORK/ats_jobs.json" data/ats_jobs.json
  else echo "The crawl did not finish cleanly, so the previous crawl results are kept."; fi
fi
cp data/ats_jobs.json "$RAW/ats_jobs.json"

KEY="${REED_KEY_FILE:-../reed_key.txt}"
if [ -s "$KEY" ]; then
  step "Fetching UK roles from Reed"
  if REED_API_KEY="$(cat "$KEY")" python3 reed.py "$WORK/reed_jobs.json"; then cp "$WORK/reed_jobs.json" data/reed_jobs.json; fi
fi
[ -f data/reed_jobs.json ] && cp data/reed_jobs.json "$RAW/reed_jobs.json"

build() { rm -f "$WORK/jobs.json"; python3 pipeline/build.py "$RAW" "$WORK/jobs.json" data | tail -4; [ -s "$WORK/jobs.json" ]; }
step "Building the dataset"
build || fail "the build produced no data"

step "Looking for employers' own job boards"
if python3 probe.py "$WORK/jobs.json" seeds.json data/ats_jobs.json data/probe_tried.json data/probe_report.json; then
  cp data/ats_jobs.json "$RAW/ats_jobs.json"
  build || fail "the build produced no data"
else
  echo "Board discovery did not finish; carrying on without it."; git checkout -q -- seeds.json data/ats_jobs.json 2>/dev/null
fi

step "Reading postings for what they say about who can apply"
python3 pipeline/targets.py make "$WORK/jobs.json" "$WORK" data "$WORK/targets.json"
if python3 check_postings.py "$WORK/targets.json" "$WORK/elig_new.json"; then
  python3 pipeline/targets.py merge "$WORK/elig_new.json" data "$WORK/targets.json"
  build || fail "the build produced no data"   # short links that were traced now point at the employer's posting
fi

step "Assembling the site"
python3 pipeline/elig_build.py "$WORK/jobs.json" "$WORK" data site/elig.js || fail "could not judge the postings"
python3 pipeline/assemble.py pipeline/template.html "$WORK/jobs.json" site || fail "the dataset looked wrong, so it was not published"
if command -v node >/dev/null 2>&1; then node tests/page_check.js site >"$WORK/page.log" 2>&1 || { tail -5 "$WORK/page.log"; git checkout -q -- site 2>/dev/null; fail "the page did not pass its checks"; }; fi

step "Publishing"
git add -A
if git diff --cached --quiet; then echo "Nothing changed since the last refresh."; exit 0; fi
git -c user.name="vpt-dev" -c user.email="vpt-dev@users.noreply.github.com" commit -q -m "Refresh listings $(date +%Y-%m-%d)" || fail "could not save the changes"
git push -q || fail "could not publish to GitHub. If it asked for a password, use a GitHub access token, not your account password."
echo; echo "Published. The live site updates in about a minute."
