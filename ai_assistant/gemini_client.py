"""One small, careful wrapper around the Gemini API for features that need structured (JSON) answers.

Used by the mock interview. It never logs prompts or answers (they can contain personal text).
Tests replace `generate_json`, so the test suite never contacts the real service.
"""
import json
import logging
import os
import re

logger = logging.getLogger(__name__)


class AIUnavailable(Exception):
    """The AI service is not configured or could not be reached."""


class AIInvalidResponse(Exception):
    """The AI answered, but not with usable JSON."""


def parse_json_text(raw):
    """Parse a model reply as JSON, tolerating a ```json fence around it."""
    text = (raw or "").strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1)
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise AIInvalidResponse("The AI reply was not valid JSON.") from exc


def generate_json(prompt, *, max_output_tokens=1200, temperature=0.3):
    """Send `prompt` to Gemini and return the parsed JSON reply (a dict or list)."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise AIUnavailable("GEMINI_API_KEY is not set.")

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise AIUnavailable("The google-genai package is not installed.") from exc

    # Same environment variables and defaults as the rest of the AI assistant.
    primary = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
    fallback = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.8-flash").strip()
    models = [primary] + ([fallback] if fallback and fallback != primary else [])

    client = None
    raw, last_error = "", None
    try:
        retry = types.HttpRetryOptions(
            attempts=2, initial_delay=0.5, max_delay=2.0, exp_base=2.0, jitter=0.25,
            http_status_codes=[408, 429, 500, 502, 503, 504],
        )
        client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=45000, retry_options=retry))
        for model in models:
            try:
                result = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=temperature,
                        max_output_tokens=max_output_tokens,
                    ),
                )
                raw = (getattr(result, "text", None) or "").strip()
                if raw:
                    break
            except Exception as exc:  # try the fallback model, then give up
                last_error = exc
                logger.warning("Gemini model %s failed: %s", model, str(exc)[:200])
    except Exception as exc:
        last_error = exc
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
    if not raw:
        raise AIUnavailable("The AI service did not return an answer.") from last_error
    return parse_json_text(raw)
