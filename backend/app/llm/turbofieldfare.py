"""TurboFieldfare's single-choice text Chat Completions adapter. No SDK retries."""
import asyncio
import json
import time

import httpx

from ..errors import AppError
from ..providers import GenerationService, PROMPT_VERSION, SCHEMA_VERSION, check_cancel
from .identity import LaunchIdentity
from .sse import SSEDecoder


class TurboFieldfare(GenerationService):
    provider_name = "turbofieldfare"
    output_setting = "LLM_MAX_OUTPUT_TOKENS"
    capabilities = {"json_schema": False, "json_mode": False, "streaming": True,
                    "tool_execution": False, "context_control": "server-startup",
                    "thinking_control": "not-exposed"}

    def __init__(self, settings):
        super().__init__(settings)
        self.identity = LaunchIdentity(settings)
        self.origin = settings.base_url.removesuffix("/v1")
        self.transport_metrics = {}

    def readiness(self):
        try:
            with httpx.Client(timeout=5, trust_env=False, follow_redirects=False) as client:
                health = client.get(self.origin + "/health")
                models = client.get(self.settings.base_url + "/models")
                health.raise_for_status()
                models.raise_for_status()
                status, listing = health.json(), models.json()
                if not isinstance(status, dict) or not isinstance(listing, dict) or status.get("status") != "ok":
                    raise ValueError("Server /health is not ready.")
                rows = listing["data"]
                if not isinstance(rows, list) or len(rows) != 1 or rows[0]["id"] != self.settings.model:
                    raise ValueError("/v1/models must serve gemma-4-26b-a4b-it only.")
            self.details = self.identity.verify()
            # No fabricated Ollama digest: manifest_sha256 is labelled in the fingerprint.
            return self.details
        except httpx.HTTPError:
            raise AppError("TURBOFIELDFARE_UNAVAILABLE", "TurboFieldfare is unavailable. Start the verified loopback server on LLM_BASE_URL; no fallback was used.", 503) from None
        except (KeyError, TypeError, ValueError):
            raise AppError("MODEL_CONFIG_INCOMPATIBLE", "TurboFieldfare returned incompatible health/model metadata. Check LLM_BASE_URL, LLM_MODEL and the runtime revision.", 503) from None

    def fingerprint(self):
        self.readiness()
        return {"provider": self.provider_name, "adapter_version": "turbofieldfare-sse-1",
                **self.details, "model": self.settings.model,
                "context": self.settings.context, "context_scope": "client-budget; server capacity in runtime_profile",
                "max_completion_tokens": self.settings.predict, "temperature": 0,
                "seed": 42, "retry_seeds": [43, 44], "repetition_penalty": 1.0,
                "reasoning_policy": "inspected no-tool template closes empty thought channel; runtime filters thoughts; no API switch; content-only",
                "capabilities": self.capabilities, "prompt_version": PROMPT_VERSION,
                "schema_version": SCHEMA_VERSION, "parser_version": "strict-json-sse-3-container-guard",
                "repair_policy_version": "compact-two-attempts-v1", "authoring_version": "compact-1"}

    def complete(self, messages, schema, attempt, cancel, content):
        check_cancel(cancel)
        # Sync job boundary, async I/O inside: cancellation closes the socket even
        # during prefill. No detached inference thread can outlive this method.
        return asyncio.run(self._bounded(messages, attempt, cancel, content))

    async def _bounded(self, messages, attempt, cancel, content):
        self.transport_metrics = {}
        task = asyncio.create_task(self._request(messages, attempt, content))
        deadline = min(time.monotonic() + self.settings.attempt_timeout,
                       getattr(self, 'generation_deadline', None) or float('inf'),
                       getattr(cancel, 'deadline', None) or float('inf'))
        try:
            while not task.done():
                check_cancel(cancel)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    code = 'MODEL_TASK_TIMEOUT' if getattr(self, 'generation_deadline', None) is not None else 'MODEL_TIMEOUT'
                    raise AppError(code, 'TurboFieldfare reached the generation time limit. Preparation was stopped instead of repeating slow requests; sources and ready shorts are saved.', 503)
                await asyncio.wait({task}, timeout=min(.05, remaining))
            check_cancel(cancel)
            return await task
        finally:
            if not task.done():
                task.cancel()
            # Await stream/client cleanup before allowing another model job.
            await asyncio.gather(task, return_exceptions=True)

    async def _request(self, messages, attempt, content):
        payload = {"model": self.settings.model, "messages": messages, "stream": True,
                   "stream_options": {"include_usage": True}, "temperature": 0,
                   "seed": 42 + attempt, "repetition_penalty": 1.0,
                   "max_completion_tokens": self.settings.predict}
        started = time.monotonic()
        finish = None
        done = False
        decoder = SSEDecoder()
        timeout = httpx.Timeout(self.settings.read_timeout, connect=self.settings.connect_timeout)
        async with httpx.AsyncClient(timeout=timeout, trust_env=False, follow_redirects=False) as client:
            async with client.stream("POST", self.settings.base_url + "/chat/completions", json=payload) as response:
                if not response.is_success:
                    # Read only a bounded envelope; never show server messages/prompts.
                    body = b""
                    async for chunk in response.aiter_bytes():
                        body += chunk[:8192 - len(body)]
                        if len(body) >= 8192:
                            break
                    code = "unknown"
                    try:
                        code = json.loads(body).get("error", {}).get("code", "unknown")
                    except (ValueError, AttributeError):
                        pass
                    self.transport_metrics = {"http_status": response.status_code, "server_error_code": str(code)[:80]}
                    raise AppError("MODEL_REQUEST_FAILED", f"TurboFieldfare rejected the request (HTTP {response.status_code}). Check the model, context and supported API fields; see local diagnostics.", 503)
                if response.headers.get("content-type", "").split(";")[0] != "text/event-stream":
                    raise AppError("MODEL_PROTOCOL_INVALID", "TurboFieldfare did not return an SSE stream.", 503)
                async for chunk in response.aiter_bytes():
                    for frame in decoder.feed(chunk):
                        if done:
                            raise ValueError("Unexpected frame after [DONE].")
                        if frame == "[DONE]":
                            if finish is None:
                                raise ValueError("[DONE] arrived without a finish reason.")
                            done = True
                            continue
                        part = json.loads(frame)
                        if not isinstance(part, dict):
                            raise ValueError("Invalid SSE object.")
                        if part.get("error"):
                            raise AppError("MODEL_REQUEST_FAILED", "TurboFieldfare failed during streaming; check the local server log.", 503)
                        if part.get("model") != self.settings.model:
                            raise AppError("MODEL_CONFIG_INCOMPATIBLE", "TurboFieldfare streamed a different model identity.", 503)
                        choices = part.get("choices")
                        if not isinstance(choices, list) or len(choices) > 1:
                            raise ValueError("Invalid SSE choices.")
                        if not choices:
                            if not isinstance(part.get("usage"), dict):
                                raise ValueError("Empty SSE choices without usage.")
                            self._usage(part["usage"])
                            continue
                        choice = choices[0]
                        if not isinstance(choice, dict) or type(choice.get("index")) is not int or choice["index"] != 0:
                            raise ValueError("Unexpected SSE choice index.")
                        delta = choice.get("delta")
                        if not isinstance(delta, dict):
                            raise ValueError("Invalid SSE delta.")
                        if delta.get("role") not in (None, "assistant"):
                            raise ValueError("Unexpected SSE role.")
                        if any(delta.get(key) for key in ("tool_calls", "function_call", "refusal", "reasoning_content", "reasoning")):
                            raise ValueError("Unexpected tool/refusal/reasoning channel; text-only lesson output is required.")
                        text = delta.get("content")
                        if text is not None:
                            if not isinstance(text, str) or finish is not None:
                                raise ValueError("Invalid or post-finish SSE content.")
                            if text:
                                self.transport_metrics.setdefault("ttft_seconds", time.monotonic() - started)
                                content(text)
                        reason = choice.get("finish_reason")
                        if reason is not None:
                            if finish is not None or reason not in ("stop", "length"):
                                raise ValueError("Unexpected or duplicate SSE finish reason.")
                            finish = reason
                decoder.finish()
        if not done or finish is None:
            raise ValueError("The model stream ended before finish and [DONE] markers.")
        return finish

    def _usage(self, usage):
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            if key in usage and type(usage[key]) is int and usage[key] >= 0:
                self.transport_metrics[key] = usage[key]
        details = usage.get("prompt_tokens_details")
        if details is not None and not isinstance(details, dict):
            raise ValueError("Invalid SSE prompt-token details.")
        cached = (details or {}).get("cached_tokens")
        if type(cached) is int and cached >= 0:
            self.transport_metrics["cached_prompt_tokens"] = cached
