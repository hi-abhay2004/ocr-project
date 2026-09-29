"""
Every threshold the pipeline uses, in one place.

PLAN_OF_ACTION_V2.md §5/§8/§12 and scripts/calibrate_thresholds.py (Phase B8)
both point here. Two consequences of that:

  1. If a value changes, it changes HERE — never as a magic number inline in a
     layer module. That is what makes calibration ("0.72 is empirically
     justified" instead of "we chose 0.72") a one-file diff.
  2. EMBEDDING_DIM drives every VectorField in the schema (apps/exams/models.py
     Concept.embedding). Changing providers later is one constant + one
     migration, not a rewrite — this is the reason it is centralised rather
     than read off whatever the first provider happens to return.
"""

# ── Embeddings ───────────────────────────────────────────────────────────
# nv-embedqa-e5-v5 (NIM) was 1024-dim but NVIDIA retired it (confirmed
# 2026-08-26: every real call started returning HTTP 410 Gone, "reached its
# end of life on 2026-08-25T09:00:00Z"). Its replacement on this account's
# actual entitlements — several catalogue-listed embedding models 404 on a
# free-tier key; nemotron-3-embed-1b is the one verified to actually work —
# is 2048-dim, not 1024. This is exactly the "one constant + one migration"
# change this file's docstring describes: EMBEDDING_DIM changed here, plus
# apps/exams/migrations/0002_concept_embedding_dim_2048.py which drops and
# regenerates every existing Concept (their old 1024-dim vectors are from a
# now-dead model regardless of dimension, so they were already stale).
# mock.py returns vectors of exactly this length so pgvector's fixed-width
# VectorField never has to change shape between mock and real runs.
EMBEDDING_DIM = 2048

# ── L3.5 — annotation adjudication trigger ──────────────────────────────
# Below this, OpenCV's own confidence in strike-vs-underline-vs-ruled-line is
# too low to trust; the VLM is asked instead. See ai/annotations/adjudicator.py.
ANNOTATION_AMBIGUITY_THRESHOLD = 0.70

# ── L4 — adaptive OCR routing ────────────────────────────────────────────
# quality_score() ranges 0-1 (ai/preprocessing.py). At or above this, plain
# Tesseract PSM 6 is trusted. Below it, morphology + PSM 11 runs first, and
# if THAT still reports confidence under OCR_CONFIDENCE_ESCALATION, the VLM
# transcribes the block directly.
OCR_QUALITY_ROUTING_THRESHOLD = 0.60
# 0.40 was verified (2026-08-27) to badly under-escalate on real cursive
# handwriting: two independent real photographed blocks that both came
# back as complete garbled nonsense ("EE LLllls—...", "set eM gate WEE
# eO)...") each scored ~0.50 Tesseract confidence — comfortably above the
# old threshold, so neither ever reached the VLM. A clean, correctly-read
# SYNTHETIC printed fixture measured 0.9467 in the same test, so 0.65
# still leaves a wide, safe margin below genuine high-confidence reads
# while actually catching the ~0.50 garbage this project's real answer
# sheets produce. Tesseract's own confidence metric doesn't reliably
# separate "read it right" from "confidently wrong" on real handwriting —
# this threshold is deliberately conservative (escalate more, not less)
# given that gap.
OCR_CONFIDENCE_ESCALATION_THRESHOLD = 0.65  # Tesseract's own 0-100 conf, read as 0-1

# ── L4.5 — specialized (non-text) content ────────────────────────────────
# Below this stroke/text-density ratio, a block is treated as a diagram/table/
# equation rather than prose and routed to ai/ocr/specialized.py instead of
# any OCR engine at all.
TEXT_DENSITY_CUTOFF = 0.15

# ── L7/L8 — coverage & scoring bands ─────────────────────────────────────
# similarity is cosine, 0-1, from the top retrieved chunk for a concept.
SIMILARITY_FULL_CREDIT = 0.72  # similarity >= this AND llm=covered  -> full weight
SIMILARITY_PARTIAL_CREDIT = 0.50  # similarity >= this (or llm=partial) -> half weight
SIMILARITY_DOWNGRADE = 0.45  # llm says "covered" but similarity < this -> downgrade to partial

# Underlined chunks get their similarity boosted before banding (capped at 1.0).
UNDERLINE_SIMILARITY_BOOST = 1.10

# RAG retrieval depth — top-k chunks retrieved per concept.
RETRIEVAL_TOP_K = 3

# Concept weights must sum to 1.0 within this tolerance after LLM extraction.
CONCEPT_WEIGHT_TOLERANCE = 0.01
CONCEPT_COUNT_MIN = 5
CONCEPT_COUNT_MAX = 8

# ── Coverage check ────────────────────────────────────────────────────────
# Reduced from 3 to 1 to cut latency: 3 passes per concept means 15+ LLM
# round-trips for a 5-concept question — the single largest latency driver.
# Single-pass is still accurate; agreement defaults to 1.0 (unanimous with
# one vote). Restore to 3 for extra confidence once speed is acceptable.
COVERAGE_PASS_COUNT = 1

# ── Composite confidence (drives the 🟢/🟠/🔴 band) ──────────────────────
CONFIDENCE_WEIGHT_OCR_QUALITY = 0.35
CONFIDENCE_WEIGHT_PASS_AGREEMENT = 0.40
CONFIDENCE_WEIGHT_RETRIEVAL_VERIFY = 0.25

CONFIDENCE_BAND_GREEN = 0.80  # >= -> auto-publishable
CONFIDENCE_BAND_ORANGE = 0.65  # >= -> publish with note; below -> force review

# ── Success targets (PLAN_OF_ACTION_V2.md §12) — read by scripts/benchmark.py
# to annotate the report with target-vs-measured, not enforced at runtime.
TARGET_PEARSON_R = 0.80
TARGET_OVERALL_ACCURACY = 0.85
TARGET_STRIKETHROUGH_ACCURACY = 0.90
TARGET_MARGIN_ARROW_PRECISION = 0.85
TARGET_TRIPLE_PASS_STD_DEV = 0.5
TARGET_LATENCY_SECONDS = 30
