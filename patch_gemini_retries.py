import re

with open("ai/providers/gemini.py", "r") as f:
    code = f.read()

# Add tenacity import at the top
if "from tenacity" not in code:
    code = code.replace("from typing import Any", "from typing import Any\nfrom tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type\nimport google.genai.errors")

# We want to retry on google.genai.errors.APIError (which covers ServerError and ClientError)
retry_decorator = "@retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=1, min=2, max=60), retry=retry_if_exception_type(google.genai.errors.APIError))\n    def chat"
code = re.sub(r'    def chat', retry_decorator, code, count=1)

retry_decorator_vlm = "@retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=1, min=2, max=60), retry=retry_if_exception_type(google.genai.errors.APIError))\n    def describe_image"
code = re.sub(r'    def describe_image', retry_decorator_vlm, code, count=1)

retry_decorator_embed = "@retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=1, min=2, max=60), retry=retry_if_exception_type(google.genai.errors.APIError))\n    def embed"
code = re.sub(r'    def embed', retry_decorator_embed, code, count=1)

with open("ai/providers/gemini.py", "w") as f:
    f.write(code)
