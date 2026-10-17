"""Two modes for the same image: serve the app or refresh its numeric data."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def refresh() -> None:
    sys.path.insert(0, str(ROOT))
    from etl.build_dataset import FETCHERS

    # Run fetchers directly so a failed subprocess stops the job, rather than
    # being ignored by build_dataset.py's existing --refresh orchestration.
    for name in (*FETCHERS, "build_dataset.py", "build_scores.py"):
        print(f"Running {name}", flush=True)
        subprocess.run([sys.executable, str(ROOT / "etl" / name)], cwd=ROOT, check=True)
    print("Refresh complete. Start or restart the app to load the updated data.", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", choices=("app", "refresh"), default="app")
    args = parser.parse_args()
    if args.mode == "refresh":
        try:
            refresh()
        except subprocess.CalledProcessError as exc:
            print("Refresh failed; inspect the fetcher output before starting the app.", file=sys.stderr)
            return exc.returncode or 1
        return 0

    os.chdir(ROOT)
    os.execv(sys.executable, [
        sys.executable, "-m", "uvicorn", "backend.app:app",
        "--host", "0.0.0.0", "--port", "8420", "--workers", "1", "--no-proxy-headers",
    ])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
