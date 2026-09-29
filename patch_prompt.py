import re

with open("ai/ocr/vlm_extractor.py", "r") as f:
    code = f.read()

prompt = """EXTRACTION_PROMPT = \"\"\"
You are extracting a handwritten student answer sheet for automated grading.
Inspect the entire page and return ONLY valid JSON. Do not use markdown fences
or explanatory prose.

Return exactly this shape:
{
  "blocks": [
    {
      "question_number": "1a",
      "bbox": [0, 0, 1000, 1000],
      "content_type": "TEXT",
      "raw_text": "text as visible, including struck text when readable",
      "reconstructed_text": "final answer text, excluding crossed-out text",
      "confidence": 0.0,
      "annotations": [
        {
          "kind": "STRIKE",
          "intent": "CORRECTION",
          "bbox": [100, 100, 200, 200],
          "confidence": 0.0
        }
      ]
    }
  ]
}

Rules:
- Return one block per answer/question region, in reading order.
- Coordinates MUST BE a list of 4 integers `[ymin, xmin, ymax, xmax]` normalized to a 1000x1000 grid (0 to 1000).
- question_number may be null for an unlabeled continuation block.
- content_type must be TEXT, DIAGRAM, TABLE, or EQUATION.
- annotation kind must be STRIKE, UNDERLINE, ARROW, or MARGIN.
- annotation intent must be CORRECTION, EMPHASIS, or INSERTION.
- Use reconstructed_text for what should be graded. Omit text that is clearly
  crossed out. Preserve meaningful margin insertions in the answer.
- If the page is blank or unreadable, return {"blocks": []}.
- Confidence values must be between 0.0 and 1.0.
\"\"\".strip()"""

code = re.sub(r'EXTRACTION_PROMPT = """.*?""".strip\(\)', prompt, code, flags=re.DOTALL)

# Update _bbox function
bbox_fn = """def _bbox(value, *, name: str, width: int, height: int) -> dict[str, float]:
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError(f"VLM {name} must be a list of 4 numbers [ymin, xmin, ymax, xmax]")
    ymin = _number(value[0], name=f"{name}.ymin", minimum=0, maximum=1000)
    xmin = _number(value[1], name=f"{name}.xmin", minimum=0, maximum=1000)
    ymax = _number(value[2], name=f"{name}.ymax", minimum=0, maximum=1000)
    xmax = _number(value[3], name=f"{name}.xmax", minimum=0, maximum=1000)
    
    x = (xmin / 1000.0) * width
    y = (ymin / 1000.0) * height
    w = ((xmax - xmin) / 1000.0) * width
    h = ((ymax - ymin) / 1000.0) * height
    
    if w <= 0 or h <= 0:
        raise ValueError(f"VLM {name} must have positive width and height")
    
    return {"x": x, "y": y, "w": w, "h": h}"""

code = re.sub(r'def _bbox\(.*?return \{"x": x, "y": y, "w": w, "h": h\}', bbox_fn, code, flags=re.DOTALL)

with open("ai/ocr/vlm_extractor.py", "w") as f:
    f.write(code)
