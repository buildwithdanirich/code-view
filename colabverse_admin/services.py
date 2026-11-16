"""Read-only, bounded platform checks. Never return connection secrets."""
import os
import shutil
import time
from django.apps import apps
from django.conf import settings
from django.db import connections
from django.utils import timezone

# Models are optional: dashboard remains functional during gradual integration.
MODEL_CANDIDATES = {
    "groups": ("community.ProjectGroup",),
    "memberships": ("community.GroupMember",),
    "meetings": ("community.GroupMeeting",),
    "questions": ("questions.Question",),
    "answers": ("questions.Answer",),
}

def model_count(labels):
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
    result = {"users": user_model._default_manager.count(), "active_users": user_model._default_manager.filter(is_active=True).count()}
    for name, labels in MODEL_CANDIDATES.items():
        result[name] = model_count(labels)
    return result

def check_database():
    started = time.monotonic()
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return {"status": "healthy", "detail": "Database responded", "latency_ms": round((time.monotonic()-started)*1000, 1)}
    except Exception:
        return {"status": "critical", "detail": "Database connection failed", "latency_ms": None}

def check_cache():
    # Only checks cache when explicitly enabled, to avoid assuming Redis exists.
    if not getattr(settings, "COLABVERSE_ADMIN_CHECK_CACHE", False):
        return {"status": "unconfigured", "detail": "Cache probe not enabled"}
    try:
        from django.core.cache import caches
        cache = caches["default"]
        key = "colabverse_admin:health_probe"
        value = str(time.time_ns())
        cache.set(key, value, timeout=15)
        if cache.get(key) != value:
            return {"status": "warning", "detail": "Cache probe did not round-trip"}
        return {"status": "healthy", "detail": "Cache responded"}
    except Exception:
        return {"status": "critical", "detail": "Cache probe failed"}

def disk_health():
    try:
        usage = shutil.disk_usage(settings.BASE_DIR)
        percent = round((usage.used / usage.total)*100, 1) if usage.total else 0
        status = "critical" if percent >= 95 else "warning" if percent >= 85 else "healthy"
        return {"status": status, "detail": f"Disk used: {percent}%", "percent": percent}
    except OSError:
        return {"status": "warning", "detail": "Disk metrics unavailable", "percent": None}

def memory_health():
    try:
        import psutil
        value = psutil.virtual_memory().percent
        status = "critical" if value >= 95 else "warning" if value >= 85 else "healthy"
        return {"status": status, "detail": f"Memory used: {value}%", "percent": value}
    except ImportError:
        return {"status": "unconfigured", "detail": "Install psutil to show memory usage", "percent": None}
    except Exception:
        return {"status": "warning", "detail": "Memory metrics unavailable", "percent": None}

def cpu_health():
    try:
        import psutil
        value = psutil.cpu_percent(interval=None)
        return {"status": "healthy", "detail": f"CPU usage (sample): {value}%", "percent": value}
    except ImportError:
        return {"status": "unconfigured", "detail": "Install psutil to show CPU usage", "percent": None}
    except Exception:
        return {"status": "warning", "detail": "CPU metrics unavailable", "percent": None}

def livekit_health():
    # Do not claim LiveKit is healthy without an authenticated service probe.
    return {"status": "unconfigured", "detail": "LiveKit health integration not configured"}

def health_report():
    checks = {
        "database": check_database(),
        "cache": check_cache(),
        "disk": disk_health(),
        "memory": memory_health(),
        "cpu": cpu_health(),
        "livekit": livekit_health(),
    }
    statuses = [v["status"] for v in checks.values()]
    overall = "critical" if "critical" in statuses else "warning" if "warning" in statuses else "healthy" if "healthy" in statuses else "unconfigured"
    return {"overall": overall, "checks": checks, "checked_at": timezone.now().isoformat()}
