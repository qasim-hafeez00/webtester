"""Provider-agnostic LLM client over the OpenAI-compatible chat API.

Every condition in an experiment goes through this one client, so token
accounting and retry behaviour are identical across conditions.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
from dataclasses import dataclass
from typing import Any

from .config import LLMConfig


class LLMError(RuntimeError):
    pass


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0
    retries: int = 0
    latency_s: float = 0.0

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def add(self, other: "Usage") -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.calls += other.calls
        self.retries += other.retries
        self.latency_s += other.latency_s


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
_QUOTA_ERROR = re.compile(r"\b(quota|rate.?limit|resource.?exhausted|too many requests)\b", re.IGNORECASE)


def api_key_env_names(base_name: str | None) -> tuple[str, ...]:
    """Return the configured base key followed by numbered fallback keys."""
    if not base_name:
        return ()
    names = [base_name] if os.environ.get(base_name) else []
    index = 1
    while os.environ.get(f"{base_name}_{index}"):
        names.append(f"{base_name}_{index}")
        index += 1
    return tuple(names)


def is_quota_error(error: Exception) -> bool:
    """Whether an API error indicates this key cannot currently make requests."""
    status = getattr(error, "status_code", None)
    if status == 429:
        return True
    return status in (400, 403) and bool(_QUOTA_ERROR.search(str(error)))


def parse_json_object(text: str) -> dict:
    """Parse the first JSON object in a model reply (tolerates code fences and prose)."""
    cleaned = _FENCE.sub("", text.strip())
    try:
        value = json.loads(cleaned)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(cleaned)):
            ch = cleaned[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        value = json.loads(cleaned[start : i + 1])
                        if isinstance(value, dict):
                            return value
                    except json.JSONDecodeError:
                        break
        start = cleaned.find("{", start + 1)
    raise LLMError(f"no JSON object in reply: {text[:200]!r}")


class LLMClient:
    def __init__(self, cfg: LLMConfig):
        from openai import AsyncOpenAI

        self.cfg = cfg
        key_env = cfg.resolved_key_env()
        self._key_envs = api_key_env_names(key_env)
        if not cfg.key_fallback:
            self._key_envs = self._key_envs[:1]
        if not self._key_envs and key_env:
            raise LLMError(
                f"{key_env} is not set. Put it in the environment or in .env at the repo root "
                f"(provider={cfg.provider})."
            )
        if self._key_envs:
            self._clients = [
                AsyncOpenAI(
                    api_key=os.environ[env_name],
                    base_url=cfg.resolved_base_url(),
                    max_retries=0,  # we retry ourselves so retries are counted
                    timeout=cfg.timeout_s,
                )
                for env_name in self._key_envs
            ]
        else:
            self._clients = [
                AsyncOpenAI(
                    api_key="not-needed",
                    base_url=cfg.resolved_base_url(),
                    max_retries=0,
                    timeout=cfg.timeout_s,
                )
            ]
        self._key_index = 0
        self._key_lock = asyncio.Lock()
        self._lock = asyncio.Lock()
        self._last_call = 0.0
        self.usage = Usage()

    async def _pace(self) -> None:
        if self.cfg.min_interval_s <= 0:
            return
        async with self._lock:
            wait = self._last_call + self.cfg.min_interval_s - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = time.monotonic()

    async def complete_json(self, system: str, user: str) -> tuple[dict, Usage]:
        """One chat completion that must return a JSON object."""
        from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

        usage = Usage(calls=1)
        kwargs = dict(
            model=self.cfg.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=self.cfg.temperature,
            max_tokens=self.cfg.max_output_tokens,
        )
        if self.cfg.json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        last_err: Exception | None = None
        # A single request must be able to walk every configured fallback key.
        max_attempts = max(self.cfg.max_retries + 1, len(self._clients))
        for attempt in range(max_attempts):
            await self._pace()
            client_index, client = await self._current_client()
            t0 = time.monotonic()
            try:
                resp = await client.chat.completions.create(**kwargs)
                usage.latency_s += time.monotonic() - t0
                if resp.usage:
                    usage.prompt_tokens += resp.usage.prompt_tokens or 0
                    usage.completion_tokens += resp.usage.completion_tokens or 0
                text = (resp.choices[0].message.content or "") if resp.choices else ""
                try:
                    data = parse_json_object(text)
                except LLMError as e:
                    last_err = e  # malformed reply: retry, the tokens still count
                    usage.retries += 1
                    continue
                self.usage.add(usage)
                return data, usage
            except (RateLimitError, APITimeoutError, APIConnectionError, APIStatusError) as e:
                usage.latency_s += time.monotonic() - t0
                status = getattr(e, "status_code", None)
                quota_error = is_quota_error(e)
                if isinstance(e, APIStatusError) and status is not None and status < 500 and not quota_error:
                    raise LLMError(f"{status}: {e}") from e
                last_err = e
                usage.retries += 1
                if quota_error:
                    await self._rotate_key(client_index)
                    delay = 0.0
                else:
                    retry_after = _retry_after(e)
                    delay = retry_after if retry_after is not None else min(60.0, 2.0 * 2**attempt)
                await asyncio.sleep(delay + random.uniform(0, 0.5))
        self.usage.add(usage)
        raise LLMError(f"LLM call failed after {max_attempts} attempts: {last_err}")

    async def _current_client(self) -> tuple[int, Any]:
        async with self._key_lock:
            return self._key_index, self._clients[self._key_index]

    async def _rotate_key(self, failed_index: int) -> None:
        if len(self._clients) == 1:
            return
        async with self._key_lock:
            if self._key_index == failed_index:
                self._key_index = (failed_index + 1) % len(self._clients)

    def cost_usd(self, usage: Usage | None = None) -> float:
        u = usage or self.usage
        return (u.prompt_tokens * self.cfg.price_in + u.completion_tokens * self.cfg.price_out) / 1e6


def _retry_after(e: Exception) -> float | None:
    resp = getattr(e, "response", None)
    if resp is None:
        return None
    value = resp.headers.get("retry-after")
    try:
        return min(120.0, float(value)) if value else None
    except ValueError:
        return None
