import re

with open("ai/providers/gemini.py", "r") as f:
    code = f.read()

# Remove the acquire outside the loop
code = code.replace("GEMINI_RATE_LIMITER.acquire()\n        client = _client()", "client = _client()")

# Now, we manually re-insert it in all three methods:
# chat
code = code.replace("client = _client()", "GEMINI_RATE_LIMITER.acquire()\n        client = _client()", 1)
# describe_image
code = code.replace("client = _client()", "GEMINI_RATE_LIMITER.acquire()\n        client = _client()", 1)

# embed
new_embed_loop = """        for text in texts:
            GEMINI_RATE_LIMITER.acquire()
            result = client.models.embed_content("""
code = re.sub(r'        for text in texts:\n            result = client\.models\.embed_content\(', new_embed_loop, code)

with open("ai/providers/gemini.py", "w") as f:
    f.write(code)
