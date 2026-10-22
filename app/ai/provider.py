"""Multi-backend LLM provider (Groq + Gemini + OpenAI, all OpenAI-compatible).

Strategy: backends are tried in Settings.llm_order until one succeeds.
If nothing is configured or everything fails -> deterministic offline fallback
(keeps the bot usable for UX checks).
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

import httpx

from app.ai.prompts.prompts import SYSTEM_PROMPT, build_user_prompt

log = logging.getLogger(__name__)


def _offline_rewrite(text: str, style: str) -> dict:
    """Deterministic fallback when no API key / API error (keeps bot usable)."""
    t = text.strip()
    t = re.sub(r"\s+", " ", t)
    if t and t[0].islower():
        # naive capitalize first letter (works for ru/uk/en)
        t = t[0].upper() + t[1:]
    if style == "short":
        # crude shorten: first sentence
        short = re.split(r"[.!?]\s", t)[0].strip(" .")
        main = short + "." if short else t
    elif style == "formal":
        main = t if t.endswith((".", "!", "?")) else t + "."
        main = f"Здравствуйте! {main} Заранее благодарю за понимание."
    elif style == "soft":
        main = t if t.endswith((".", "!", "?")) else t + "."
        main = f"{main} Надеюсь, это не причинит неудобств."
    elif style == "confident":
        main = re.sub(r"(?i)^(извини(те)?(,)?\s*(пожалуйста(,)?)?\s*)", "", t)
        main = re.sub(r"(?i)если можно[, ]*", "", main).strip()
        if main:
            main = main[0].upper() + main[1:]
    elif style == "fix":
        main = t  # best-effort: capitalization only
    else:
        main = t if t.endswith((".", "!", "?")) else t + "."
    return {
        "intent": "other",
        "language": "ru",
        "tone": style,
        "meaning": t[:200],
        "rewritten_text": main,
        "alternatives": [],
        "suggestion": "",
    }


def _extract_json(text: str) -> dict:
    """Parse JSON even if the model wrapped it in markdown or prose."""
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except Exception:
            pass
    # Last resort: treat whole text as the rewritten variant
    return {"rewritten_text": text[:2000]}


@dataclass
class Backend:
    name: str  # groq | gemini | openai
    api_key: str
    base_url: str
    model: str
    vision_model: str = ""
    stt_model: str = ""
    timeout: int = 60
    alt_models: list[str] = field(default_factory=list)

    @property
    def chat_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"

    @property
    def stt_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/audio/transcriptions"


class LLMProvider:
    """Unified provider. Backward compatible: LLMProvider(api_key, base_url, model)
    creates a single-backend instance (used in tests)."""

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        timeout: int = 60,
        backends: list[Backend] | None = None,
        backend_name: str = "openai",
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        # transport — точка инъекции для тестов (httpx.MockTransport)
        self.transport = transport
        self.error_callback = None  # hook: async fn(backend_name, op, exc)
        self.timeout = timeout
        if backends is not None:
            self.backends: list[Backend] = backends
        elif api_key:
            self.backends = [Backend(backend_name, api_key, base_url, model, timeout=timeout)]
        else:
            self.backends = []
        # compat attrs (first backend)
        self.api_key = self.backends[0].api_key if self.backends else ""
        self.base_url = self.backends[0].base_url if self.backends else base_url
        self.model = self.backends[0].model if self.backends else model

    @classmethod
    def from_settings(cls, settings) -> "LLMProvider":
        order = settings.backend_order
        available: dict[str, Backend] = {}
        if settings.groq_api_key:
            available["groq"] = Backend(
                "groq", settings.groq_api_key, settings.groq_base_url,
                settings.groq_model, vision_model=settings.groq_vision_model,
                stt_model=settings.groq_stt_model, timeout=settings.openai_timeout,
            )
        if settings.gemini_api_key:
            primary = settings.gemini_model
            alts = [m for m in ("gemini-3.8-flash", "gemini-3-flash-preview", "gemini-3.7-flash", "gemini-3.5-flash") if m != primary]
            available["gemini"] = Backend(
                "gemini", settings.gemini_api_key, settings.gemini_base_url,
                primary, timeout=settings.openai_timeout, alt_models=alts,
            )
        if settings.openai_api_key:
            available["openai"] = Backend(
                "openai", settings.openai_api_key, settings.openai_base_url,
                settings.openai_model, stt_model="whisper-1", timeout=settings.openai_timeout,
            )
        backends = [available[name] for name in order if name in available]
        inst = cls(backends=backends, timeout=settings.openai_timeout)
        return inst

    @property
    def configured(self) -> bool:
        return bool(self.backends)

    @property
    def backend_names(self) -> list[str]:
        return [b.name for b in self.backends]

    # ---------------- chat ----------------


    async def _notify_backend_error(self, backend: Backend, op: str, exc: Exception) -> None:
        """Telemetry hook (расширенный /admin / лог ошибок LLM в БД)."""
        cb = self.error_callback
        if cb is None:
            return
        try:
            await cb(backend.name, op, exc)
        except Exception:
            log.exception("provider error_callback failed")

    async def _chat(self, backend: Backend, messages: list[dict], want_json: bool) -> str:
        models = [backend.model] + list(backend.alt_models)
        last_err: Exception | None = None
        for i, model in enumerate(models):
            payload: dict = {"model": model, "temperature": 0.7, "messages": messages}
            if want_json:
                payload["response_format"] = {"type": "json_object"}
            try:
                async with httpx.AsyncClient(timeout=backend.timeout, transport=self.transport) as client:
                    resp = await client.post(
                        backend.chat_url,
                        headers={"Authorization": f"Bearer {backend.api_key}"},
                        json=payload,
                    )
                    resp.raise_for_status()
                    return resp.json()["choices"][0]["message"]["content"]
            except httpx.HTTPStatusError as e:
                # Some models reject response_format -> retry as plain text
                if want_json and e.response.status_code == 400:
                    log.warning("%s rejected json_object mode, retrying plain", backend.name)
                    async with httpx.AsyncClient(timeout=backend.timeout, transport=self.transport) as client:
                        payload.pop("response_format", None)
                        resp = await client.post(
                            backend.chat_url,
                            headers={"Authorization": f"Bearer {backend.api_key}"},
                            json=payload,
                        )
                        resp.raise_for_status()
                        return resp.json()["choices"][0]["message"]["content"]
                # 429/5xx -> try next model of the same backend
                if e.response.status_code in (429, 500, 502, 503) and i < len(models) - 1:
                    log.warning("%s model %s busy (%s), trying %s", backend.name, model,
                                e.response.status_code, models[i + 1])
                    last_err = e
                    continue
                raise
            except (httpx.ConnectError, httpx.ReadTimeout) as e:
                if i < len(models) - 1:
                    last_err = e
                    continue
                raise
        assert last_err is not None
        raise last_err

    async def rewrite(
        self,
        text: str,
        style: str = "neutral",
        target_lang: str | None = None,
        custom_style: str | None = None,
        user_style: dict | None = None,
        recipient: str | None = None,
        context_text: str | None = None,
        reply_mode: bool = False,
    ) -> dict:
        if not self.configured:
            return _offline_rewrite(text, style)
        user_prompt = build_user_prompt(
            text, style, target_lang, custom_style, user_style, recipient, context_text, reply_mode
        )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        last_err: Exception | None = None
        for backend in self.backends:
            try:
                content = await self._chat(backend, messages, want_json=True)
                parsed = _extract_json(content)
                out = self._normalize(parsed, style)
                out["_backend"] = backend.name
                return out
            except Exception as e:
                log.warning("LLM backend %s failed: %s", backend.name, e)
                await self._notify_backend_error(backend, "rewrite", e)
                last_err = e
                continue
        log.warning("All LLM backends failed (%s), offline fallback", last_err)
        return _offline_rewrite(text, style)

    def _normalize(self, parsed: dict, style: str) -> dict:
        out = {
            "intent": str(parsed.get("intent", "other")),
            "language": str(parsed.get("language", "ru")),
            "tone": str(parsed.get("tone", style)),
            "meaning": str(parsed.get("meaning", "")),
            "rewritten_text": str(parsed.get("rewritten_text", "")),
            "alternatives": [],
            "suggestion": str(parsed.get("suggestion", "")),
        }
        alts = parsed.get("alternatives") or []
        for a in alts[:3]:
            if isinstance(a, dict) and a.get("text"):
                out["alternatives"].append({"style": str(a.get("style", "neutral")), "text": str(a["text"])})
        if not out["rewritten_text"]:
            # model returned something unexpected — stringify
            out["rewritten_text"] = json.dumps(parsed, ensure_ascii=False)[:1000]
        return out

    # ---------------- speech ----------------

    async def transcribe_voice(self, audio_bytes: bytes, filename: str = "voice.ogg") -> str:
        """Whisper-compatible transcription via Groq/OpenAI. Raises if none configured."""
        last_err: Exception | None = None
        for backend in self.backends:
            stt_model = backend.stt_model or ("whisper-1" if backend.name == "openai" else "")
            if not stt_model:
                continue  # e.g. gemini has no whisper endpoint
            try:
                async with httpx.AsyncClient(timeout=120, transport=self.transport) as client:
                    files = {"file": (filename, audio_bytes, "audio/ogg"), "model": (None, stt_model)}
                    resp = await client.post(
                        backend.stt_url,
                        headers={"Authorization": f"Bearer {backend.api_key}"},
                        files=files,
                    )
                    resp.raise_for_status()
                    return resp.json().get("text", "")
            except Exception as e:
                log.warning("STT backend %s failed: %s", backend.name, e)
                await self._notify_backend_error(backend, "transcribe", e)
                last_err = e
        raise RuntimeError(f"STT not available (tried {[b.name for b in self.backends]}): {last_err}")

    # ---------------- vision ----------------

    async def extract_text_from_image(self, image_bytes: bytes) -> str:
        """Vision OCR via chat-completions image_url. Raises if not configured."""
        import base64

        b64 = base64.b64encode(image_bytes).decode()
        last_err: Exception | None = None
        for backend in self.backends:
            model = backend.vision_model or backend.model
            try:
                async with httpx.AsyncClient(timeout=backend.timeout, transport=self.transport) as client:
                    resp = await client.post(
                        backend.chat_url,
                        headers={"Authorization": f"Bearer {backend.api_key}"},
                        json={
                            "model": model,
                            "messages": [
                                {
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": "Извлеки весь текст с этого изображения. Верни только текст, без комментариев."},
                                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                                    ],
                                }
                            ],
                        },
                    )
                    resp.raise_for_status()
                    return resp.json()["choices"][0]["message"]["content"].strip()
            except Exception as e:
                log.warning("Vision backend %s failed: %s", backend.name, e)
                await self._notify_backend_error(backend, "vision", e)
                last_err = e
        raise RuntimeError(f"Vision not available: {last_err}")
