from datetime import datetime, timezone


def is_stale(lastseen: datetime, delay: int, jitter: float):
    """
    Convenience function for calculating staleness
    """
    interval_max = (delay + delay * jitter) + 30
    diff = getutcnow() - lastseen
    return diff.total_seconds() > interval_max


def getutcnow():
    return datetime.now(timezone.utc)
