"""LLM service - wrapper for internal LiteLLM endpoint."""

from openai import AsyncOpenAI

from app.config import settings

# AsyncOpenAI client for LiteLLM (OpenAI-compatible API)
llm_client = AsyncOpenAI(
    api_key=settings.llm_api_key,
    base_url=settings.llm_base_url,
)


async def llm_check(system_prompt: str, user_prompt: str) -> str:
    """Run a single LLM check and return the response text."""
    response = await llm_client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        max_tokens=2000,
    )
    return response.choices[0].message.content or ""
