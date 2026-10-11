"""Operator time-zone setting and the pure date/time formatters (M28 F1 L1).

A leaf module: stdlib, pydantic, ``tzlocal`` and ``tzdata`` only. The database
repository is imported lazily inside the async load/save functions, and nothing
from ``the_one.agent``, ``the_one.tools`` or ``the_one.interfaces`` is imported
at module level (pinned by a test).

**Zone names come from the tzdata package, never the host.** ``zone_names()``
reads ``tzdata/zoneinfo/tzdata.zi`` once; a name is accepted only if it is in
that fixed set, so an operator-supplied string is never used as a path
(``localtime``, ``posixrules`` and ``../x`` are all refused).

**Formatters are locale- and platform-neutral.** No ``strftime`` (``%-d``,
``%A``, ``%p`` differ by platform and locale): f-strings over datetime fields,
fixed English weekday and month tables, and the offset built by hand as
``UTC+05:30`` (ASCII hyphen-minus).

**Seams.** Code here calls ``utcnow()`` and ``detect_system_zone()`` through the
module namespace at call time, so tests can monkeypatch both.
"""

from __future__ import annotations

import functools
import importlib.resources
import logging
import re
import time
import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any, Literal
from zoneinfo import ZoneInfo

import tzlocal
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

logger = logging.getLogger(__name__)

CURRENT_TIME_TOOL_NAME = "current_time"
SETTING_KEY = "time_zone"

# Stable messages the model's validators raise; the PUT route classifies on them.
ERR_ZONE_UNKNOWN = "zone_unknown"
ERR_ZONE_REQUIRED = "zone_required"

_WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)
_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

_RELOAD_INTERVAL_S = 60.0
_last_reload: float | None = None


# ── Zone names (tzdata package, read once) ────────────────────────────────


@functools.lru_cache(maxsize=1)
def _parse_tzdata_zi() -> tuple[tuple[str, ...], frozenset[str]]:
    text = (
        importlib.resources.files("tzdata")
        .joinpath("zoneinfo")
        .joinpath("tzdata.zi")
        .read_text(encoding="utf-8")
    )
    canonical: set[str] = set()
    links: set[str] = set()
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "Z":
            canonical.add(parts[1])
        elif len(parts) >= 3 and parts[0] == "L":
            links.add(parts[2])
    return tuple(sorted(canonical)), frozenset(canonical | links)


def canonical_zones() -> list[str]:
    """Sorted canonical (``Z``) zone names from tzdata."""
    return list(_parse_tzdata_zi()[0])


def zone_names() -> frozenset[str]:
    """Every zone name tzdata knows: canonical names plus link aliases."""
    return _parse_tzdata_zi()[1]


def is_known_zone(key: Any) -> bool:
    """True only for a string that is a tzdata zone or link name."""
    return isinstance(key, str) and key in zone_names()


def utcnow() -> datetime:
    """The current instant, aware, UTC. A test seam."""
    return datetime.now(timezone.utc)


def detect_system_zone() -> str | None:
    """The host's IANA zone name, or None when it cannot be determined.

    ``tzlocal`` caches its answer for the process; it is reloaded when the last
    reload is more than a minute old so a long-running app follows a host
    zone change.
    """
    global _last_reload
    try:
        now = time.monotonic()
        if _last_reload is None or now - _last_reload > _RELOAD_INTERVAL_S:
            _last_reload = now
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    tzlocal.reload_localzone()
            except Exception:  # noqa: BLE001 — freshness is best effort
                logger.debug("tzlocal reload failed", exc_info=True)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            name = tzlocal.get_localzone_name()
    except Exception:  # noqa: BLE001 — detection must never raise
        return None
    if isinstance(name, str) and name and is_known_zone(name):
        return name
    return None


# ── The setting ───────────────────────────────────────────────────────────


class TimeZoneSetting(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["system", "zone"] = "system"
    zone: str | None = None

    @field_validator("zone")
    @classmethod
    def _zone_is_known(cls, v: str | None) -> str | None:
        if v is not None and not is_known_zone(v):
            raise ValueError(ERR_ZONE_UNKNOWN)
        return v

    @model_validator(mode="after")
    def _zone_mode_needs_zone(self) -> TimeZoneSetting:
        if self.mode == "zone" and self.zone is None:
            raise ValueError(ERR_ZONE_REQUIRED)
        return self


@dataclass(frozen=True)
class EffectiveZone:
    key: str | None
    tzinfo: tzinfo


def _system_zone() -> EffectiveZone:
    name = detect_system_zone()
    if name:
        try:
            return EffectiveZone(name, ZoneInfo(name))
        except Exception:  # noqa: BLE001
            logger.warning("Detected system zone %r could not be loaded", name)
    local = datetime.now().astimezone()
    offset = local.utcoffset() or timedelta(0)
    abbr = local.tzname()
    return EffectiveZone(None, timezone(offset, abbr) if abbr else timezone(offset))


def resolve(setting: TimeZoneSetting) -> EffectiveZone:
    if setting.mode == "zone" and setting.zone:
        try:
            return EffectiveZone(setting.zone, ZoneInfo(setting.zone))
        except Exception:  # noqa: BLE001
            logger.warning(
                "Configured time zone %r could not be loaded; using the system zone", setting.zone
            )
    return _system_zone()


async def load_setting(conn) -> TimeZoneSetting:
    from the_one.db.repositories import AppMetadataRepository

    raw = await AppMetadataRepository(conn).get(SETTING_KEY)
    if raw is None:
        return TimeZoneSetting()
    try:
        return TimeZoneSetting.model_validate_json(raw)
    except Exception:  # noqa: BLE001 — a bad stored value falls back to default
        logger.warning("Stored time-zone setting is invalid; using the default")
        return TimeZoneSetting()


async def save_setting(conn, setting: TimeZoneSetting) -> None:
    from the_one.db.repositories import AppMetadataRepository

    await AppMetadataRepository(conn).set(SETTING_KEY, setting.model_dump_json())


async def load_effective_zone(conn=None) -> EffectiveZone:
    """Load the stored setting and resolve it. Never raises."""
    try:
        if conn is None:
            from the_one.db.connection import get_connection

            conn = await get_connection()
        return resolve(await load_setting(conn))
    except Exception:  # noqa: BLE001
        logger.warning("Could not load the time-zone setting; using the system zone", exc_info=True)
        return _system_zone()


# ── Formatters (pure, locale- and platform-neutral) ───────────────────────


def offset_label(local: datetime) -> str:
    """``UTC+05:30`` / ``UTC-07:00`` / ``UTC+00:00`` for an aware datetime."""
    delta = local.utcoffset() or timedelta(0)
    minutes = int(delta.total_seconds()) // 60
    sign = "-" if minutes < 0 else "+"
    minutes = abs(minutes)
    return f"UTC{sign}{minutes // 60:02d}:{minutes % 60:02d}"


def zone_label(eff: EffectiveZone, local: datetime) -> str:
    return eff.key if eff.key else f"system time zone, {offset_label(local)}"


_NUMERIC_ABBREVIATION = re.compile(r"^[+-]\d{2,4}$")


def _abbreviation(local: datetime) -> str:
    name = local.tzname()
    if not name or name.startswith("UTC+") or name.startswith("UTC-"):
        return ""
    if _NUMERIC_ABBREVIATION.match(name):
        return ""
    return name


def _clock(local: datetime) -> str:
    hour = local.hour % 12 or 12
    return f"{hour}:{local.minute:02d} {'AM' if local.hour < 12 else 'PM'}"


def _long_date(local: datetime) -> str:
    return f"{_WEEKDAYS[local.weekday()]}, {_MONTHS[local.month - 1]} {local.day}, {local.year}"


def tool_lines(now: datetime, eff: EffectiveZone) -> list[str]:
    local = now.astimezone(eff.tzinfo)
    abbr = _abbreviation(local)
    abbr_part = f" {abbr}" if abbr else ""
    return [
        f"{local.isoformat(timespec='seconds')} ({zone_label(eff, local)})",
        f"{_long_date(local)}, {_clock(local)}{abbr_part} ({offset_label(local)})",
    ]


def render_date_line(date_text: str, zone_text: str, *, tool_available: bool) -> str:
    if tool_available:
        return (
            f"Today is {date_text} ({zone_text}). This date is as of when this conversation "
            f"was last loaded. For the current date and time, call {CURRENT_TIME_TOOL_NAME}."
        )
    return f"Today is {date_text} ({zone_text}), as of when this conversation was last loaded."


def date_line(now: datetime, eff: EffectiveZone, *, tool_available: bool) -> str:
    local = now.astimezone(eff.tzinfo)
    return render_date_line(
        _long_date(local), zone_label(eff, local), tool_available=tool_available
    )


def clock_text(now: datetime, eff: EffectiveZone) -> str:
    return _clock(now.astimezone(eff.tzinfo))


def zone_rows(at: datetime) -> list[dict[str, str]]:
    """Picker rows for the canonical zones, sorted by region then city."""
    rows: list[dict[str, str]] = []
    for name in canonical_zones():
        if name == "Factory" or (name.startswith("Etc/") and name != "Etc/UTC"):
            continue
        try:
            local = at.astimezone(ZoneInfo(name))
        except Exception:  # noqa: BLE001 — skip a zone the host cannot load
            continue
        if name == "Etc/UTC":
            region, city = "UTC", "UTC"
        else:
            region = name.split("/", 1)[0]
            city = name.rsplit("/", 1)[-1].replace("_", " ")
        rows.append(
            {
                "zone": name,
                "region": region,
                "city": city,
                "offset": offset_label(local),
                "abbreviation": local.tzname() or "",
            }
        )
    rows.sort(key=lambda r: (r["region"], r["city"]))
    return rows
