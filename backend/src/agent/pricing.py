"""Provider/model-aware LLM pricing resolution."""

from dataclasses import dataclass

from core import settings

DEEPSEEK_PRICING_SOURCE_URL = "https://api-docs.deepseek.com/quick_start/pricing"


@dataclass(frozen=True)
class ModelPricing:
    provider: str
    model: str
    input_cache_miss_usd_per_1m_tokens: float
    output_usd_per_1m_tokens: float
    input_cache_hit_usd_per_1m_tokens: float | None = None
    source: str = "registry"
    note: str | None = None


DEEPSEEK_MODEL_PRICING: dict[str, ModelPricing] = {
    "deepseek-v4-flash": ModelPricing(
        provider="deepseek",
        model="deepseek-v4-flash",
        input_cache_hit_usd_per_1m_tokens=0.0028,
        input_cache_miss_usd_per_1m_tokens=0.14,
        output_usd_per_1m_tokens=0.28,
        source=DEEPSEEK_PRICING_SOURCE_URL,
    ),
    "deepseek-v4-pro": ModelPricing(
        provider="deepseek",
        model="deepseek-v4-pro",
        input_cache_hit_usd_per_1m_tokens=0.003625,
        input_cache_miss_usd_per_1m_tokens=0.435,
        output_usd_per_1m_tokens=0.87,
        source=DEEPSEEK_PRICING_SOURCE_URL,
    ),
}

DEEPSEEK_MODEL_ALIASES = {
    "deepseek-chat": "deepseek-v4-flash",
    "deepseek-reasoner": "deepseek-v4-flash",
}


def _normalize(value: str) -> str:
    return value.strip().lower()


def _provider_for_model(model_name: str) -> str:
    configured_provider = _normalize(settings.llm_provider)
    if configured_provider != "auto":
        return configured_provider
    if _normalize(model_name).startswith("deepseek-"):
        return "deepseek"
    return "unknown"


def resolve_model_pricing(model_name: str | None = None) -> ModelPricing | None:
    resolved_model = model_name or settings.default_model
    normalized_model = _normalize(resolved_model)
    provider = _provider_for_model(resolved_model)

    if provider == "deepseek":
        canonical_model = DEEPSEEK_MODEL_ALIASES.get(normalized_model, normalized_model)
        pricing = DEEPSEEK_MODEL_PRICING.get(canonical_model)
        if pricing is None:
            return None
        if canonical_model == normalized_model:
            return pricing
        return ModelPricing(
            provider=pricing.provider,
            model=resolved_model,
            input_cache_hit_usd_per_1m_tokens=pricing.input_cache_hit_usd_per_1m_tokens,
            input_cache_miss_usd_per_1m_tokens=pricing.input_cache_miss_usd_per_1m_tokens,
            output_usd_per_1m_tokens=pricing.output_usd_per_1m_tokens,
            source=pricing.source,
            note=(
                f"{resolved_model} is priced as compatibility alias of "
                f"{canonical_model}."
            ),
        )

    return None


def estimate_cost_usd(
    input_tokens: int,
    output_tokens: int,
    *,
    cache_read_tokens: int = 0,
    model_name: str | None = None,
) -> float:
    pricing = resolve_model_pricing(model_name)
    if pricing is None:
        return 0.0

    billable_input_tokens = max(input_tokens, 0)
    billable_output_tokens = max(output_tokens, 0)
    cache_hit_tokens = max(min(cache_read_tokens, billable_input_tokens), 0)
    cache_miss_tokens = billable_input_tokens - cache_hit_tokens
    cache_hit_price = (
        pricing.input_cache_hit_usd_per_1m_tokens
        if pricing.input_cache_hit_usd_per_1m_tokens is not None
        else pricing.input_cache_miss_usd_per_1m_tokens
    )

    return round(
        (
            cache_miss_tokens * pricing.input_cache_miss_usd_per_1m_tokens
            + cache_hit_tokens * cache_hit_price
            + billable_output_tokens * pricing.output_usd_per_1m_tokens
        )
        / 1_000_000,
        8,
    )
