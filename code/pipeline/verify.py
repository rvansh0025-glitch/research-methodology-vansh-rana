"""Steps 4 and 5 - Registry check and classification.

`build_snapshot` queries the PyPI JSON API and the npm registry once, at the
start of data collection (T0), and freezes the result to a JSON file. All
later classification reads only that frozen snapshot, so results do not drift
as registries change.

Classes:
  Valid            - existed before T0 with credible history
  Hallucinated     - absent from the registry at T0
  Suspect-squatted - exists, but first published after the model's training
                     cutoff AND has negligible downloads or no source repo
  Ambiguous        - lookup failed; sent to two-annotator manual review
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

USER_AGENT = "phantom-dependencies-research/1.0"
LOW_DOWNLOADS = 100  # downloads in the last month below this count as "negligible"
REPO_HOSTS = ("github.com", "gitlab.com", "bitbucket.org", "codeberg.org", "sr.ht")


def _get_json(url: str, retries: int = 3):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if attempt == retries - 1:
                raise
        except urllib.error.URLError:
            if attempt == retries - 1:
                raise
        time.sleep(2 ** attempt)
    return None


def _has_repo(urls) -> bool:
    text = json.dumps(urls or "").lower()
    return any(h in text for h in REPO_HOSTS)


def lookup_pypi(name: str) -> dict:
    data = _get_json(f"https://pypi.org/pypi/{urllib.parse.quote(name)}/json")
    if data is None:
        return {"exists": False}
    uploads = [f["upload_time_iso_8601"] for files in data.get("releases", {}).values()
               for f in files if f.get("upload_time_iso_8601")]
    info = data.get("info", {})
    downloads = None
    try:
        stats = _get_json(f"https://pypistats.org/api/packages/{urllib.parse.quote(name.lower())}/recent")
        downloads = stats["data"]["last_month"] if stats else None
    except Exception:
        pass
    return {
        "exists": True,
        "first_release": min(uploads) if uploads else None,
        "n_releases": len(data.get("releases", {})),
        "has_repo": _has_repo([info.get("project_urls"), info.get("home_page")]),
        "downloads_last_month": downloads,
    }


def lookup_npm(name: str) -> dict:
    enc = urllib.parse.quote(name, safe="@")  # scoped: @scope%2Fname
    data = _get_json(f"https://registry.npmjs.org/{enc}")
    if data is None or "error" in data:
        return {"exists": False}
    downloads = None
    try:
        stats = _get_json(f"https://api.npmjs.org/downloads/point/last-month/{enc}")
        downloads = stats.get("downloads") if stats else None
    except Exception:
        pass
    return {
        "exists": True,
        "first_release": (data.get("time") or {}).get("created"),
        "n_releases": len(data.get("versions") or {}),
        "has_repo": _has_repo(data.get("repository")),
        "downloads_last_month": downloads,
    }


def build_snapshot(names: set[tuple[str, str]], path: str, pause: float = 0.2) -> dict:
    """Look up every (ecosystem, dist) pair once and freeze the result at T0."""
    snap = {"t0": datetime.now(timezone.utc).isoformat(), "pypi": {}, "npm": {}}
    for eco, dist in sorted(names):
        try:
            snap[eco][dist] = lookup_pypi(dist) if eco == "pypi" else lookup_npm(dist)
        except Exception as e:  # network failure -> Ambiguous later
            snap[eco][dist] = {"error": str(e)}
        time.sleep(pause)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snap, f, indent=2)
    return snap


def _date(s: str | None):
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def classify(ecosystem: str, dist: str, snapshot: dict, model_cutoff: str | None) -> str:
    entry = snapshot.get(ecosystem, {}).get(dist)
    if entry is None or "error" in entry:
        return "Ambiguous"
    if not entry.get("exists"):
        return "Hallucinated"
    first = _date(entry.get("first_release"))
    cutoff = _date(model_cutoff + "T00:00:00+00:00") if model_cutoff else None
    if first and cutoff and first > cutoff:
        dl = entry.get("downloads_last_month")
        low_use = dl is not None and dl < LOW_DOWNLOADS
        if low_use or not entry.get("has_repo"):
            return "Suspect-squatted"
    return "Valid"
