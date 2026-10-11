"""Fake Irsap VMC web server reproducing the observed behaviour of the unit.

HTML snippets mirror the pages served by a real Irsair H 220 (firmware web
interface), including the server-side menu cursor.
"""

from __future__ import annotations

import re
import time

from aiohttp import web

HEAD = '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN"><html><head><title>{t}</title><!----></head><body>'
TAIL = "</body></html>"

FRAMES = [
    "ifalarms.html",
    "ifspeed_sp.html",
    "iftemp_e.html",
    "if4423.html",
    "if5523.html",
    "iftemp_r.html",
    "iftemp_x.html",
    "if7834.html",
    "iftemp_i.html",
    "if4545.html",
    "ifab45.html",
    "ifcc45.html",
    "ifdd45.html",
    "iftemp_on.html",
    "iftimer.html",
    "if9977.html",
    "iftemp_sp.html",
]

MENU_ITEMS = [
    "Stato",
    "Allarmi",
    "Programma",
    "Orologio",
    "Parametri",
    "Installatore",
    "Fabbrica",
]
PAGE_IDS = {
    "home": "00",
    "menu": "02",
    "Stato": "0D",
    "Parametri": "08",
    "Allarmi": "03",
    "Programma": "04",
    "Orologio": "05",
    "Installatore": "06",
    "Fabbrica": "07",
}


def _btns(wid: str, toggle: bool) -> str:
    names = ["dec", "ddc"] + (["tgl"] if toggle else []) + ["iic", "inc"]
    imgs = {
        "dec": "push_dw.gif",
        "ddc": "push_dwdw.gif",
        "tgl": "push_on_off.gif",
        "iic": "push_upup.gif",
        "inc": "push_up.gif",
    }
    return "".join(
        f'<input type="image" name="{n}{wid}" src="{imgs[n]}">' for n in names
    )


class FakeVmc:
    """In-memory state + aiohttp app."""

    def __init__(self) -> None:
        self.temps = {"e": 22.7, "r": 23.3, "x": 22.7, "i": 23.8}
        self.on = True
        self.speed = 40
        self.setpoint = 22.0
        self.season = 1  # 0 = Inverno, 1 = Estate
        self.boost_end: float | None = None
        self.bypass = False
        self.alarm = False
        self.cursor = "home"
        self.stato_offset = 0
        self.season_changes: list[float] = []
        self.requests: list[str] = []
        self.status_lines = [
            "Te(Esterna)022.7",
            "Tr(Ripresa)023.3",
            "Tx(Espulsa)022.8",
            "Ti(Ingr.)  023.9",
            "Antig.Batt.  Off",
            "Vent.Ingr.  1798",
            "VentI.Remoto Off",
            "Vent.Estr.  1736",
            "VentE.Remoto Off",
            "Ore Vent.  13644",
            "Bypass       Off",
        ]

    # ------------------------------------------------------------ pages
    def home(self) -> str:
        frames = "".join(f'<iframe src="{f}"></iframe>' for f in FRAMES)
        return (
            HEAD.format(t="Home") + '<form action="index.html" method="post">'
            '<input type="submit" name="ar10000" value="Refresh On"></form>'
            "<p>To get a coplete Home page click on the icon close the menu word or enable iframes!</p>"
            f'<a href="cmd_sel0000menu.html">Menu</a>{frames}' + TAIL
        )

    def menu_page(self) -> str:
        pid = PAGE_IDS[self.cursor]
        if self.cursor == "menu":
            links = "".join(
                f'<a href="cmd_sel02{i + 1:02X}menu.html">{name}</a>'
                for i, name in enumerate(MENU_ITEMS)
            )
            return (
                HEAD.format(t="Menu")
                + '<img src="logo.gif"><a href="cmd_sel0280menu.html">Home</a> &gt; Menu'
                + links
                + TAIL
            )
        nav = (
            f'<img src="logo.gif"><a href="cmd_sel{pid}80menu.html">Home</a> &gt; '
            f'<a href="cmd_sel{pid}82menu.html">Menu</a> &gt; {self.cursor}'
        )
        if self.cursor == "Parametri":
            body = (
                f"<pre>Stagione  {['Inverno', 'Estate'][self.season]}</pre>"
                f'<form action="menu.html" method="post">{_btns("0801", False)}</form>'
            )
        elif self.cursor == "Stato":
            win = self.status_lines[self.stato_offset : self.stato_offset + 8]
            body = "".join(f"<pre>{line}</pre>" for line in win)
            code = f"0D{8 + self.stato_offset:02X}"
            btns = ""
            if self.stato_offset > 0:
                btns += f'<input type="image" name="sup{code}" src="push_up.gif"><input type="image" name="suu{code}" src="push_upup.gif">'
            if self.stato_offset + 8 < len(self.status_lines):
                btns += f'<input type="image" name="sdw{code}" src="push_dw.gif"><input type="image" name="sdd{code}" src="push_dwdw.gif">'
            body = (
                '<form action="menu.html" method="post"><input type="submit" name="ar10D00" value="Refresh On"></form>'
                + body
                + f'<form action="menu.html" method="post">{btns}</form>'
            )
        else:
            body = "<pre>...</pre>"
        return HEAD.format(t="Menu") + nav + body + TAIL

    def current(self) -> str:
        return self.home() if self.cursor == "home" else self.menu_page()

    def boost_remaining(self) -> int:
        if self.boost_end is None:
            return 0
        rem = int(self.boost_end - time.monotonic())
        if rem <= 0:
            self.boost_end = None
            return 0
        return rem

    def widget(self, name: str) -> str:
        t = name.removesuffix(".html")
        if t.startswith("iftemp_") and t[-1] in self.temps:
            v = self.temps[t[-1]]
            label = f"T{t[-1]} {v:05.1f}"
            inner = (
                f"<h3>{label}</h3>"
                if t[-1] in "ex"
                else f'<div style="text-align:right"><h3>{label}</h3></div>'
            )
            return HEAD.format(t=t) + inner + TAIL
        if t == "ifspeed_sp":
            val = f"{self.speed:03d}%" if self.on else "Off"
            return (
                HEAD.format(t=t)
                + f'<form action="ifspeed_sp.html" method="post"><table><tr><td><h3>{val}</h3></td><td>'
                + _btns("0001", True)
                + "</td></tr></table></form>"
                + TAIL
            )
        if t == "iftemp_sp":
            return (
                HEAD.format(t=t)
                + f'<form action="iftemp_sp.html" method="post"><h3>{self.setpoint:.1f}</h3>'
                + _btns("0003", False)
                + "</form>"
                + TAIL
            )
        if t == "iftimer":
            return (
                HEAD.format(t=t)
                + '<table><tr><td><form action="iftimer.html" method="post">'
                + _btns("0002", True)
                + '</form></td><td><iframe src="iftimer_value.html"></iframe></td></tr></table>'
                + TAIL
            )
        if t == "iftimer_value":
            rem = self.boost_remaining()
            txt = (
                f"<h3>{rem // 3600:02d}.{rem % 3600 // 60:02d}.{rem % 60:02d}</h3>"
                if rem
                else ""
            )
            return HEAD.format(t=t) + txt + TAIL
        if t == "if5523":
            return (
                HEAD.format(t=t)
                + f'<img src="img5523_bypass_{"on" if self.bypass else "off"}.gif">'
                + TAIL
            )
        if t == "if7834":
            return (
                HEAD.format(t=t)
                + f'<img src="img7834_alarms_{"on" if self.alarm else "off"}.gif">'
                + TAIL
            )
        if t == "ifalarms":
            return (
                HEAD.format(t=t) + ("<h3>A01 Filtri</h3>" if self.alarm else "") + TAIL
            )
        if t in ("ifab45", "if4545"):
            return HEAD.format(t=t) + f'<img src="img{t[2:]}_on_2.gif">' + TAIL
        return HEAD.format(t=t) + '<img src="img_white.gif">' + TAIL

    # ------------------------------------------------------------ commands
    def press(self, page: str, button: str) -> None:
        op, wid = button[:3], button[3:]
        if page == "ifspeed_sp" and wid == "0001":
            if op == "tgl":
                self.on = not self.on
            elif self.on:
                delta = {"inc": 1, "dec": -1, "iic": 10, "ddc": -10}[op]
                self.speed = max(20, min(100, self.speed + delta))
        elif page == "iftemp_sp" and wid == "0003":
            delta = {"inc": 0.2, "dec": -0.2, "iic": 2, "ddc": -2}[op]
            self.setpoint = round(max(16.0, min(28.0, self.setpoint + delta)), 1)
        elif page == "iftimer" and wid == "0002":
            rem = self.boost_remaining()
            if op == "tgl":
                self.boost_end = None if rem else time.monotonic() + 600
            elif not rem:
                if op in ("inc", "iic"):
                    self.boost_end = time.monotonic() + 600
            else:
                delta = {"inc": 60, "dec": -60, "iic": 600, "ddc": -600}[op]
                new = min(rem + delta, 4 * 3600)
                self.boost_end = time.monotonic() + new if new > 0 else None
        elif page == "menu":
            if self.cursor == "Parametri" and wid == "0801":
                old = self.season
                self.season = max(
                    0, min(1, self.season + (1 if op in ("inc", "iic") else -1))
                )
                if self.season != old:
                    self.season_changes.append(time.monotonic())
            elif self.cursor == "Stato" and wid == f"0D{8 + self.stato_offset:02X}":
                if op in ("sdw", "sdd") and self.stato_offset + 8 < len(
                    self.status_lines
                ):
                    self.stato_offset += 1
                if op in ("sup", "suu") and self.stato_offset > 0:
                    self.stato_offset -= 1

    def navigate(self, code: str) -> None:
        pid, action = code[:2], code[2:]
        if pid != PAGE_IDS[self.cursor]:
            return  # stale link: the unit ignores it
        if action == "80":
            self.cursor = "home"
        elif action == "82" or (self.cursor == "home" and action == "00"):
            self.cursor = "menu"
        elif self.cursor == "menu":
            idx = int(action, 16) - 1
            if 0 <= idx < len(MENU_ITEMS):
                self.cursor = MENU_ITEMS[idx]
                self.stato_offset = 0

    # ------------------------------------------------------------ aiohttp
    async def handler(self, request: web.Request) -> web.Response:
        name = request.match_info["name"]
        self.requests.append(f"{request.method} {name}")
        if request.method == "POST":
            form = await request.post()
            button = next((k[:-2] for k in form if k.endswith(".x")), None)
            if button:
                self.press(name.removesuffix(".html"), button)
        if m := re.fullmatch(r"cmd_sel([0-9A-F]{4})menu\.html", name):
            self.navigate(m.group(1))
            return web.Response(text=self.current(), content_type="text/html")
        if name in ("menu.html",):
            return web.Response(text=self.current(), content_type="text/html")
        if name in ("", "index.html"):
            return web.Response(text=self.home(), content_type="text/html")
        return web.Response(text=self.widget(name), content_type="text/html")

    def app(self) -> web.Application:
        app = web.Application()
        app.router.add_route("*", "/{name:.*}", self.handler)
        return app
