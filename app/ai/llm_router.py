import hashlib
from typing import AsyncGenerator, Optional
from app.config import settings


# ─── Provider: Gemini ────────────────────────────────────────────────────────

async def _call_gemini(
    prompt: str,
    system: str,
    stream: bool = False,
) -> AsyncGenerator[str, None]:
    """
    Call Google Gemini API.
    Uses gemini-1.5-flash by default — fast and free tier available.
    """
    import google.generativeai as genai

    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not set")

    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel(
        model_name=settings.GEMINI_MODEL,
        system_instruction=system,
    )

    if stream:
        response = await model.generate_content_async(
            prompt,
            stream=True,
        )
        async for chunk in response:
            if chunk.text:
                yield chunk.text
    else:
        response = await model.generate_content_async(prompt)
        yield response.text


# ─── Provider: Groq ──────────────────────────────────────────────────────────

async def _call_groq(
    prompt: str,
    system: str,
    stream: bool = False,
) -> AsyncGenerator[str, None]:
    """
    Call Groq API — extremely fast inference.
    Uses llama3-8b-8192 by default.
    """
    from groq import AsyncGroq

    if not settings.GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not set")

    client = AsyncGroq(api_key=settings.GROQ_API_KEY)

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]

    if stream:
        response = await client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=messages,
            stream=True,
        )
        async for chunk in response:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
    else:
        response = await client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=messages,
            stream=False,
        )
        yield response.choices[0].message.content


# ─── Provider: OpenRouter ────────────────────────────────────────────────────

async def _call_openrouter(
    prompt: str,
    system: str,
    stream: bool = False,
) -> AsyncGenerator[str, None]:
    """
    Call OpenRouter API — aggregates many models.
    Used as final fallback.
    OpenRouter uses OpenAI-compatible API format.
    """
    from openai import AsyncOpenAI

    if not settings.OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY not set")

    client = AsyncOpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]

    if stream:
        response = await client.chat.completions.create(
            model=settings.OPENROUTER_MODEL,
            messages=messages,
            stream=True,
        )
        async for chunk in response:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
    else:
        response = await client.chat.completions.create(
            model=settings.OPENROUTER_MODEL,
            messages=messages,
            stream=False,
        )
        yield response.choices[0].message.content


# ─── LLM Router: tries each provider in order ────────────────────────────────

async def call_llm(
    prompt: str,
    system: str,
    stream: bool = False,
) -> tuple[AsyncGenerator[str, None], str]:
    """
    Main entry point for all LLM calls in Egloo.
    Returns (generator, model_name_used).

    Fallback order:
      1. Gemini (primary — best quality)
      2. Groq   (secondary — fastest)
      3. OpenRouter (fallback — most reliable)

    Each provider is tried in order.
    If it fails (no key, rate limit, timeout), moves to next.
    If all fail, raises RuntimeError.
    """
    providers = [
        ("gemini", _call_gemini),
        ("groq", _call_groq),
        ("openrouter", _call_openrouter),
    ]

    last_error = None

    for model_name, provider_fn in providers:
        try:
            # Test if provider is configured before trying
            if model_name == "gemini" and not settings.GEMINI_API_KEY:
                continue
            if model_name == "groq" and not settings.GROQ_API_KEY:
                continue
            if model_name == "openrouter" and not settings.OPENROUTER_API_KEY:
                continue

            gen = provider_fn(prompt, system, stream)
            # Peek at first chunk to verify connection works
            # We wrap in a peekable generator
            first_chunk = None
            buffer = []

            async for chunk in gen:
                first_chunk = chunk
                buffer.append(chunk)
                break

            if first_chunk is None:
                continue

            # Rebuild full generator: yield buffered + rest
            async def _full_gen(buf, original_gen):
                for c in buf:
                    yield c
                async for c in original_gen:
                    yield c

            return _full_gen(buffer, gen), model_name

        except Exception as e:
            last_error = e
            print(f"[WARNING] LLM provider {model_name} failed: {e}")
            continue

    raise RuntimeError(
        f"All LLM providers failed. Last error: {last_error}. "
        f"Add at least one API key to .env: "
        f"GEMINI_API_KEY, GROQ_API_KEY, or OPENROUTER_API_KEY"
    )


async def call_llm_simple(
    prompt: str,
    system: str,
) -> tuple[str, str]:
    """
    Non-streaming LLM call — collects full response as string.
    Returns (full_text, model_name).
    Used for digest generation, topic clustering, etc.
    """
    gen, model_name = await call_llm(prompt, system, stream=False)
    chunks = []
    async for chunk in gen:
        chunks.append(chunk)
    return "".join(chunks), model_name


# ─── Query hash helper (for Redis cache) ─────────────────────────────────────

def hash_query(user_id: str, question: str) -> str:
    """
    Create a cache key from user_id + question.
    Same user asking same question returns cached answer.
    """
    raw = f"{user_id}:{question.strip().lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()
