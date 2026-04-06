"""Garmin Connect helper: auth, fetch sleep/HRV/RHR/body battery, shape for briefing."""

import os
import time
import logging
from datetime import date, datetime
from pathlib import Path

from garminconnect import Garmin

logger = logging.getLogger(__name__)

AGENT_ROOT = Path(__file__).resolve().parent.parent
TOKENSTORE = AGENT_ROOT / "garmin_tokens"


def _prompt_mfa() -> str:
    """Read MFA code from stdin (used only on interactive first-time login)."""
    return input("Garmin MFA code: ").strip()


def _get_client() -> Garmin | None:
    """Authenticate with Garmin Connect. Returns None on failure.

    On first run (no cached tokens), authenticates with email+password.
    If the Garmin account has MFA enabled and this is an interactive session
    (TTY), prompts for the one-time code.  Subsequent runs load cached tokens
    and skip the network auth entirely.
    """
    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    if not email or not password:
        logger.warning("GARMIN_EMAIL or GARMIN_PASSWORD not set — skipping Garmin.")
        return None

    TOKENSTORE.mkdir(exist_ok=True)
    tokenstore_path = str(TOKENSTORE)

    # Only offer interactive MFA prompt when running in a terminal.
    # Automated (launchd) runs should not block waiting for input.
    import sys
    mfa_callback = _prompt_mfa if sys.stdin.isatty() else None

    try:
        client = Garmin(email=email, password=password, prompt_mfa=mfa_callback)
        mfa_status, _ = client.login(tokenstore=tokenstore_path)
        if mfa_status:
            # return_on_mfa=False (default) means the library handled MFA inline;
            # a non-None mfa_status here is unexpected — log and continue.
            logger.warning("Garmin login MFA status: %s", mfa_status)
        logger.info("Garmin Connect authenticated.")
        return client
    except Exception as e:
        logger.error("Garmin Connect auth failed: %s", e)
        return None


def _format_duration(total_seconds: int | float | None) -> str | None:
    """Format seconds into 'Xh Ym' string."""
    if not total_seconds or total_seconds <= 0:
        return None
    hours = int(total_seconds) // 3600
    minutes = (int(total_seconds) % 3600) // 60
    if hours > 0:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


def _format_stage(label: str, seconds: int | float | None) -> str | None:
    """Format a single sleep stage."""
    dur = _format_duration(seconds)
    return f"{label} {dur}" if dur else None


def _fetch_once(client: Garmin, target_date: str) -> dict | None:
    """Fetch all Garmin data for a single date. Returns raw dict or None."""
    try:
        sleep = client.get_sleep_data(target_date)
    except Exception as e:
        logger.warning("Garmin sleep fetch failed: %s", e)
        return None

    # Check if sleep data is present and complete
    daily_sleep = sleep.get("dailySleepDTO", {})
    sleep_start = daily_sleep.get("sleepStartTimestampLocal")
    sleep_end = daily_sleep.get("sleepEndTimestampLocal")
    if not sleep_start or not sleep_end:
        return None  # No sleep recorded or sync incomplete

    # Fetch remaining metrics — each can fail independently
    hrv = None
    try:
        hrv = client.get_hrv_data(target_date)
    except Exception as e:
        logger.warning("Garmin HRV fetch failed: %s", e)

    rhr = None
    try:
        rhr = client.get_rhr_day(target_date)
    except Exception as e:
        logger.warning("Garmin RHR fetch failed: %s", e)

    body_battery = None
    try:
        body_battery = client.get_body_battery(target_date)
    except Exception as e:
        logger.warning("Garmin body battery fetch failed: %s", e)

    return {
        "sleep": sleep,
        "hrv": hrv,
        "rhr": rhr,
        "body_battery": body_battery,
    }


def _shape(raw: dict) -> dict:
    """Shape raw Garmin API responses into the clean dict for the briefing."""
    daily_sleep = raw["sleep"].get("dailySleepDTO", {})

    # Sleep duration and times
    duration_secs = daily_sleep.get("sleepTimeSeconds")
    duration_str = _format_duration(duration_secs)

    sleep_score = daily_sleep.get("sleepScores", {}).get("overall", {}).get("value")

    # Bedtime / wake time from timestamps
    bedtime = None
    wake_time = None
    start_ts = daily_sleep.get("sleepStartTimestampLocal")
    end_ts = daily_sleep.get("sleepEndTimestampLocal")
    if start_ts:
        bedtime = datetime.fromtimestamp(start_ts / 1000).strftime("%H:%M")
    if end_ts:
        wake_time = datetime.fromtimestamp(end_ts / 1000).strftime("%H:%M")

    # Sleep stages
    deep = daily_sleep.get("deepSleepSeconds")
    light = daily_sleep.get("lightSleepSeconds")
    rem = daily_sleep.get("remSleepSeconds")
    awake = daily_sleep.get("awakeSleepSeconds")
    stage_parts = [
        _format_stage("deep", deep),
        _format_stage("REM", rem),
        _format_stage("light", light),
        _format_stage("awake", awake),
    ]
    stages_str = " · ".join(p for p in stage_parts if p)

    # HRV
    hrv_data = {}
    if raw.get("hrv"):
        hrv_summary = raw["hrv"].get("hrvSummary", {})
        # lastNight is the overnight HRV value
        hrv_value = hrv_summary.get("lastNight")
        hrv_baseline = hrv_summary.get("baseline")
        hrv_status = hrv_summary.get("status")  # BALANCED, UNBALANCED, LOW, etc.
        if hrv_value is not None:
            hrv_data = {
                "value_ms": round(hrv_value),
                "status": (hrv_status or "unknown").lower(),
                "baseline_ms": round(hrv_baseline) if hrv_baseline else None,
            }

    # Resting HR
    rhr_data = {}
    if raw.get("rhr"):
        rhr_entries = raw["rhr"].get("allMetrics", {}).get("metricsMap", {})
        rhr_vals = rhr_entries.get("WELLNESS_RESTING_HEART_RATE", [])
        if rhr_vals:
            latest = rhr_vals[0]  # Most recent entry
            rhr_value = latest.get("value")
            # Get 7-day baseline from the statistics
            stats = raw["rhr"].get("allMetrics", {}).get("metricsStatistics", {})
            rhr_baseline = None
            if stats:
                rhr_baseline_data = stats.get("WELLNESS_RESTING_HEART_RATE", {})
                rhr_baseline = rhr_baseline_data.get("mean")
            if rhr_value is not None:
                rhr_data = {
                    "value": round(rhr_value),
                    "baseline": round(rhr_baseline) if rhr_baseline else None,
                }

    # Body battery — morning value (highest charged value)
    bb_morning = None
    if raw.get("body_battery"):
        bb_list = raw["body_battery"]
        if isinstance(bb_list, list) and bb_list:
            # Body battery entries have 'charged' and 'drained' values
            bb_day = bb_list[0] if isinstance(bb_list[0], dict) else {}
            bb_morning = bb_day.get("charged")

    # Compute anomalies
    anomalies = _compute_anomalies(
        duration_secs=duration_secs,
        sleep_score=sleep_score,
        hrv=hrv_data,
        rhr=rhr_data,
        body_battery_morning=bb_morning,
    )

    return {
        "sleep": {
            "duration": duration_str,
            "score": sleep_score,
            "bedtime": bedtime,
            "wake_time": wake_time,
            "stages": stages_str,
        },
        "hrv": hrv_data,
        "resting_hr": rhr_data,
        "body_battery_morning": bb_morning,
        "anomalies": anomalies,
    }


def _compute_anomalies(
    duration_secs: int | float | None,
    sleep_score: int | None,
    hrv: dict,
    rhr: dict,
    body_battery_morning: int | None,
) -> list[str]:
    """Flag readiness anomalies. Returns list of human-readable strings."""
    flags = []

    # HRV status not balanced
    if hrv and hrv.get("status") and hrv["status"] not in ("balanced", "unknown"):
        baseline = hrv.get("baseline_ms")
        value = hrv.get("value_ms")
        if baseline and value and baseline > 0:
            pct = round((value - baseline) / baseline * 100)
            flags.append(f"HRV {hrv['status']} ({pct:+d}% vs baseline)")
        else:
            flags.append(f"HRV {hrv['status']}")

    # Sleep score < 70
    if sleep_score is not None and sleep_score < 70:
        flags.append(f"Sleep score low ({sleep_score}/100)")

    # Sleep duration < 6h
    if duration_secs is not None and duration_secs < 6 * 3600:
        dur_str = _format_duration(duration_secs)
        flags.append(f"Short sleep ({dur_str})")

    # Resting HR elevated
    if rhr and rhr.get("value") and rhr.get("baseline"):
        delta = rhr["value"] - rhr["baseline"]
        if delta > 5:
            flags.append(f"Resting HR elevated (+{delta} bpm vs baseline)")

    # Body battery low
    if body_battery_morning is not None and body_battery_morning < 50:
        flags.append(f"Body battery low ({body_battery_morning})")

    return flags


def fetch_garmin_readiness(
    target_date: date | None = None,
    max_retries: int = 5,
    retry_delay: int = 30,
) -> dict | None:
    """Fetch last night's readiness data from Garmin Connect.

    Retries up to max_retries times with retry_delay seconds between attempts
    to handle Garmin sync lag (watch → phone → cloud).

    Returns shaped dict (see _shape()) or None on failure.
    """
    target = target_date or date.today()
    date_str = target.isoformat()

    client = _get_client()
    if not client:
        return None

    for attempt in range(max_retries):
        try:
            raw = _fetch_once(client, date_str)
            if raw:
                shaped = _shape(raw)
                if shaped.get("sleep", {}).get("duration"):
                    logger.info("Garmin readiness fetched for %s.", date_str)
                    return shaped
        except Exception as e:
            logger.warning("Garmin fetch error (attempt %d): %s", attempt + 1, e)

        if attempt < max_retries - 1:
            logger.info(
                "Garmin sync not ready (attempt %d/%d), waiting %ds...",
                attempt + 1, max_retries, retry_delay,
            )
            time.sleep(retry_delay)

    logger.warning("Garmin data unavailable after %d retries — skipping Body section.", max_retries)
    return None


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    from dotenv import load_dotenv

    load_dotenv(AGENT_ROOT / ".env")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    # Quick test with 1 retry (no waiting for standalone check)
    result = fetch_garmin_readiness(max_retries=1)
    if result:
        print(json.dumps(result, indent=2, default=str))
    else:
        print("No Garmin data available.")
