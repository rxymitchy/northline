import json

from app.config import settings
from app.http_compat import http_post_json, response_text
from app.logging_util import estimate_openai_cost, record_usage


def chat_json(run_id: int | None, system: str, user: str, temperature: float = 0.2) -> str:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    payload = {
        "model": settings.openai_model,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    resp = http_post_json(
        "https://api.openai.com/v1/chat/completions",
        payload,
        headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        timeout=90,
    )
    if getattr(resp, "status_code", 0) >= 400:
        body = response_text(resp)[:500]
        if "insufficient_quota" in body or "credit" in body.lower():
            raise RuntimeError(
                "OpenAI account has no credits. Add billing at https://platform.openai.com/settings/organization/billing/"
            )
        raise RuntimeError(f"OpenAI HTTP {resp.status_code}: {body}")
    data = json.loads(response_text(resp))
    usage = data.get("usage") or {}
    tokens_in = int(usage.get("prompt_tokens") or 0)
    tokens_out = int(usage.get("completion_tokens") or 0)
    record_usage(
        run_id,
        "openai",
        settings.openai_model,
        tokens_in,
        tokens_out,
        estimate_openai_cost(tokens_in, tokens_out),
    )
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"OpenAI returned no choices: {data}")
    return (choices[0].get("message") or {}).get("content") or "{}"
