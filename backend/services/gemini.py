"""
Gemini LLM Provider
===================
Singleton wrapper around the Google Gemini API.
Features:
  - Retry logic with exponential backoff
  - Truncation detection
  - Token usage tracking
  - Configurable temperature per call
"""
from __future__ import annotations
import asyncio
import logging
import time
from typing import Optional

import httpx

from backend.config import get_settings

log = logging.getLogger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider:
    _instance: Optional["GeminiProvider"] = None

    def __init__(self):
        cfg = get_settings()
        self._api_key = cfg.gemini_api_key
        self._model = cfg.gemini_model
        self._max_tokens = cfg.gemini_max_tokens
        self._retry_attempts = cfg.gemini_retry_attempts
        self._retry_delay = cfg.gemini_retry_delay
        self._client = httpx.AsyncClient(timeout=60.0)
        self._total_tokens = 0
        self._total_calls = 0

    @classmethod
    def get_instance(cls) -> "GeminiProvider":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: Optional[int] = None,
        temperature: float = 0.1,
    ) -> str:
        """
        Generate a response from Gemini with retry logic.
        Raises RuntimeError if all attempts fail.
        """
        if not self._api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not configured. Set it in your .env file."
            )

        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "maxOutputTokens": max_tokens or self._max_tokens,
                "temperature": temperature,
                "topP": 0.8,
                "topK": 40,
            },
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ],
        }

        url = f"{GEMINI_API_BASE}/models/{self._model}:generateContent?key={self._api_key}"

        last_error: Exception | None = None
        for attempt in range(1, self._retry_attempts + 1):
            try:
                t_start = time.perf_counter()
                resp = await self._client.post(url, json=payload)
                elapsed = round((time.perf_counter() - t_start) * 1000)

                if resp.status_code == 429:
                    wait = self._retry_delay * (2 ** (attempt - 1))
                    log.warning("Gemini rate limited — retrying in %.1fs (attempt %d/%d)", wait, attempt, self._retry_attempts)
                    await asyncio.sleep(wait)
                    continue

                if resp.status_code != 200:
                    raise RuntimeError(f"Gemini API error {resp.status_code}: {resp.text[:200]}")

                data = resp.json()

                # Check for finish reason truncation
                candidates = data.get("candidates", [])
                if not candidates:
                    raise RuntimeError("Gemini returned no candidates")

                candidate = candidates[0]
                finish_reason = candidate.get("finishReason", "STOP")
                if finish_reason == "MAX_TOKENS":
                    log.warning("Gemini response truncated (MAX_TOKENS) — consider increasing max_tokens")

                text = candidate.get("content", {}).get("parts", [{}])[0].get("text", "")
                if not text:
                    raise RuntimeError("Gemini returned empty text")

                # Track usage
                usage = data.get("usageMetadata", {})
                tokens = usage.get("totalTokenCount", 0)
                self._total_tokens += tokens
                self._total_calls += 1

                log.debug(
                    "Gemini: %dms, %d tokens, attempt=%d/%d, finish=%s",
                    elapsed, tokens, attempt, self._retry_attempts, finish_reason,
                )

                return text

            except httpx.TimeoutException as e:
                last_error = e
                log.warning("Gemini timeout on attempt %d/%d", attempt, self._retry_attempts)
                await asyncio.sleep(self._retry_delay * attempt)
            except RuntimeError as e:
                last_error = e
                if "429" in str(e) or "rate" in str(e).lower():
                    await asyncio.sleep(self._retry_delay * attempt)
                else:
                    raise

        raise RuntimeError(f"Gemini failed after {self._retry_attempts} attempts: {last_error}")

    @property
    def stats(self) -> dict:
        return {
            "total_calls": self._total_calls,
            "total_tokens": self._total_tokens,
            "model": self._model,
        }
