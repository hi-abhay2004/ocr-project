"""
Downloads the STS-B dataset (GLUE benchmark) for threshold calibration
(scripts/calibrate_thresholds.py, BACKEND_PLAN.md §B8).

Size-capped on purpose: STS-B's dev split (~1500 sentence pairs with
human-rated 0-5 similarity scores) is enough to sanity-check a similarity
threshold; the ~5.7k-pair train split isn't needed for this and would just
make every calibration run slower for no extra signal.

Usage:
    python scripts/download_datasets.py
"""

import csv
import io
import sys
import zipfile
from pathlib import Path

import httpx

STSB_URL = "https://dl.fbaipublicfiles.com/glue/data/STS-B.zip"
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "stsb"
DEV_TSV_NAME = "STS-B/dev.tsv"


def download_stsb() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / "dev.tsv"
    if out_path.exists():
        print(f"Already downloaded: {out_path}")
        return out_path

    print(f"Downloading {STSB_URL} ...")
    response = httpx.get(STSB_URL, timeout=60, follow_redirects=True)
    response.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        with zf.open(DEV_TSV_NAME) as src, open(out_path, "wb") as dst:
            dst.write(src.read())

    print(f"Saved {out_path}")
    return out_path


def sanity_check(path: Path) -> None:
    with open(path, encoding="utf-8", errors="replace") as f:
        rows = list(csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE))
    print(f"{len(rows) - 1} sentence pairs")
    # Columns per the GLUE STS-B format: sentence1=7, sentence2=8, score=9
    # (0-5, human-rated).
    sample = rows[1]
    print(f"Sample row: score={sample[9]!r} s1={sample[7][:40]!r}")


if __name__ == "__main__":
    try:
        tsv_path = download_stsb()
        sanity_check(tsv_path)
    except httpx.HTTPError as exc:
        print(f"Download failed: {exc}", file=sys.stderr)
        sys.exit(1)
