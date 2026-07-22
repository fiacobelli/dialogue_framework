"""LLM provider abstraction layer.

Supports multiple backends (Ollama, Groq) with a common interface.
"""
import logging
import requests
from .config import OLLAMA_BASE_URL, GROQ_API_URL, LLM_ERROR_MESSAGE

logger = logging.getLogger(__name__)


class OllamaProvider:
    """Local Ollama LLM provider for development."""
    def __init__(self, model: str = "mistral:7b-instruct", base_url: str = None):
        self.model = model
        self.base_url = base_url or OLLAMA_BASE_URL

    def generate(self, messages: list, system_prompt: str = None, json_mode: bool = False, temperature: float = None) -> str:
        """Generate response from message history."""
        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)

        payload = {"model": self.model, "messages": all_messages, "stream": False}
        if json_mode:
            payload["format"] = "json"
        if temperature is not None:
            payload["options"] = {"temperature": temperature}
        try:
            resp = requests.post(f"{self.base_url}/api/chat", json=payload)
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        except Exception:
            return LLM_ERROR_MESSAGE


class GroqProvider:
    """Groq cloud LLM provider for production."""

    def __init__(self, model: str = "openai/gpt-oss-120b", api_key: str = None, fallback_model: str = None):
        self.model = model
        self.api_key = api_key
        self.fallback_model = fallback_model if fallback_model and fallback_model != model else None

    def generate(self, messages: list, system_prompt: str = None, json_mode: bool = False, temperature: float = None) -> str:
        """Generate response from message history."""
        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)

        response = self._generate_with_model(self.model, all_messages, json_mode, temperature)
        if response != LLM_ERROR_MESSAGE:
            return response
        if self.fallback_model:
            logger.warning("Groq primary model %s failed; trying fallback model %s", self.model, self.fallback_model)
            return self._generate_with_model(self.fallback_model, all_messages, json_mode, temperature)
        return LLM_ERROR_MESSAGE

    def _generate_with_model(self, model: str, all_messages: list, json_mode: bool, temperature: float = None) -> str:
        payload = {"model": model, "messages": all_messages}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if temperature is not None:
            payload["temperature"] = temperature
        try:
            resp = requests.post(
                GROQ_API_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            logger.warning("Groq LLM call failed for model %s: %s", model, exc)
            return LLM_ERROR_MESSAGE


def get_provider(name: str, **kwargs):
    """Factory function to get configured LLM provider."""
    providers = {"ollama": OllamaProvider, "groq": GroqProvider}
    if name not in providers:
        raise ValueError(f"Unknown provider: {name}")
    return providers[name](**kwargs)
