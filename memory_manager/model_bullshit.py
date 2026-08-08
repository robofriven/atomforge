import requests


class ModelBullshit:
    def __init__(self):
        self.base_url = "http://127.0.0.1:5001/v1"

    def ask(self, prompt: str) -> str:
        response = requests.post(
            f"{self.base_url}/chat/completions",
            json={
                "model": "koboldcpp/Qwen3-VL-8B-Instruct-abliterated.Q4_K_M",
                "messages": [{"role": "user", "content": prompt}],
            },
        )

        response.raise_for_status()

        return response.json()["choices"][0]["message"]["content"]
