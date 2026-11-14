"""Write the site files. Usage: assemble.py template.html jobs.json out_dir [YYYY-MM-DD]"""
import json, sys, shutil, datetime, os
tpl, jobs, out = sys.argv[1:4]
snap = sys.argv[4] if len(sys.argv) > 4 else datetime.date.today().isoformat()
raw = open(jobs, encoding="utf-8").read()
d = json.loads(raw)
assert len(d) > 5000, f"only {len(d)} jobs: refusing to write a thin dataset"
os.makedirs(out, exist_ok=True)
open(f"{out}/data.js", "w", encoding="utf-8").write(f"window.SNAP={json.dumps(snap)};window.JOBS={raw};")
shutil.copyfile(tpl, f"{out}/index.html")
print("jobs", len(d), "snapshot", snap)
