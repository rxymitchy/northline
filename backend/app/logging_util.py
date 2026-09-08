from app.config import settings
from app.db import SessionLocal
from app.models import ApiUsage, EventLog


def log_event(run_id: int | None, event_type: str, message: str, payload: str = "{}", level: str = "info"):
    db = SessionLocal()
    try:
        db.add(
            EventLog(
                run_id=run_id,
                level=level,
                event_type=event_type,
                message=message,
                payload=payload,
            )
        )
        db.commit()
    finally:
        db.close()


def record_usage(
    run_id: int | None,
    provider: str,
    model: str | None,
    tokens_in: int,
    tokens_out: int,
    estimated_cost_usd: float,
):
    db = SessionLocal()
    try:
        db.add(
            ApiUsage(
                run_id=run_id,
                provider=provider,
                model=model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                estimated_cost_usd=estimated_cost_usd,
            )
        )
        db.commit()
    finally:
        db.close()


def estimate_openai_cost(tokens_in: int, tokens_out: int) -> float:
    return (tokens_in / 1_000_000) * settings.openai_input_cost_per_1m + (
        tokens_out / 1_000_000
    ) * settings.openai_output_cost_per_1m
