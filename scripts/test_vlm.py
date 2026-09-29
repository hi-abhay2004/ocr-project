import os
import django
import cv2
import numpy as np

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from apps.evaluation.models import SheetPage
from ai.providers.nim import NIMVLMProvider
from ai.ocr.vlm_extractor import EXTRACTION_PROMPT

p = SheetPage.objects.last()
img = cv2.imdecode(np.frombuffer(p.image.read(), np.uint8), cv2.IMREAD_COLOR)

ok, buffer = cv2.imencode(".png", img)
if not ok:
    print("Could not encode")
    exit(1)

vlm = NIMVLMProvider()
print("Sending to VLM...")
raw = vlm.describe_image(buffer.tobytes(), EXTRACTION_PROMPT)
print("--- VLM OUTPUT ---")
print(raw)
