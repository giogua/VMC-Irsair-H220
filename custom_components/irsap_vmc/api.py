"""Async client for the embedded web interface of Irsap Irsair VMC units.

The unit exposes an old-style HTML interface (no JSON API):

* The home page is a frameset of tiny pages (``iftemp_e.html``,
  ``ifspeed_sp.html``...), each one showing a single value.  Reading these
  pages has no side effects.
* Commands are HTML forms with image buttons, posted back to the same page
  (e.g. ``inc0001.x=5&inc0001.y=5`` to ``ifspeed_sp.html``).  The response
  already contains the updated value.
* The "Menu" section mirrors the physical display: navigating it changes a
  server-side cursor.  ``menu.html`` (GET) returns the page the cursor is on,
  links are context-dependent (``cmd_selPPXXmenu.html``) and must therefore
  always be taken from the last response.  After every menu operation the
  client brings the cursor back to the home page.

This module has no Home Assistant dependency so it can be tested standalone.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10

# Season values as shown by the unit, in "dec -> inc" order.
SEASON_WINTER = "Inverno"
SEASON_SUMMER = "Estate"
SEASONS = (SEASON_WINTER, SEASON_SUMMER)

# Minimum delay between two consecutive season changes (requested by the owner).
SEASON_CHANGE_MIN_INTERVAL = 5.0

# Home page widgets.
PAGE_TEMP_OUTDOOR = "iftemp_e.html"
PAGE_TEMP_EXTRACT = "iftemp_r.html"
PAGE_TEMP_EXHAUST = "iftemp_x.html"
PAGE_TEMP_SUPPLY = "iftemp_i.html"
PAGE_SPEED = "ifspeed_sp.html"
PAGE_SETPOINT = "iftemp_sp.html"
PAGE_TIMER = "iftimer.html"
PAGE_TIMER_VALUE = "iftimer_value.html"
PAGE_ALARMS_TEXT = "ifalarms.html"
PAGE_BYPASS_ICON = "if5523.html"
PAGE_ALARM_ICON = "if7834.html"
PAGE_FAN_A_ICON = "ifab45.html"
PAGE_FAN_B_ICON = "if4545.html"

PAGE_MENU = "menu.html"

# Button suffixes per widget.
SPEED_ID = "0001"
TIMER_ID = "0002"
SETPOINT_ID = "0003"
SEASON_ID = "0801"

# (small, big) step of the +/- and ++/-- buttons, as observed on the unit.
SPEED_STEPS = (1.0, 10.0)
SETPOINT_STEPS = (0.2, 2.0)

MAX_STEPS = 120


class IrsapVmcError(Exception):
    """Generic error talking to the unit."""


class IrsapVmcConnectionError(IrsapVmcError):
    """The unit cannot be reached."""


class IrsapVmcNavigationError(IrsapVmcError):
    """The menu cursor ended up somewhere unexpected."""


# --------------------------------------------------------------------------
# HTML parsing
# --------------------------------------------------------------------------


@dataclass
class Page:
    """Relevant content of a page served by the unit."""

    text: str = ""
    links: dict[str, str] = field(default_factory=dict)
    inputs: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    frames: list[str] = field(default_factory=list)
    pre: list[str] = field(default_factory=list)

    @property
    def is_home(self) -> bool:
        """True when this is the home (frameset) page."""
        return bool(self.frames)

    @property
    def breadcrumb(self) -> str:
        """Last element of the "Home > Menu > X" breadcrumb ('' if none).

        The page text is "Home > Menu > Parametri" followed by the page
        content (which always comes from <pre> blocks), e.g.
        "Home > Menu > ParametriStagione Estate".
        """
        if not self.text.startswith("Home >"):
            return ""
        last = self.text.split(">")[-1].strip()
        if self.pre:
            idx = last.find(self.pre[0])
            if idx >= 0:
                last = last[:idx]
        # The main menu lists its entries (as links) right after "Menu".
        if "Parametri" in self.links and last.startswith("Menu"):
            return "Menu"
        return last.strip()

    def input_starting(self, prefix: str) -> str | None:
        """First input name starting with prefix."""
        return next((name for name in self.inputs if name.startswith(prefix)), None)


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.page = Page()
        self._text: list[str] = []
        self._link_href: str | None = None
        self._link_text: list[str] = []
        self._in_pre = False
        self._pre: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        if tag in ("script", "style", "title"):
            self._skip += 1
        elif tag == "a":
            self._link_href = a.get("href", "")
            self._link_text = []
        elif tag == "input" and a.get("name"):
            self.page.inputs.append(a["name"])
        elif tag == "img" and a.get("src"):
            self.page.images.append(a["src"])
        elif tag in ("iframe", "frame") and a.get("src"):
            self.page.frames.append(a["src"])
        elif tag == "pre":
            self._in_pre = True
            self._pre = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "title"):
            self._skip = max(0, self._skip - 1)
        elif tag == "a" and self._link_href is not None:
            text = " ".join("".join(self._link_text).split())
            if text:
                self.page.links[text] = self._link_href
            self._link_href = None
        elif tag == "pre" and self._in_pre:
            value = " ".join("".join(self._pre).split())
            if value:
                self.page.pre.append(value)
            self._in_pre = False

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        self._text.append(data)
        if self._link_href is not None:
            self._link_text.append(data)
        if self._in_pre:
            self._pre.append(data)

    def close(self) -> None:
        super().close()
        self.page.text = " ".join("".join(self._text).split())


def parse_page(html: str) -> Page:
    """Parse a page served by the unit."""
    parser = _Parser()
    parser.feed(html)
    parser.close()
    return parser.page


_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def parse_number(text: str) -> float | None:
    """Return the first number found in text, if any."""
    match = _NUM_RE.search(text or "")
    return float(match.group()) if match else None


_TIMER_RE = re.compile(r"(\d+)[.:](\d{1,2})[.:](\d{1,2})")


def parse_timer(text: str) -> int | None:
    """Parse the boost countdown ("H.MM.SS") into seconds; None if idle."""
    match = _TIMER_RE.search(text or "")
    if not match:
        return None
    hours, minutes, seconds = (int(g) for g in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def icon_is_on(page: Page) -> bool | None:
    """Return the on/off state encoded in a status icon file name."""
    for src in page.images:
        name = src.lower().rsplit("/", 1)[-1]
        if "_on" in name:
            return True
        if "_off" in name:
            return False
    return None


_STATUS_NUM_RE = re.compile(r"^(?P<label>.+?)\s*(?P<value>-?\d+(?:\.\d+)?)$")
_STATUS_TXT_RE = re.compile(r"^(?P<label>.+?)\s+(?P<value>\S+)$")

# Map of normalised "Stato" labels -> keys.
STATUS_LABELS = {
    "te(esterna)": "temp_outdoor",
    "tr(ripresa)": "temp_extract",
    "tx(espulsa)": "temp_exhaust",
    "ti(ingr.)": "temp_supply",
    "antig.batt.": "antifreeze",
    "vent.ingr.": "supply_fan_rpm",
    "venti.remoto": "supply_fan_remote",
    "vent.estr.": "exhaust_fan_rpm",
    "vente.remoto": "exhaust_fan_remote",
    "orevent.": "fan_hours",
    "bypass": "bypass",
}


def parse_status_line(line: str) -> tuple[str, str | float | bool] | None:
    """Parse a line of the "Stato" menu, e.g. ``Vent.Ingr.  1800``."""
    line = line.strip()
    match = _STATUS_NUM_RE.match(line) or _STATUS_TXT_RE.match(line)
    if not match:
        return None
    label = re.sub(r"\s+", "", match.group("label")).lower()
    key = STATUS_LABELS.get(label, label)
    raw = match.group("value")
    value: str | float | bool
    if raw.lower() == "on":
        value = True
    elif raw.lower() == "off":
        value = False
    else:
        num = parse_number(raw)
        value = num if num is not None and _STATUS_NUM_RE.match(line) else raw
    return key, value


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------


@dataclass
class VmcData:
    """Snapshot of the unit state."""

    temp_outdoor: float | None = None
    temp_extract: float | None = None
    temp_exhaust: float | None = None
    temp_supply: float | None = None
    speed: float | None = None
    speed_raw: str = ""
    setpoint: float | None = None
    boost_remaining: int = 0  # seconds, 0 when the boost is not running
    bypass: bool | None = None
    alarm: bool | None = None
    alarm_text: str = ""
    fan_a: bool | None = None
    fan_b: bool | None = None
    season: str | None = None
    status: dict[str, Any] = field(default_factory=dict)
    status_updated: float | None = None

    @property
    def is_on(self) -> bool | None:
        """Unit on: the speed widget shows "Off" when switched off."""
        if not self.speed_raw:
            return None
        return self.speed_raw.strip().lower() != "off"

    @property
    def boost_active(self) -> bool:
        """True while the boost countdown is running."""
        return self.boost_remaining > 0

    @property
    def efficiency(self) -> float | None:
        """Heat recovery (supply side) efficiency, in %."""
        te, tr, ti = self.temp_outdoor, self.temp_extract, self.temp_supply
        if te is None or tr is None or ti is None:
            return None
        delta = tr - te
        if abs(delta) < 2.0:
            # Too small a difference: the value would be pure noise.
            return None
        eff = (ti - te) / delta * 100.0
        return round(max(0.0, min(100.0, eff)), 1)


# --------------------------------------------------------------------------
# Client
# --------------------------------------------------------------------------


class IrsapVmcClient:
    """Serialised client for one unit."""

    def __init__(
        self,
        host: str,
        session: aiohttp.ClientSession,
        timeout: float = DEFAULT_TIMEOUT,
        season_change_interval: float = SEASON_CHANGE_MIN_INTERVAL,
    ) -> None:
        host = host.strip().rstrip("/")
        if not host.startswith(("http://", "https://")):
            host = f"http://{host}"
        self.base_url = host
        self._session = session
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._lock = asyncio.Lock()
        self._season_interval = season_change_interval
        self._last_season_change = 0.0

    # ---------------------------------------------------------------- HTTP

    async def _request(self, method: str, page: str, data: str | None = None) -> Page:
        url = f"{self.base_url}/{page.lstrip('/')}"
        headers = (
            {"Content-Type": "application/x-www-form-urlencoded"} if data else None
        )
        try:
            async with self._session.request(
                method, url, data=data, headers=headers, timeout=self._timeout
            ) as resp:
                resp.raise_for_status()
                html = await resp.text(errors="replace")
        except (aiohttp.ClientError, TimeoutError) as err:
            raise IrsapVmcConnectionError(f"{method} {url}: {err}") from err
        return parse_page(html)

    async def _get(self, page: str) -> Page:
        return await self._request("GET", page)

    async def _press(self, page: str, button: str) -> Page:
        """Simulate a click on an image button of a form."""
        _LOGGER.debug("Pressing %s on %s", button, page)
        return await self._request("POST", page, f"{button}.x=5&{button}.y=5")

    # ------------------------------------------------------------ reading

    async def async_validate(self) -> None:
        """Check that host is an Irsap VMC web interface."""
        async with self._lock:
            page = await self._get(PAGE_TEMP_OUTDOOR)
        if not re.search(r"\bTe\b", page.text):
            raise IrsapVmcError("Unexpected content: not an Irsap VMC interface?")

    async def async_get_data(self, previous: VmcData | None = None) -> VmcData:
        """Read the home page widgets (no side effects)."""
        data = VmcData()
        if previous is not None:
            data.season = previous.season
            data.status = previous.status
            data.status_updated = previous.status_updated
        async with self._lock:
            pages: dict[str, Page] = {}
            for page in (
                PAGE_TEMP_OUTDOOR,
                PAGE_TEMP_EXTRACT,
                PAGE_TEMP_EXHAUST,
                PAGE_TEMP_SUPPLY,
                PAGE_SPEED,
                PAGE_SETPOINT,
                PAGE_TIMER_VALUE,
                PAGE_ALARMS_TEXT,
                PAGE_BYPASS_ICON,
                PAGE_ALARM_ICON,
                PAGE_FAN_A_ICON,
                PAGE_FAN_B_ICON,
            ):
                pages[page] = await self._get(page)

        def _temp(page: str) -> float | None:
            return parse_number(pages[page].text.split(" ", 1)[-1])

        data.temp_outdoor = _temp(PAGE_TEMP_OUTDOOR)
        data.temp_extract = _temp(PAGE_TEMP_EXTRACT)
        data.temp_exhaust = _temp(PAGE_TEMP_EXHAUST)
        data.temp_supply = _temp(PAGE_TEMP_SUPPLY)
        data.speed_raw = pages[PAGE_SPEED].text
        data.speed = parse_number(data.speed_raw)
        data.setpoint = parse_number(pages[PAGE_SETPOINT].text)
        data.boost_remaining = parse_timer(pages[PAGE_TIMER_VALUE].text) or 0
        data.alarm_text = pages[PAGE_ALARMS_TEXT].text
        data.bypass = icon_is_on(pages[PAGE_BYPASS_ICON])
        data.alarm = icon_is_on(pages[PAGE_ALARM_ICON])
        if data.alarm is None:
            data.alarm = bool(data.alarm_text)
        data.fan_a = icon_is_on(pages[PAGE_FAN_A_ICON])
        data.fan_b = icon_is_on(pages[PAGE_FAN_B_ICON])
        return data

    # ------------------------------------------------------- menu cursor

    async def _go_home(self, page: Page | None = None) -> Page:
        """Bring the menu cursor back to the home page."""
        page = page or await self._get(PAGE_MENU)
        for _ in range(6):
            if page.is_home:
                return page
            link = page.links.get("Home")
            if not link:
                raise IrsapVmcNavigationError(
                    f"No 'Home' link on page: {page.text[:60]!r}"
                )
            page = await self._get(link)
        raise IrsapVmcNavigationError("Unable to reach the home page")

    async def _open_menu_section(self, section: str) -> Page:
        """Navigate Home > Menu > section and return that page."""
        home = await self._go_home()
        menu_link = home.links.get("Menu")
        if not menu_link:
            raise IrsapVmcNavigationError("No 'Menu' link on home page")
        menu = await self._get(menu_link)
        link = menu.links.get(section)
        if not link:
            raise IrsapVmcNavigationError(f"Menu section {section!r} not found")
        page = await self._get(link)
        if page.breadcrumb != section:
            raise IrsapVmcNavigationError(
                f"Expected section {section!r}, got {page.breadcrumb!r}"
            )
        return page

    async def async_get_menu_data(self) -> tuple[str | None, dict[str, Any]]:
        """Read "Parametri > Stagione" and the full "Stato" list.

        This moves the server-side menu cursor and restores it to home.
        """
        async with self._lock:
            try:
                season = self._season_from(await self._open_menu_section("Parametri"))
                status = await self._read_status_locked()
            finally:
                await self._safe_go_home()
        return season, status

    async def _read_status_locked(self) -> dict[str, Any]:
        page = await self._open_menu_section("Stato")
        lines: list[str] = []
        for _ in range(40):
            for line in page.pre:
                if line not in lines:
                    lines.append(line)
            button = page.input_starting("sdw")
            if not button:
                break
            page = await self._press(PAGE_MENU, button)
        status: dict[str, Any] = {}
        for line in lines:
            parsed = parse_status_line(line)
            if parsed:
                status[parsed[0]] = parsed[1]
        return status

    async def _safe_go_home(self) -> None:
        try:
            await self._go_home()
        except IrsapVmcError as err:  # pragma: no cover - best effort
            _LOGGER.warning("Unable to bring the VMC menu back home: %s", err)

    @staticmethod
    def _season_from(page: Page) -> str | None:
        for line in page.pre:
            if line.lower().startswith("stagione"):
                value = line.split(None, 1)[-1].strip()
                return value
        return None

    # ------------------------------------------------------------ commands

    async def async_press(self, page: str, button: str) -> Page:
        """Press a single button on a home widget."""
        async with self._lock:
            return await self._press(page, button)

    async def async_toggle_power(self) -> None:
        """Toggle the unit on/off."""
        await self.async_press(PAGE_SPEED, f"tgl{SPEED_ID}")

    # Boost ("timer"): maximum ventilation for a given time, then back to the
    # previous speed.  Observed behaviour: when idle the value page is empty;
    # any start (toggle, + or ++) starts a 10 minute countdown shown as
    # "H.MM.SS"; +/- change it by 1 minute, ++/-- by 10 minutes; the toggle
    # stops it.

    async def _timer_remaining(self) -> int:
        return parse_timer((await self._get(PAGE_TIMER_VALUE)).text) or 0

    async def async_start_boost(self, minutes: int | None = None) -> int:
        """Start (or adjust) the boost; returns the remaining seconds."""
        async with self._lock:
            remaining = await self._timer_remaining()
            if remaining <= 0:
                await self._press(PAGE_TIMER, f"tgl{TIMER_ID}")
                remaining = await self._timer_remaining()
                if remaining <= 0:
                    raise IrsapVmcError("Boost did not start")
            if minutes is None:
                return remaining
            target = max(1, int(minutes))
            for _ in range(MAX_STEPS):
                current = round(remaining / 60)
                diff = target - current
                if diff == 0:
                    break
                if abs(diff) >= 10:
                    prefix = "iic" if diff > 0 else "ddc"
                else:
                    prefix = "inc" if diff > 0 else "dec"
                await self._press(PAGE_TIMER, f"{prefix}{TIMER_ID}")
                new = await self._timer_remaining()
                if new <= 0:
                    # Went below the minimum and stopped: restart and stop
                    # adjusting downwards.
                    await self._press(PAGE_TIMER, f"tgl{TIMER_ID}")
                    remaining = await self._timer_remaining()
                    break
                if round(new / 60) == current:
                    remaining = new
                    break  # limit reached
                remaining = new
            return remaining

    async def async_stop_boost(self) -> None:
        """Stop the boost if running."""
        async with self._lock:
            if await self._timer_remaining() > 0:
                await self._press(PAGE_TIMER, f"tgl{TIMER_ID}")

    async def async_set_speed(self, target: float) -> float | None:
        """Set fan speed (%) by pressing +/- until target is reached."""
        return await self._set_by_steps(PAGE_SPEED, SPEED_ID, target, SPEED_STEPS)

    async def async_set_setpoint(self, target: float) -> float | None:
        """Set the temperature set point by pressing +/- until reached."""
        return await self._set_by_steps(
            PAGE_SETPOINT, SETPOINT_ID, target, SETPOINT_STEPS
        )

    async def _set_by_steps(
        self, page: str, wid: str, target: float, steps: tuple[float, float]
    ) -> float | None:
        """Press +/- (small step) and ++/-- (big step) until target is reached.

        Every response already contains the new value, so each press is
        verified; the loop stops early if the unit stops moving (limit).
        """
        small, big = steps
        async with self._lock:
            current = parse_number((await self._get(page)).text)
            if current is None:
                raise IrsapVmcError("The unit is off or the value is not readable")
            for _ in range(MAX_STEPS):
                diff = target - current
                if abs(diff) < small / 2:
                    break
                up = diff > 0
                use_big = abs(diff) >= big - small / 2
                prefix = (
                    ("iic" if up else "ddc") if use_big else ("inc" if up else "dec")
                )
                new = parse_number((await self._press(page, f"{prefix}{wid}")).text)
                if new is None:
                    raise IrsapVmcError(f"Cannot read value from {page} after command")
                if abs(new - current) < small / 2:
                    break  # limit reached
                current = new
            return current

    async def async_set_season(self, season: str) -> str | None:
        """Set "Parametri > Stagione" (Inverno / Estate)."""
        if season not in SEASONS:
            raise ValueError(f"Invalid season {season!r}")
        async with self._lock:
            try:
                page = await self._open_menu_section("Parametri")
                current = self._season_from(page)
                for _ in range(len(SEASONS)):
                    if current == season:
                        break
                    wait = self._season_interval - (
                        time.monotonic() - self._last_season_change
                    )
                    if wait > 0:
                        await asyncio.sleep(wait)
                    button = (
                        "inc"
                        if SEASONS.index(season) > SEASONS.index(current or season)
                        else "dec"
                    )
                    page = await self._press(PAGE_MENU, f"{button}{SEASON_ID}")
                    self._last_season_change = time.monotonic()
                    if page.breadcrumb != "Parametri":
                        raise IrsapVmcNavigationError(
                            "Lost the 'Parametri' page while changing season"
                        )
                    new = self._season_from(page)
                    if new == current:
                        break
                    current = new
                return current
            finally:
                await self._safe_go_home()
