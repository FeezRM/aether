"""Pin every model file in app/ai/models.py to an exact revision, size and SHA-256.

Run from backend/ on a machine that can reach huggingface.co:

    .venv/bin/python scripts/pin_models.py

It rewrites the ModelFile(...) entries in place, so downloads are checked against
hashes recorded in the source rather than ones reported at download time.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ai.models import TIERS  # noqa: E402

SOURCE = Path(__file__).resolve().parents[1] / "app" / "ai" / "models.py"


def get(url: str):
    with urllib.request.urlopen(url, timeout=30) as res:
        return json.load(res)


def main() -> None:
    text = SOURCE.read_text()
    files = {(f.repo, f.filename) for t in TIERS.values() for f in t.files}
    for repo, filename in sorted(files):
        revision = get(f"https://huggingface.co/api/models/{repo}/revision/main")["sha"]
        tree = get(f"https://huggingface.co/api/models/{repo}/tree/{revision}")
        entry = next((e for e in tree if e["path"] == filename), None)
        if entry is None or "lfs" not in entry:
            sys.exit(f"{filename} not found in {repo}@{revision}")
        sha, size = entry["lfs"]["oid"], entry["lfs"]["size"]
        pattern = re.compile(rf'ModelFile\("{re.escape(repo)}", "{re.escape(filename)}"[^)]*\)')
        replacement = f'ModelFile("{repo}", "{filename}", {size:_}, sha256="{sha}", revision="{revision}")'
        text, n = pattern.subn(replacement, text)
        if not n:
            sys.exit(f"Could not find the ModelFile entry for {filename}")
        print(f"{filename}: {size:,} bytes, sha256 {sha}, revision {revision[:12]}")
    SOURCE.write_text(text)


if __name__ == "__main__":
    main()
