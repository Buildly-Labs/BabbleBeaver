"""
Task-based routing for LLMManager.

Lets operators declare which provider(s) should handle which *kind* of task
(code generation, summarization, extraction, chat, reasoning, ...) via
environment variables, then refines that ordering over time using recorded
outcomes (success/failure, latency) so a provider that's failing or slow for
a given task type gets tried later without anyone editing config by hand.

Configuration:
    ROUTE_<TASK_TYPE>=<provider_name>[,<provider_name>...]

    Provider names are LLMConfig.name values (a provider's own type name by
    default, e.g. "openai", "gemini", "digitalocean", or a custom BYOT
    endpoint's name from CUSTOM_ENDPOINTS). Example:

        ROUTE_CODE=myollama,openai
        ROUTE_SUMMARIZE=digitalocean
        ROUTE_CHAT=openai,digitalocean

    A task type with no ROUTE_<TASK_TYPE> configured falls back to the
    LLMManager's normal priority order (unchanged default behavior).
"""

import os
import logging
from typing import List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Small fixed starting taxonomy. Not enforced strictly - an unrecognized
# task_type simply won't match a ROUTE_<TASK_TYPE> rule and falls back to
# default priority order, so this list can grow without a code migration.
KNOWN_TASK_TYPES = ["chat", "code", "summarize", "extract", "reason"]

DEFAULT_TASK_TYPE = "chat"

# How much recent outcome history to weigh, and how much a struggling
# provider gets pushed back (not excluded - it can still be tried last).
OUTCOME_LOOKBACK = timedelta(hours=24)
MIN_SAMPLES_TO_SCORE = 3


def get_configured_route(task_type: str) -> List[str]:
    """
    Return the ordered list of provider names configured for a task type via
    ROUTE_<TASK_TYPE>, or an empty list if none is configured.
    """
    env_key = f"ROUTE_{task_type.upper()}"
    raw = os.getenv(env_key, "")
    return [name.strip() for name in raw.split(",") if name.strip()]


def score_providers(task_type: str, provider_names: List[str]) -> List[str]:
    """
    Reorder provider_names using recent outcome history for this task_type.

    Providers with a higher recent success rate and lower average latency
    for this specific task type are moved earlier. Providers with too few
    samples (< MIN_SAMPLES_TO_SCORE) or no history are left in their
    configured relative order (neither promoted nor demoted), so a brand
    new route works exactly as configured until data accumulates.
    """
    if len(provider_names) <= 1:
        return provider_names

    try:
        from database import db_manager, RoutingOutcome
    except Exception as e:
        logger.warning(f"Routing outcome scoring unavailable ({e}); using configured order.")
        return provider_names

    since = datetime.utcnow() - OUTCOME_LOOKBACK
    scores = {}

    try:
        with db_manager.get_session() as session:
            for name in provider_names:
                rows = (
                    session.query(RoutingOutcome)
                    .filter(
                        RoutingOutcome.task_type == task_type,
                        RoutingOutcome.provider_name == name,
                        RoutingOutcome.timestamp >= since,
                    )
                    .all()
                )
                if len(rows) < MIN_SAMPLES_TO_SCORE:
                    scores[name] = None  # not enough data - stays neutral
                    continue

                successes = sum(1 for r in rows if r.success)
                success_rate = successes / len(rows)
                latencies = [r.latency_ms for r in rows if r.latency_ms is not None]
                avg_latency = sum(latencies) / len(latencies) if latencies else 0

                # Success rate dominates; latency is a secondary tiebreaker
                # normalized into a small penalty (ms -> a fraction of a point).
                scores[name] = success_rate - min(avg_latency / 100_000, 0.2)
    except Exception as e:
        logger.warning(f"Failed to read routing outcomes ({e}); using configured order.")
        return provider_names

    # Stable sort: unscored providers (None) keep their original relative
    # position by being treated as better than any *measured* poor performer
    # but worse than any measured good one - i.e. sort only moves providers
    # with actual evidence, up or down, around the neutral unscored ones.
    def sort_key(item):
        idx, name = item
        s = scores.get(name)
        if s is None:
            return (0, idx)  # neutral: keep original order
        return (-s, idx)  # higher score first

    indexed = list(enumerate(provider_names))
    indexed.sort(key=sort_key)
    return [name for _, name in indexed]


def resolve_provider_order(task_type: Optional[str]) -> List[str]:
    """
    Resolve the provider name order to try for a given task type.

    Returns an empty list if no route is configured for this task type,
    signaling the caller to fall back to LLMManager's default priority order.
    """
    task_type = (task_type or DEFAULT_TASK_TYPE).strip().lower()
    configured = get_configured_route(task_type)
    if not configured:
        return []
    return score_providers(task_type, configured)


def record_outcome(
    task_type: Optional[str],
    provider_name: str,
    provider_type: str,
    success: bool,
    latency_ms: Optional[int] = None,
    error: Optional[str] = None,
):
    """Persist a single routing attempt's outcome for future scoring."""
    task_type = (task_type or DEFAULT_TASK_TYPE).strip().lower()
    try:
        from database import db_manager, RoutingOutcome
        with db_manager.get_session() as session:
            session.add(RoutingOutcome(
                task_type=task_type,
                provider_name=provider_name,
                provider_type=provider_type,
                success=success,
                latency_ms=latency_ms,
                error=error,
            ))
    except Exception as e:
        # Outcome tracking is best-effort - never let it break the actual request.
        logger.warning(f"Failed to record routing outcome: {e}")
