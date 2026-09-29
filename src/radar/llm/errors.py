class TransientLLMError(Exception):
    """Transient LLM error (rate limit 429, overload 529) — the only
    category retried by the retry policy (module 4.3).

    Translated by ``AnthropicClient`` from the real Anthropic SDK
    exceptions, so the retry code stays SDK-independent (the same
    mechanism works with ``FakeLLM`` in tests, with no dependency on the
    ``anthropic`` package). Any other exception — including non-transient
    HTTP errors (400, 401...) and code bugs — is never retried: it is
    either isolated per item (boundary already in place in
    ``score_item``/``drafting``), or propagated as is if it occurs
    outside that boundary.
    """
