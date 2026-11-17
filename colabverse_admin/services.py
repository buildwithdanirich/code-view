"""
ColabVerse administration services.

Responsibilities:
    - Collect platform statistics.
    - Monitor PostgreSQL connectivity.
    - Check configured cache availability.
    - Monitor disk, memory, and CPU usage.
    - Report LiveKit monitoring configuration.
    - Provide a combined project health report.

Health checks must never expose database passwords,
API keys, tokens, or other sensitive information.
"""

import shutil
import time

from django.apps import apps
from django.conf import settings
from django.db import connections
from django.utils import timezone


# ---------------------------------------------------------
# PLATFORM STATISTICS
# ---------------------------------------------------------

# Models used by the administration dashboard.
#
# Questions, answers, and meetings are intentionally
# excluded from administration statistics.
MODEL_CANDIDATES = {
    "groups": (
        "community.ProjectGroup",
    ),
    "memberships": (
        "community.GroupMember",
    ),
}


def model_count(labels):
    """
    Count records belonging to the first available model.

    Return None when:
        - The model does not exist.
        - The database query fails.

    This allows the dashboard to remain usable
    while optional application features are integrated.
    """

    for label in labels:

        try:
            model = apps.get_model(label)

            return model._default_manager.count()

        except (LookupError, AttributeError):
            continue

        except Exception:
            return None

    return None


def get_counts(user_model):
    """
    Retrieve platform statistics.

    Includes:
        - Total registered users.
        - Active user accounts.
        - Communities and development groups.
        - Group memberships.

    Report and support ticket counts are added
    separately by the dashboard view.
    """

    result = {
        "users": (
            user_model._default_manager.count()
        ),
        "active_users": (
            user_model._default_manager
            .filter(is_active=True)
            .count()
        ),
    }

    # Retrieve optional community statistics.
    for name, labels in MODEL_CANDIDATES.items():

        result[name] = model_count(labels)

    return result


# ---------------------------------------------------------
# POSTGRESQL DATABASE HEALTH
# ---------------------------------------------------------

def check_database():
    """
    Verify that PostgreSQL responds to a simple query.

    Measures the time required to execute SELECT 1.

    This is a lightweight connectivity check,
    not a complete database performance assessment.
    """

    started = time.monotonic()

    try:

        with connections["default"].cursor() as cursor:

            cursor.execute("SELECT 1")

            cursor.fetchone()

        elapsed = (
            time.monotonic() - started
        ) * 1000

        return {
            "status": "healthy",
            "detail": "Database responded",
            "latency_ms": round(elapsed, 1),
        }

    except Exception:

        return {
            "status": "critical",
            "detail": "Database connection failed",
            "latency_ms": None,
        }


# ---------------------------------------------------------
# CACHE HEALTH
# ---------------------------------------------------------

def check_cache():
    """
    Check whether the configured Django cache works.

    Cache probing must be explicitly enabled through:

        COLABVERSE_ADMIN_CHECK_CACHE = True

    This avoids assuming that every deployment
    uses Redis or another external cache service.
    """

    if not getattr(
        settings,
        "COLABVERSE_ADMIN_CHECK_CACHE",
        False,
    ):

        return {
            "status": "unconfigured",
            "detail": "Cache probe not enabled",
        }

    try:

        from django.core.cache import caches

        cache = caches["default"]

        key = "colabverse_admin:health_probe"

        value = str(time.time_ns())

        # Store a temporary health-check value.
        cache.set(
            key,
            value,
            timeout=15,
        )

        # Verify the stored value can be retrieved.
        if cache.get(key) != value:

            return {
                "status": "warning",
                "detail": "Cache probe did not round-trip",
            }

        return {
            "status": "healthy",
            "detail": "Cache responded",
        }

    except Exception:

        return {
            "status": "critical",
            "detail": "Cache probe failed",
        }


# ---------------------------------------------------------
# DISK HEALTH
# ---------------------------------------------------------

def disk_health():
    """
    Check disk usage for the filesystem
    containing the Django project.

    Warning threshold: 85%
    Critical threshold: 95%
    """

    try:

        usage = shutil.disk_usage(
            settings.BASE_DIR
        )

        percent = (
            round(
                (usage.used / usage.total) * 100,
                1,
            )
            if usage.total
            else 0
        )

        if percent >= 95:

            status = "critical"

        elif percent >= 85:

            status = "warning"

        else:

            status = "healthy"

        return {
            "status": status,
            "detail": f"Disk used: {percent}%",
            "percent": percent,
        }

    except OSError:

        return {
            "status": "warning",
            "detail": "Disk metrics unavailable",
            "percent": None,
        }


# ---------------------------------------------------------
# MEMORY HEALTH
# ---------------------------------------------------------

def memory_health():
    """
    Monitor server memory usage.

    Uses the optional psutil package.

    Warning threshold: 85%
    Critical threshold: 95%
    """

    try:

        import psutil

        percent = psutil.virtual_memory().percent

        if percent >= 95:

            status = "critical"

        elif percent >= 85:

            status = "warning"

        else:

            status = "healthy"

        return {
            "status": status,
            "detail": f"Memory used: {percent}%",
            "percent": percent,
        }

    except ImportError:

        return {
            "status": "unconfigured",
            "detail": "Install psutil to show memory usage",
            "percent": None,
        }

    except Exception:

        return {
            "status": "warning",
            "detail": "Memory metrics unavailable",
            "percent": None,
        }


# ---------------------------------------------------------
# CPU HEALTH
# ---------------------------------------------------------

def cpu_health():
    """
    Monitor CPU usage using psutil.

    This is a non-blocking sample.

    The first sample may not represent
    meaningful recent CPU activity.
    """

    try:

        import psutil

        percent = psutil.cpu_percent(
            interval=None
        )

        if percent >= 95:

            status = "critical"

        elif percent >= 85:

            status = "warning"

        else:

            status = "healthy"

        return {
            "status": status,
            "detail": f"CPU usage (sample): {percent}%",
            "percent": percent,
        }

    except ImportError:

        return {
            "status": "unconfigured",
            "detail": "Install psutil to show CPU usage",
            "percent": None,
        }

    except Exception:

        return {
            "status": "warning",
            "detail": "CPU metrics unavailable",
            "percent": None,
        }


# ---------------------------------------------------------
# LIVEKIT SERVICE HEALTH
# ---------------------------------------------------------

def livekit_health():
    """
    Report LiveKit monitoring configuration.

    An authenticated LiveKit health check
    has not been integrated yet.

    Do not report LiveKit as healthy without
    verifying the actual service.
    """

    return {
        "status": "unconfigured",
        "detail": "LiveKit health integration not configured",
    }


# ---------------------------------------------------------
# OVERALL PROJECT HEALTH
# ---------------------------------------------------------

def health_report():
    """
    Collect project health information.

    Returns:
        - Overall health status.
        - Individual service checks.
        - Timestamp of the health check.

    An unconfigured service is not automatically
    considered healthy or unhealthy.
    """

    checks = {
        "database": check_database(),
        "cache": check_cache(),
        "disk": disk_health(),
        "memory": memory_health(),
        "cpu": cpu_health(),
        "livekit": livekit_health(),
    }

    statuses = [
        result["status"]
        for result in checks.values()
    ]

    # Determine the most serious reported condition.
    if "critical" in statuses:

        overall = "critical"

    elif "warning" in statuses:

        overall = "warning"

    elif "healthy" in statuses:

        overall = "healthy"

    else:

        overall = "unconfigured"

    return {
        "overall": overall,
        "checks": checks,
        "checked_at": timezone.now().isoformat(),
    }