"""
Celery background worker tasks for payout processing.
"""

from celery import shared_task
from celery.utils.log import get_task_logger
from django.utils import timezone
from datetime import timedelta
import random

logger = get_task_logger(__name__)

MAX_ATTEMPTS = 3
STUCK_THRESHOLD_SECONDS = 30


@shared_task(bind=True, max_retries=MAX_ATTEMPTS)
def process_payout(self, payout_id: str):
    """
    Process a single payout.

    Workflow:
    1. Fetch the payout
    2. Check if it's PENDING (guard against processing twice)
    3. Move to PROCESSING
    4. Simulate bank API call
    5. Transition to COMPLETED or FAILED based on outcome
    6. On FAILED: transition_payout atomically creates a CREDIT refund entry
    7. On COMPLETED: transition_payout atomically creates a DEBIT settlement entry
    """
    from .models import Payout
    from .services import transition_payout

    try:
        payout = Payout.objects.select_for_update().get(pk=payout_id)
    except Payout.DoesNotExist:
        logger.error(f"Payout {payout_id} not found")
        return

    # Guard: only process pending payouts
    if payout.status != Payout.PENDING:
        logger.info(f"Payout {payout_id} is {payout.status}, skipping")
        return

    # Move to PROCESSING
    payout.status = Payout.PROCESSING
    payout.processing_started_at = timezone.now()
    payout.attempt_count += 1
    payout.save(update_fields=["status", "processing_started_at",
                                "attempt_count", "updated_at"])

    # Simulate bank API call
    # 70% success, 20% failure, 10% hang (timeout)
    outcome = random.choices(
        ["success", "failure", "hang"],
        weights=[70, 20, 10]
    )[0]

    if outcome == "success":
        transition_payout(payout, Payout.COMPLETED)
        logger.info(f"Payout {payout_id} completed")

    elif outcome == "failure":
        transition_payout(payout, Payout.FAILED,
                          failure_reason="Bank rejected the transfer")
        logger.warning(f"Payout {payout_id} failed")

    elif outcome == "hang":
        # Don't transition — the retry task will pick it up
        logger.warning(f"Payout {payout_id} hanging in processing")


@shared_task
def retry_stuck_payouts():
    """
    Periodic task: find payouts stuck in PROCESSING > 30 seconds.
    Uses exponential backoff. After MAX_ATTEMPTS, moves to failed.

    This task runs every 30 seconds (configured in settings.CELERY_BEAT_SCHEDULE).
    """
    from .models import Payout
    from .services import transition_payout

    threshold = timezone.now() - timedelta(seconds=STUCK_THRESHOLD_SECONDS)

    stuck_payouts = Payout.objects.filter(
        status=Payout.PROCESSING,
        processing_started_at__lt=threshold,
    )

    for payout in stuck_payouts:
        if payout.attempt_count >= MAX_ATTEMPTS:
            transition_payout(payout, Payout.FAILED,
                              failure_reason="Max retry attempts exceeded")
            logger.error(f"Payout {payout.id} exhausted retries → failed")
        else:
            # Exponential backoff: 2^attempt_count seconds
            backoff = 2 ** payout.attempt_count
            # Reset to pending so process_payout can pick it up
            payout.status = Payout.PENDING
            payout.save(update_fields=["status", "updated_at"])
            process_payout.apply_async(args=[str(payout.id)], countdown=backoff)
            logger.info(
                f"Payout {payout.id} retrying in {backoff}s "
                f"(attempt {payout.attempt_count + 1}/{MAX_ATTEMPTS})"
            )
