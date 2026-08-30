class TransientLLMError(Exception):
    """Erreur LLM transitoire (rate limit 429, surcharge 529) — seule
    catégorie retentée par la politique de retry (module 4.3).

    Traduite par ``AnthropicClient`` depuis les exceptions réelles du SDK
    Anthropic, pour que le code de retry reste indépendant du SDK (le même
    mécanisme fonctionne avec ``FakeLLM`` en test, sans dépendance au
    package ``anthropic``). Toute autre exception — y compris les erreurs
    HTTP non transitoires (400, 401...) et les bugs de code — n'est jamais
    retentée : elle est soit isolée par item (frontière déjà en place dans
    ``score_item``/``drafting``), soit propagée telle quelle si elle survient
    hors de cette frontière.
    """
