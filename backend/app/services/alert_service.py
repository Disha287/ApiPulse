from datetime import datetime, timezone
import logging
from app.core.redis_client import get_redis
from app.models.models import Incident, Monitor

logger = logging.getLogger("apipulse.alerts")


async def trigger_alert_if_not_cooled_down(
    monitor: Monitor,
    incident: Incident,
    cooldown_seconds: int = 300,
) -> bool:
    """
    Attempts to acquire a Redis distributed cooldown lock for the monitor.
    If acquired, dispatches an alert banner and sets the TTL lock.
    If the lock already exists, suppresses the alert to prevent notification storms.
    """
    redis = await get_redis()
    lock_key = f"alert:cooldown:{monitor.id}"

    # Atomic SET if Not eXists with expiration
    acquired = await redis.set(lock_key, str(incident.id), ex=cooldown_seconds, nx=True)

    if acquired:
        logger.warning(
            "\n" + "=" * 65 + "\n"
            f"[ALERT DISPATCHED] 🚨 MONITOR DOWN (3-Strike Triggered)\n"
            f"Monitor:    {monitor.name} (ID: {monitor.id})\n"
            f"Target URL: {monitor.url} ({monitor.method})\n"
            f"Incident:   {incident.id} (Failures: {incident.failure_count})\n"
            f"Error:      {incident.trigger_error or 'Unknown Failure'}\n"
            f"Cooldown:   Active for {cooldown_seconds}s (Lock Key: {lock_key})\n"
            + "=" * 65
        )
        return True
    else:
        ttl = await redis.ttl(lock_key)
        logger.info(
            f"[ALERT SUPPRESSED BY REDIS COOLDOWN] Monitor '{monitor.name}' ({monitor.id}) "
            f"already alerted. Cooldown lock active (TTL: {ttl}s remaining)."
        )
        return False


async def send_recovery_notification(
    monitor: Monitor,
    incident: Incident,
) -> None:
    """
    Clears the Redis cooldown lock and dispatches a recovery notification banner.
    """
    redis = await get_redis()
    lock_key = f"alert:cooldown:{monitor.id}"
    await redis.delete(lock_key)

    duration_str = "Unknown"
    if incident.started_at and incident.resolved_at:
        duration_seconds = round(
            (incident.resolved_at - incident.started_at).total_seconds(), 1
        )
        duration_str = f"{duration_seconds}s"

    logger.info(
        "\n" + "=" * 65 + "\n"
        f"[RECOVERY DISPATCHED] ✅ MONITOR RECOVERED TO HEALTHY\n"
        f"Monitor:    {monitor.name} (ID: {monitor.id})\n"
        f"Target URL: {monitor.url}\n"
        f"Incident:   {incident.id} (Status: {incident.status})\n"
        f"Downtime:   {duration_str}\n"
        f"Lock:       Cooldown key {lock_key} cleared.\n"
        + "=" * 65
    )

