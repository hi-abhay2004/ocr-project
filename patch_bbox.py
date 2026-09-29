import re

with open("ai/ocr/vlm_extractor.py", "r") as f:
    code = f.read()

new_bbox = """def _bbox(value, *, name: str, width: int, height: int) -> dict[str, float]:
    if not isinstance(value, dict):
        raise ValueError(f"VLM {name} must be an object")
    x_norm = _number(value.get("x"), name=f"{name}.x", minimum=0, maximum=1000)
    y_norm = _number(value.get("y"), name=f"{name}.y", minimum=0, maximum=1000)
    w_norm = _number(value.get("w"), name=f"{name}.w", minimum=0, maximum=1000)
    h_norm = _number(value.get("h"), name=f"{name}.h", minimum=0, maximum=1000)
    if w_norm <= 0 or h_norm <= 0:
        raise ValueError(f"VLM {name} must have positive width and height")
    
    x = (x_norm / 1000.0) * width
    y = (y_norm / 1000.0) * height
    w = (w_norm / 1000.0) * width
    h = (h_norm / 1000.0) * height
    
    if x + w > width + 10 or y + h > height + 10:  # add slight tolerance
        raise ValueError(f"VLM {name} extends outside the page")
        
    return {"x": x, "y": y, "w": w, "h": h}"""

code = re.sub(r'def _bbox\(.*?return \{"x": x, "y": y, "w": w, "h": h\}', new_bbox, code, flags=re.DOTALL)

with open("ai/ocr/vlm_extractor.py", "w") as f:
    f.write(code)
