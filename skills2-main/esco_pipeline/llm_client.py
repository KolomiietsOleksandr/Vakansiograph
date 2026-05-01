"""Unified LLM client abstraction for Gemini and vLLM (OpenAI-compatible) backends."""

import asyncio
import json
import logging

from esco_pipeline.config import Settings
from esco_pipeline.utils import retry_with_backoff

logger = logging.getLogger(__name__)

# Default max output tokens for vLLM (used by llm_two_stage mapper)
_DEFAULT_MAX_TOKENS_VLLM = 2048


def _is_retryable(exc: BaseException) -> bool:
    """Return True only for errors worth retrying (server errors, timeouts, rate limits).
    4xx client errors (especially 400 Bad Request) are deterministic — don't waste time retrying."""
    exc_str = str(exc)
    # OpenAI-style error codes
    if "Error code: 4" in exc_str and "429" not in exc_str:
        # 400, 401, 403, 404 etc — not retryable (except 429 rate-limit)
        return False
    return True


class LLMClient:
    """Wraps either Gemini or an OpenAI-compatible server (vLLM) behind a
    single ``generate_json`` method that returns parsed JSON and token usage."""

    def __init__(self, config: Settings):
        self._provider = config.llm_provider
        self._config = config
        self._async_openai_client = None

        if self._provider == "gemini":
            from google import genai

            self._gemini_client = genai.Client(api_key=config.gemini_api_key)
        elif self._provider == "vllm":
            from openai import AsyncOpenAI, OpenAI

            import httpx

            # Sync client for single calls
            self._openai_client = OpenAI(
                base_url=config.vllm_base_url,
                api_key=config.vllm_api_key,
                timeout=600.0,
                max_retries=0,  # we handle retries ourselves
            )
            # Async client for batch calls — longer timeout for vLLM queue
            self._async_openai_client = AsyncOpenAI(
                base_url=config.vllm_base_url,
                api_key=config.vllm_api_key,
                timeout=600.0,
                max_retries=0,  # we handle retries ourselves
                http_client=httpx.AsyncClient(
                    limits=httpx.Limits(
                        max_connections=config.llm_max_concurrent + 10,
                        max_keepalive_connections=config.llm_max_concurrent,
                    ),
                    timeout=httpx.Timeout(600.0, connect=30.0),
                ),
            )
        else:
            raise ValueError(f"Unknown llm_provider: {self._provider!r}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @retry_with_backoff(max_attempts=3)
    def generate_json(
        self,
        prompt: str,
        *,
        max_tokens: int | None = None,
        system_message: str | None = None,
    ) -> tuple[dict | list, dict]:
        """Send *prompt* to the configured LLM and return ``(parsed_json, token_usage)``."""
        if self._provider == "gemini":
            return self._call_gemini(prompt)
        else:
            return self._call_vllm(prompt, max_tokens=max_tokens, system_message=system_message)

    def generate_json_batch(
        self,
        prompts: list[str],
        max_concurrent: int = 16,
        *,
        max_tokens: int | None = None,
        system_message: str | None = None,
    ) -> list[tuple[dict | list, dict]]:
        """Send multiple prompts concurrently and return results in input order.

        Uses asyncio for vLLM backend to avoid GIL/thread-lock contention.
        Falls back to ThreadPoolExecutor for Gemini.
        """
        if not prompts:
            return []

        if self._provider == "vllm" and self._async_openai_client is not None:
            return self._batch_async_vllm(prompts, max_concurrent, max_tokens=max_tokens, system_message=system_message)

        # Gemini fallback: use threads (Gemini SDK is sync-only)
        return self._batch_threaded(prompts, max_concurrent, max_tokens=max_tokens, system_message=system_message)

    # ------------------------------------------------------------------
    # Async vLLM batch
    # ------------------------------------------------------------------

    def _batch_async_vllm(
        self,
        prompts: list[str],
        max_concurrent: int,
        *,
        max_tokens: int | None = None,
        system_message: str | None = None,
    ) -> list[tuple[dict | list, dict]]:
        """Run all prompts concurrently via AsyncOpenAI + asyncio."""

        async def _run():
            sem = asyncio.Semaphore(max_concurrent)
            tasks = [
                self._async_call_vllm(sem, prompt, max_tokens=max_tokens, system_message=system_message)
                for prompt in prompts
            ]
            return await asyncio.gather(*tasks)

        # Use existing event loop if available, otherwise create one
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            # Already in an async context — run in a new thread to avoid nesting
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                results = pool.submit(lambda: asyncio.run(_run())).result()
        else:
            results = asyncio.run(_run())

        return list(results)

    async def _async_call_vllm(
        self,
        sem: asyncio.Semaphore,
        prompt: str,
        *,
        max_tokens: int | None = None,
        system_message: str | None = None,
        _retries: int = 3,
    ) -> tuple[dict | list, dict]:
        """Single async vLLM call with semaphore and retry."""
        sys_msg = system_message or (
            "You are an expert skill-to-ESCO taxonomy mapper. "
            "Always respond with valid JSON only, no markdown fences."
        )
        effective_max_tokens = max_tokens or _DEFAULT_MAX_TOKENS_VLLM

        async with sem:
            for attempt in range(1, _retries + 1):
                try:
                    response = await self._async_openai_client.chat.completions.create(
                        model=self._config.vllm_model,
                        messages=[
                            {"role": "system", "content": sys_msg},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.0,
                        max_tokens=effective_max_tokens,
                        response_format={"type": "json_object"},
                    )
                    choice = response.choices[0]
                    text = (choice.message.content or "").strip()
                    token_usage: dict = {}
                    if response.usage:
                        token_usage = {
                            "input": response.usage.prompt_tokens or 0,
                            "output": response.usage.completion_tokens or 0,
                            "total": response.usage.total_tokens or 0,
                        }
                    logger.debug("vLLM response (%d chars): %s", len(text), text[:300])
                    return self._safe_parse_json(text), token_usage
                except Exception as e:
                    if not _is_retryable(e) or attempt == _retries:
                        logger.error("Async vLLM call failed (attempt %d/%d): %s", attempt, _retries, e)
                        return {}, {}
                    logger.warning("Async vLLM call retry %d/%d: %s", attempt, _retries, e)
                    await asyncio.sleep(min(2 ** attempt, 10))

        return {}, {}

    # ------------------------------------------------------------------
    # Threaded fallback (Gemini)
    # ------------------------------------------------------------------

    def _batch_threaded(
        self,
        prompts: list[str],
        max_concurrent: int,
        *,
        max_tokens: int | None = None,
        system_message: str | None = None,
    ) -> list[tuple[dict | list, dict]]:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results: list[tuple[dict | list, dict] | None] = [None] * len(prompts)

        with ThreadPoolExecutor(max_workers=min(max_concurrent, len(prompts))) as pool:
            future_to_idx = {
                pool.submit(
                    self.generate_json,
                    prompt,
                    max_tokens=max_tokens,
                    system_message=system_message,
                ): idx
                for idx, prompt in enumerate(prompts)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    if not _is_retryable(e):
                        logger.error("Batch LLM request %d non-retryable: %s", idx, e)
                    else:
                        logger.warning("Batch LLM request %d failed: %s", idx, e)
                    results[idx] = ({}, {})

        return [(r if r is not None else ({}, {})) for r in results]

    # ------------------------------------------------------------------
    # Gemini backend
    # ------------------------------------------------------------------

    def _call_gemini(self, prompt: str) -> tuple[dict | list, dict]:
        from google.genai import types

        response = self._gemini_client.models.generate_content(
            model=self._config.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
        token_usage: dict = {}
        meta = response.usage_metadata
        if meta:
            token_usage = {
                "input": meta.prompt_token_count or 0,
                "output": meta.candidates_token_count or 0,
                "total": meta.total_token_count or 0,
            }
        text = response.text.strip()
        return self._safe_parse_json(text), token_usage

    # ------------------------------------------------------------------
    # vLLM / OpenAI-compatible backend (sync, for single calls)
    # ------------------------------------------------------------------

    def _call_vllm(
        self,
        prompt: str,
        *,
        max_tokens: int | None = None,
        system_message: str | None = None,
    ) -> tuple[dict | list, dict]:
        sys_msg = system_message or (
            "You are an expert skill-to-ESCO taxonomy mapper. "
            "Always respond with valid JSON only, no markdown fences."
        )
        effective_max_tokens = max_tokens or _DEFAULT_MAX_TOKENS_VLLM

        response = self._openai_client.chat.completions.create(
            model=self._config.vllm_model,
            messages=[
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=effective_max_tokens,
            response_format={"type": "json_object"},
        )
        choice = response.choices[0]
        text = (choice.message.content or "").strip()
        token_usage: dict = {}
        if response.usage:
            token_usage = {
                "input": response.usage.prompt_tokens or 0,
                "output": response.usage.completion_tokens or 0,
                "total": response.usage.total_tokens or 0,
            }
        logger.debug("vLLM response (%d chars): %s", len(text), text[:300])
        return self._safe_parse_json(text), token_usage

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_parse_json(text: str) -> dict | list:
        # Strip markdown code fences if present
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("LLMClient: failed to parse JSON: %s", cleaned[:200])
            return {}
