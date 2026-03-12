from __future__ import annotations


def format_duration_human(duration_seconds: float) -> str:
    """Formatiert Sekunden als kompakte menschenlesbare Dauer (z.B. `1h 2m 3s`)."""
    total_seconds = max(0, int(round(duration_seconds)))
    days, remainder = divmod(total_seconds, 24 * 3600)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)
