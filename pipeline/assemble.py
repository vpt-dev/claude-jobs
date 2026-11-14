"""Write the site files. Usage: assemble.py template.html jobs.json out_dir [YYYY-MM-DD]

Refuses to publish a dataset that looks broken: far fewer roles than a normal day, or far fewer than
the dataset already on the site.
"""
import datetime
import json
import os
import re
import shutil
import sys

tpl, jobs, out = sys.argv[1:4]
snap = sys.argv[4] if len(sys.argv) > 4 else datetime.date.today().isoformat()
raw = open(jobs, encoding="utf-8").read()
d = json.loads(raw)
assert len(d) > 5000, f"only {len(d)} jobs: refusing to write a thin dataset"
os.makedirs(out, exist_ok=True)
old = os.path.join(out, "data.js")
if os.path.exists(old):
    was = len(re.findall(r'\],"[0-9a-f]{12}"', open(old, encoding="utf-8").read()))  # one job id per role
    assert not was or len(d) > 0.6 * was, f"{len(d)} jobs against {was} on the site: refusing to publish a dataset that shrank this much"
health = "null"
hp = os.path.join(os.path.dirname(jobs) or ".", "health.json")
if os.path.exists(hp):
    health = json.dumps(json.load(open(hp)), separators=(",", ":"))
tmp = old + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    f.write(f"window.SNAP={json.dumps(snap)};window.HEALTH={health};window.JOBS={raw};")
os.replace(tmp, old)
shutil.copyfile(tpl, f"{out}/index.html")
print("jobs", len(d), "snapshot", snap)
