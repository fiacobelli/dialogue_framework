"""LLM provider abstraction layer.

Supports multiple backends (Ollama, Groq) with a common interface.
"""

import requests
from .config import OLLAMA_BASE_URL, GROQ_API_URL, LLM_ERROR_MESSAGE


class OllamaProvider:
    """Local Ollama LLM provider for development."""
    def __init__(self, model: str = "mistral:7b-instruct", base_url: str = None):
        self.model = model
        self.base_url = base_url or OLLAMA_BASE_URL

    def generate(self, messages: list, system_prompt: str = None, json_mode: bool = False) -> str:
        """Generate response from message history."""
        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)

        payload = {"model": self.model, "messages": all_messages, "stream": False}
        if json_mode:
            payload["format"] = "json"
        try:
            resp = requests.post(f"{self.base_url}/api/chat", json=payload)
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        except Exception:
            return LLM_ERROR_MESSAGE


class GroqProvider:
    """Groq cloud LLM provider for production."""

    def __init__(self, model: str = "llama-3.1-8b-instant", api_key: str = None):
        self.model = model
        self.api_key = api_key

    def generate(self, messages: list, system_prompt: str = None, json_mode: bool = False) -> str:
        """Generate response from message history."""
        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)

        payload = {"model": self.model, "messages": all_messages}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            resp = requests.post(
                GROQ_API_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception:
            return LLM_ERROR_MESSAGE


def get_provider(name: str, **kwargs):
    """Factory function to get configured LLM provider."""
    providers = {"ollama": OllamaProvider, "groq": GroqProvider}
    if name not in providers:
        raise ValueError(f"Unknown provider: {name}")
    return providers[name](**kwargs)
