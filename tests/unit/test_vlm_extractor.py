import json

import numpy as np

from ai.ocr.vlm_extractor import extract_page
from ai.providers.mock import MockVLMProvider


def test_vlm_extractor_validates_structured_page_response():
    response = {
        "blocks": [
            {
                "question_number": "1a",
                "bbox": {"x": 100, "y": 50, "w": 300, "h": 200},
                "content_type": "TEXT",
                "raw_text": "old crossed text and final answer",
                "reconstructed_text": "final answer",
                "confidence": 0.84,
                "annotations": [
                    {
                        "kind": "STRIKE",
                        "intent": "CORRECTION",
                        "bbox": {"x": 120, "y": 80, "w": 80, "h": 20},
                        "confidence": 0.91,
                    }
                ],
            }
        ]
    }
    image = np.full((400, 600, 3), 255, dtype=np.uint8)
    provider = MockVLMProvider(response=json.dumps(response))

    result = extract_page(image, provider)

    assert provider.call_count == 1
    assert result.confidence == 0.84
    assert result.blocks[0].question_number == "1a"
    assert result.blocks[0].reconstructed_text == "final answer"
    assert result.blocks[0].annotations[0].kind == "STRIKE"


def test_vlm_extractor_rejects_out_of_bounds_coordinates():
    response = {
        "blocks": [
            {
                "question_number": "1",
                "bbox": {"x": 0, "y": 0, "w": 601, "h": 100},
                "content_type": "TEXT",
                "raw_text": "",
                "reconstructed_text": "",
                "confidence": 0.5,
                "annotations": [],
            }
        ]
    }
    image = np.full((400, 600, 3), 255, dtype=np.uint8)

    try:
        extract_page(image, MockVLMProvider(response=json.dumps(response)))
    except ValueError as error:
        assert "block.bbox.w" in str(error)
    else:
        raise AssertionError("out-of-bounds VLM coordinates were accepted")