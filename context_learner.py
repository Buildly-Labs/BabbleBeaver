"""
Context-level learning for ContextBuilder.

ContextBuilder can format request context into the system prompt using
different templates ("minimal" vs "verbose"). Which one actually produces
better results can vary by task type - e.g. verbose instructions might help
a reasoning/analysis task but just add noise to a short chat reply.

This module doesn't change what context is included (that's a separate,
larger step - see the "field-level relevance" note in README.md); it only
learns which *template* to prefer per task type, using the same outcome
signal (success/latency) already recorded by task_router - reusing the
`routing_outcomes` table's `context_template` column so both routing and
template choices are visible in one place.

Configuration:
    CONTEXT_TEMPLATE_<TASK_TYPE>=minimal|verbose

    A task type with no CONTEXT_TEMPLATE_<TASK_TYPE> configured uses
    ContextBuilder's own default (config-driven, currently "minimal").
"""

import os
import logging
from typing import Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

TEMPLATES = ["minimal", "verbose"]

# Same lookback/sample-size philosophy as task_router: don't act on a
# template choice until there's enough evidence, and only ever choose
# between the built-in templates, never invent a new one from data.
OUTCOME_LOOKBACK = timedelta(hours=24)
MIN_SAMPLES_TO_SCORE = 5


def get_configured_template(task_type: str) -> Optional[str]:
    """
    Return the template explicitly configured for a task type via
    CONTEXT_TEMPLATE_<TASK_TYPE>, or None if unconfigured (caller should
    fall back to ContextBuilder's own default).
    """
    env_key = f"CONTEXT_TEMPLATE_{task_type.upper()}"
    value = os.getenv(env_key, "").strip().lower()
    return value if value in TEMPLATES else None


def score_templates(task_type: str) -> Optional[str]:
    """
    Compare recent outcomes for each template on this task_type and return
    whichever has the better success rate (latency as tiebreaker), or None
    if there isn't enough evidence yet for at least two templates.
    """
    try:
        from database import db_manager, RoutingOutcome
    except Exception as e:
        logger.warning(f"Context template scoring unavailable ({e}).")
        return None

    since = datetime.utcnow() - OUTCOME_LOOKBACK
    scores = {}

    try:
        with db_manager.get_session() as session:
            for template in TEMPLATES:
                rows = (
                    session.query(RoutingOutcome)
                    .filter(
                        RoutingOutcome.task_type == task_type,
                        RoutingOutcome.context_template == template,
                        RoutingOutcome.timestamp >= since,
                    )
                    .all()
                )
                if len(rows) < MIN_SAMPLES_TO_SCORE:
                    continue
                successes = sum(1 for r in rows if r.success)
                success_rate = successes / len(rows)
                latencies = [r.latency_ms for r in rows if r.latency_ms is not None]
                avg_latency = sum(latencies) / len(latencies) if latencies else 0
                scores[template] = success_rate - min(avg_latency / 100_000, 0.2)
    except Exception as e:
        logger.warning(f"Failed to read context template outcomes ({e}).")
        return None

    if len(scores) < 2:
        # Need evidence for more than one template to justify picking a winner;
        # otherwise we'd "learn" a preference from a single template nobody
        # has compared against anything yet.
        return None

    return max(scores, key=scores.get)


def resolve_template(task_type: Optional[str], default_template: str) -> str:
    """
    Resolve which context template to use for this task type: explicit
    CONTEXT_TEMPLATE_<TASK_TYPE> config wins if set; otherwise, once enough
    outcome data exists comparing templates for this task type, use the
    learned winner; otherwise fall back to default_template (ContextBuilder's
    own configured default).
    """
    from task_router import DEFAULT_TASK_TYPE
    task_type = (task_type or DEFAULT_TASK_TYPE).strip().lower()

    configured = get_configured_template(task_type)
    if configured:
        return configured

    learned = score_templates(task_type)
    if learned:
        return learned

    return default_template
