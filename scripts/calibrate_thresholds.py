"""
Calibrates ai.config's similarity thresholds against STS-B (run
scripts/download_datasets.py first) — measures how well cosine similarity
between the CONFIGURED embedding provider's vectors correlates with
STS-B's human similarity judgements (0-5), and where the current
SIMILARITY_FULL_CREDIT / SIMILARITY_PARTIAL_CREDIT thresholds fall against
that.

IMPORTANT — reads honestly, not automatically: this does NOT write
anything back into ai/config.py. With LLM_PROVIDER=mock (this project's
CI/dev default, since no NIM key is configured), the embedding provider is
ai.providers.mock.MockEmbeddingProvider — a content hash, not a semantic
model. Its cosine similarity has NO reason to correlate with human
judgements of meaning, and running this script against it will show
exactly that (a near-zero Pearson r). That is the correct, expected
result, not a bug — it's what proves this script's own correlation
math works, and it's why ai.config's thresholds were reasoned about
directly rather than fitted to a provider that doesn't understand
language. Re-run this with LLM_PROVIDER=nim (a real NIM key configured)
for a calibration run whose numbers are actually meaningful to act on.

Usage:
    python scripts/download_datasets.py   # once
    python scripts/calibrate_thresholds.py
"""

import csv
import sys
from pathlib import Path

from scipy.stats import pearsonr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.config import SIMILARITY_FULL_CREDIT, SIMILARITY_PARTIAL_CREDIT  # noqa: E402
from ai.providers import get_embedding_provider  # noqa: E402
from ai.providers.factory import _provider_name  # noqa: E402
from ai.rag.store import cosine_similarity  # noqa: E402

DEV_TSV = Path(__file__).resolve().parent.parent / "data" / "stsb" / "dev.tsv"
SAMPLE_SIZE = 300  # capped — see BACKEND_PLAN.md §B8, this only needs to sanity-check a threshold


def load_pairs(path: Path, limit: int = SAMPLE_SIZE) -> list[tuple[str, str, float]]:
    with open(path, encoding="utf-8", errors="replace") as f:
        rows = list(csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE))
    pairs = [(row[7], row[8], float(row[9]) / 5.0) for row in rows[1 : limit + 1]]
    return pairs


def measure(pairs: list[tuple[str, str, float]]) -> tuple[list[float], list[float]]:
    embedder = get_embedding_provider()
    sentences1 = [p[0] for p in pairs]
    sentences2 = [p[1] for p in pairs]
    vectors1 = embedder.embed(sentences1)
    vectors2 = embedder.embed(sentences2)

    predicted = [
        (cosine_similarity(v1, v2) + 1)
        / 2  # [-1,1] -> [0,1], matching ai.pipeline's own convention
        for v1, v2 in zip(vectors1, vectors2, strict=True)
    ]
    human = [p[2] for p in pairs]
    return predicted, human


def report(predicted: list[float], human: list[float]) -> None:
    r, p_value = pearsonr(predicted, human)
    print(f"Provider under test: LLM_PROVIDER={_provider_name()!r}")
    print(f"Pairs evaluated:     {len(predicted)}")
    print(f"Pearson r:           {r:.4f} (p={p_value:.4g})")
    print("Target (§12):        r >= 0.80 (ai.config.TARGET_PEARSON_R)")
    print()

    for label, threshold in [
        ("SIMILARITY_FULL_CREDIT", SIMILARITY_FULL_CREDIT),
        ("SIMILARITY_PARTIAL_CREDIT", SIMILARITY_PARTIAL_CREDIT),
    ]:
        above = [h for pr, h in zip(predicted, human, strict=True) if pr >= threshold]
        below = [h for pr, h in zip(predicted, human, strict=True) if pr < threshold]
        avg_above = sum(above) / len(above) if above else float("nan")
        avg_below = sum(below) / len(below) if below else float("nan")
        print(
            f"{label} = {threshold}: "
            f"{len(above)} pairs scored >= it (avg human label {avg_above:.2f}), "
            f"{len(below)} below (avg human label {avg_below:.2f})"
        )

    print()
    if _provider_name() == "mock":
        print(
            "LLM_PROVIDER=mock: MockEmbeddingProvider is a content hash, not a "
            "semantic model, so a low/near-zero r here is EXPECTED and does not "
            "indicate a problem with ai.config's thresholds — those were reasoned "
            "about directly, not fitted to this provider. This run only proves the "
            "correlation measurement itself works. Re-run with a real NIM key "
            "(LLM_PROVIDER=nim) for a calibration whose numbers should actually "
            "inform ai/config.py — and even then, change the constants by hand "
            "after reviewing the report, not automatically."
        )


if __name__ == "__main__":
    if not DEV_TSV.exists():
        print(f"{DEV_TSV} not found — run scripts/download_datasets.py first.", file=sys.stderr)
        sys.exit(1)

    pairs = load_pairs(DEV_TSV)
    predicted, human = measure(pairs)
    report(predicted, human)
