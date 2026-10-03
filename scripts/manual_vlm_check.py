"""
Manual, ad-hoc check: sends the most recently uploaded sheet page to the
configured VLM provider and prints the raw extraction response.

Not a pytest test (despite living next to scripts that are) — it does real
Django ORM access and a real network call. Renamed from `test_vlm.py`
because that name matched pytest's `test_*.py` collection pattern and its
module-level `SheetPage.objects.last()` call broke `pytest` collection for
the whole repo before any real test could run.

Usage:
    python scripts/manual_vlm_check.py
"""

import os

import cv2
import django
import numpy as np

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from ai.ocr.vlm_extractor import EXTRACTION_PROMPT  # noqa: E402
from ai.providers.factory import get_vlm_provider  # noqa: E402
from apps.evaluation.models import SheetPage  # noqa: E402


def main() -> None:
    page = SheetPage.objects.last()
    if page is None:
        print("No SheetPage rows exist yet — upload a sheet first.")
        return

    img = cv2.imdecode(np.frombuffer(page.image.read(), np.uint8), cv2.IMREAD_COLOR)
    ok, buffer = cv2.imencode(".png", img)
    if not ok:
        print("Could not encode")
        return

    vlm = get_vlm_provider()
    print(f"Sending to VLM ({vlm.__class__.__name__})...")
    raw = vlm.describe_image(buffer.tobytes(), EXTRACTION_PROMPT)
    print("--- VLM OUTPUT ---")
    print(raw)


if __name__ == "__main__":
    main()
