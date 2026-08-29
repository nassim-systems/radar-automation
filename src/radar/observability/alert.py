from radar.observability.models import RunRecord


def check_alert(record: RunRecord, *, max_cost_usd: float) -> str | None:
    """Vérifie un run contre un seuil simple : coût excessif ou échecs LLM.

    Fonction pure. Renvoie un message d'alerte si un seuil est dépassé, sinon
    ``None``. Ne décide pas du signal (exit code, stderr) : ça reste la
    responsabilité de l'appelant (``app.main``).
    """
    if record.usage.cost_usd > max_cost_usd:
        return (
            f"coût du run ({record.usage.cost_usd:.4f} USD) "
            f"> seuil ({max_cost_usd:.4f} USD)"
        )
    if record.report.n_failures > 0:
        return f"{record.report.n_failures} échec(s) LLM durant le run"
    return None
