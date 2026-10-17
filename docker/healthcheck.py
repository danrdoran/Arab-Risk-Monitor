"""Check the server and bundled data without making an AI provider request."""

import json
from urllib.request import urlopen

with urlopen("http://127.0.0.1:8420/api/health", timeout=4) as response:
    health = json.load(response)
raise SystemExit(0 if health.get("status") == "ok" and all(
    health.get(key) for key in ("data_loaded", "papers_loaded", "graph_loaded", "scores_loaded")
) else 1)
