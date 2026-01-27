import requests


class OllamaProvider:
    def __init__(self, model: str = "mistral:7b-instruct", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url

    def generate(self, messages: list, system_prompt: str = None) -> str:
        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)

        try:
            resp = requests.post(f"{self.base_url}/api/chat", json={
                "model": self.model,
                "messages": all_messages,
                "stream": False
            })
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        except Exception:
            return "I'm having trouble responding right now."


class GroqProvider:
    def __init__(self, model: str = "llama-3.1-8b-instant", api_key: str = None):
        self.model = model
        self.api_key = api_key

    def generate(self, messages: list, system_prompt: str = None) -> str:
        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)

        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "messages": all_messages}
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception:
            return "I'm having trouble responding right now."


def get_provider(name: str, **kwargs):
    providers = {"ollama": OllamaProvider, "groq": GroqProvider}
    if name not in providers:
        raise ValueError(f"Unknown provider: {name}")
    return providers[name](**kwargs)
