import os
import logging
import requests

logger = logging.getLogger(__name__)


class ModelBullshit:
    def __init__(self):
        self.url = "https://openrouter.ai/api/v1/chat/completions"
        self.api_key = os.environ["OPENROUTER_API_KE"]
        self.model = "z-ai/glm-5.2"

    def ask(self, prompt: str) -> str:
        logger.info("Sending prompt to %s: %s", self.model, prompt)

        response = requests.post(
            self.url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            },
        )

        logger.info(
            "OpenRouter response status: %s",
            response.status_code,
        )

        response.raise_for_status()

        response_text = response.json()["choices"][0]["message"]["content"]

        logger.info("Model response: %s", response_text)

        return response_text
