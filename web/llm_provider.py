"""LLM provider abstraction layer.

Supports multiple backends (Ollama, Groq) with a common interface.
"""

import json as _json
import logging
import time
import requests
from .config import OLLAMA_BASE_URL, GROQ_API_URL, LLM_ERROR_MESSAGE

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BACKOFF_SECONDS = [0, 2, 5]   # longer waits help with 429 rate limits
RATE_LIMIT_BACKOFF = 15        # extra wait when Groq returns 429


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
            payload["temperature"] = temperature

        for attempt in range(MAX_RETRIES):
            try:
                if BACKOFF_SECONDS[attempt]:
                    time.sleep(BACKOFF_SECONDS[attempt])
                resp = requests.post(f"{self.base_url}/api/chat", json=payload, timeout=30)
                resp.raise_for_status()
                return resp.json()["message"]["content"]
            except Exception as e:
                logger.warning("Ollama LLM attempt %d/%d failed: %s", attempt + 1, MAX_RETRIES, e)
        logger.error("Ollama LLM call failed after %d attempts", MAX_RETRIES)
        return LLM_ERROR_MESSAGE

    def generate_stream(self, messages: list, system_prompt: str = None, temperature: float = None):
        """Stream tokens from Ollama. Yields delta content strings."""
        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)
        payload = {"model": self.model, "messages": all_messages, "stream": True}
        if temperature is not None:
            payload["temperature"] = temperature
        resp = requests.post(f"{self.base_url}/api/chat", json=payload, stream=True, timeout=60)
        try:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                chunk = _json.loads(line)
                delta = chunk.get("message", {}).get("content", "")
                if delta:
                    yield delta
                if chunk.get("done"):
                    break
        finally:
            resp.close()


class GroqProvider:
    """Groq cloud LLM provider for production."""

    def __init__(self, model: str = "llama-3.1-8b-instant", api_key: str = None):
        self.model = model
        self.api_key = api_key

    def generate(self, messages: list, system_prompt: str = None, json_mode: bool = False, temperature: float = None) -> str:
        """Generate response from message history."""
        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)

        payload = {"model": self.model, "messages": all_messages}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if temperature is not None:
            payload["temperature"] = temperature

        for attempt in range(MAX_RETRIES):
            try:
                if BACKOFF_SECONDS[attempt]:
                    time.sleep(BACKOFF_SECONDS[attempt])
                resp = requests.post(
                    GROQ_API_URL,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                    timeout=30,
                )
                if resp.status_code == 429:
                    logger.warning(
                        "Groq rate limit (429) on attempt %d/%d — waiting %ds. Response: %s",
                        attempt + 1, MAX_RETRIES, RATE_LIMIT_BACKOFF, resp.text[:200]
                    )
                    time.sleep(RATE_LIMIT_BACKOFF)
                    continue
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
            except requests.exceptions.Timeout:
                logger.warning("Groq timeout on attempt %d/%d", attempt + 1, MAX_RETRIES)
            except requests.exceptions.ConnectionError as e:
                logger.warning("Groq connection error on attempt %d/%d: %s", attempt + 1, MAX_RETRIES, e)
            except requests.exceptions.HTTPError as e:
                logger.warning("Groq HTTP %s on attempt %d/%d: %s", resp.status_code, attempt + 1, MAX_RETRIES, e)
            except Exception as e:
                logger.warning("Groq unexpected error on attempt %d/%d: %s", attempt + 1, MAX_RETRIES, e)
        logger.error("Groq LLM call failed after %d attempts for model %s", MAX_RETRIES, self.model)
        return LLM_ERROR_MESSAGE


    def generate_stream(self, messages: list, system_prompt: str = None, temperature: float = None):
        """Stream tokens from Groq. Yields delta.content strings. No retry — fail fast."""
        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)
        payload = {"model": self.model, "messages": all_messages, "stream": True}
        if temperature is not None:
            payload["temperature"] = temperature
        resp = requests.post(
            GROQ_API_URL,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=payload,
            stream=True,
            timeout=30,
        )
        try:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                if line.startswith(b'data: '):
                    data = line[6:]
                    if data == b'[DONE]':
                        break
                    chunk = _json.loads(data)
                    delta = chunk['choices'][0]['delta'].get('content', '')
                    if delta:
                        yield delta
        finally:
            resp.close()


def get_provider(name: str, **kwargs):
    """Factory function to get configured LLM provider."""
    providers = {"ollama": OllamaProvider, "groq": GroqProvider}
    if name not in providers:
        raise ValueError(f"Unknown provider: {name}")
    return providers[name](**kwargs)
