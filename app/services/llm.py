"""LLM service - wrapper for internal LiteLLM endpoint.

Designed to work across both classic chat models and newer reasoning models
(e.g. gpt-5.5), which reject parameters like a non-default ``temperature``.
We therefore degrade gracefully: send the preferred params, and if the proxy
rejects an unsupported parameter we retry without it.
"""

from openai import AsyncOpenAI, BadRequestError

from app.config import settings
from app.logging_config import logger
from app.secrets_manager import redact

# AsyncOpenAI client for LiteLLM (OpenAI-compatible API)
llm_client = AsyncOpenAI(
    api_key=settings.llm_api_key,
    base_url=settings.llm_base_url,
)


async def llm_check(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.1,
    max_tokens: int = 2000,
    creds: dict | None = None,
) -> str:
    """Run a single LLM check and return the response text.

    Retries without ``temperature`` if the model only supports the default,
    so reasoning models (gpt-5.x) work without special-casing each one.

    ``creds`` (BYOK): when provided with ``api_key``/``base_url``, an ephemeral
    client is built for this call so each user can use their own key. Falls
    back to the global client + ``settings.llm_model`` otherwise.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    if creds and creds.get("api_key") and creds.get("base_url"):
        client = AsyncOpenAI(api_key=creds["api_key"], base_url=creds["base_url"])
        model = creds.get("model") or settings.llm_model
    else:
        client = llm_client
        model = settings.llm_model

    kwargs = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if temperature is not None:
        kwargs["temperature"] = temperature

    try:
        response = await client.chat.completions.create(**kwargs)
    except BadRequestError as exc:
        msg = str(exc).lower()
        # Reasoning models reject non-default temperature; retry without it.
        if "temperature" in msg and "temperature" in kwargs:
            kwargs.pop("temperature", None)
            response = await client.chat.completions.create(**kwargs)
        else:
            logger.error(f"LLM request failed: {redact(str(exc))}")
            raise

    choice = response.choices[0].message
    content = choice.content or ""
    # Reasoning models may put text in reasoning_content when content is empty.
    if not content:
        content = getattr(choice, "reasoning_content", "") or ""
    return content
