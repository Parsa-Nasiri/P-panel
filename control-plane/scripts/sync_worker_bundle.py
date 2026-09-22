"""Sync the built Node bundle into the control plane for API-based upload.

Run after every node-worker build (and before committing):

    cd node-worker && npm run build
    cd ../control-plane && python scripts/sync_worker_bundle.py
"""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "node-worker" / "dist" / "worker.js"
DST_DIR = ROOT / "control-plane" / "assets"
DST = DST_DIR / "worker_bundle.js"


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"source bundle missing: {SRC} — run `npm run build` in node-worker first")

    DST_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SRC, DST)
    print(f"synced {SRC} -> {DST} ({DST.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
