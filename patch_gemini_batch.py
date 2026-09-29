import re

with open("ai/providers/gemini.py", "r") as f:
    code = f.read()

new_embed = """    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=1, min=2, max=60), retry=retry_if_exception_type(Exception))
    def embed(self, texts: list[str]) -> list[list[float]]:
        self.call_count += 1
        
        # We use raw requests to access batchEmbedContents which is missing in the SDK
        import requests
        import os
        api_key = os.environ.get("GEMINI_API_KEY", "")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:batchEmbedContents?key={api_key}"
        
        # Batch in chunks of 100 to be safe
        embeddings = []
        for i in range(0, len(texts), 100):
            batch_texts = texts[i:i+100]
            GEMINI_RATE_LIMITER.acquire()
            payload = {
                "requests": [
                    {"model": f"models/{self.model}", "content": {"parts": [{"text": text}]}}
                    for text in batch_texts
                ]
            }
            res = requests.post(url, json=payload)
            if res.status_code != 200:
                raise RuntimeError(f"Batch embed failed: {res.text}")
            
            data = res.json()
            for item in data.get("embeddings", []):
                emb = item["values"]
                if len(emb) > 2048:
                    emb = emb[:2048]
                elif len(emb) < 2048:
                    emb = emb + [0.0] * (2048 - len(emb))
                embeddings.append(emb)
        return embeddings"""

code = re.sub(r'    @retry.*?def embed\(.*?return embeddings', new_embed, code, flags=re.DOTALL)

with open("ai/providers/gemini.py", "w") as f:
    f.write(code)
