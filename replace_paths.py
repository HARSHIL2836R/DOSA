import os
import subprocess
import re

res = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
renames = {}
for line in res.stdout.splitlines():
    if 'R' in line[:2]:
        parts = line.split(' -> ')
        if len(parts) == 2:
            old = parts[0][3:].strip().strip('"')
            new = parts[1].strip().strip('"')
            renames[old] = new

print(f"Found {len(renames)} renames.")

files_to_update = []
for root, dirs, files in os.walk('.'):
    if 'build' in dirs: dirs.remove('build')
    if '.git' in dirs: dirs.remove('.git')
    for f in files:
        if f.endswith('.sh') or f.endswith('.py') or f == 'Makefile' or f.endswith('.json') or f.endswith('.md'):
            files_to_update.append(os.path.join(root, f))

for fpath in files_to_update:
    try:
        with open(fpath, 'r') as f:
            content = f.read()
    except Exception:
        continue
    new_content = content
    for old, new in sorted(renames.items(), key=lambda x: -len(x[0])):
        # Word boundary to avoid partial matches
        # We can just use string replace since paths usually don't overlap partially without boundary
        new_content = new_content.replace(old, new)
    if new_content != content:
        with open(fpath, 'w') as f:
            f.write(new_content)
        print(f"Updated {fpath}")
