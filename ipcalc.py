#!/usr/bin/env python3
"""
ipcalc — a terminal-UI IPv4/IPv6 subnet calculator (Textual front-end).

Three fields, top to bottom:
  • Address — 192.168.1.10/24 · 10.0.0.1 255.0.0.0 · 172.16.5.4 · 2001:db8::1/64
  • Split into /N — divide the network into equal /N subnets (a table).
  • VLSM host counts — e.g. "sales:50, eng:20, 10"; allocates right-sized
    subnets largest-first. Overrides Split when filled.

Tab moves between fields; results update as you type.
Keys: q/Esc quit · Ctrl+L clear · c copy current row/detail to clipboard.
"""

import shutil
import subprocess

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Footer, Header, Input, Select, Static

import ipcalc_core as core

MAX_ROWS = 4096   # cap rows rendered into the split table


def binary_text(ip, prefix):
    """Rich Text of an IPv4 address in binary, network vs host bits colored."""
    t = Text()
    bi = 0
    for ch in core.bits(ip):
        if ch == ".":
            t.append(".", style="dim")
        else:
            t.append(ch, style="bold yellow" if bi < prefix else "magenta")
            bi += 1
    return t


def detail_panel(iface):
    """A Rich renderable: the single-network detail grid."""
    rows, p = core.describe(iface)
    v6 = iface.version == 6
    grid = Table.grid(padding=(0, 3))
    for _ in range(3):
        grid.add_column(justify="left")
    for row in rows:
        if row is None:
            grid.add_row("", "", "")
            continue
        label, value, ip = row
        third = Text("") if (v6 or ip is None) else binary_text(ip, p)
        grid.add_row(Text(label, style="bold cyan"),
                     Text(value, style="bold green"), third)
    if v6:
        sub = Text("IPv6", style="dim")
    else:
        sub = Text.assemble(("network bits", "bold yellow"), "  ",
                            ("host bits", "magenta"))
    title = f"[b]Network detail[/b] · {'IPv6' if v6 else 'IPv4'}"
    return Panel(grid, title=title, subtitle=sub,
                 border_style="cyan", padding=(1, 2))


class IpCalc(App):
    CSS = """
    Screen { layout: vertical; }
    #form { height: auto; padding: 1 2 0 2; }
    .lbl { color: $text-muted; padding: 0 1; }
    Input { margin-bottom: 1; }
    Select { margin-bottom: 1; }
    #message { height: auto; padding: 0 2; color: $error; text-style: bold; }
    #detail { height: auto; padding: 0 2; }
    #summary { height: auto; padding: 0 2; color: $accent; text-style: bold; }
    DataTable { height: 1fr; margin: 1 2 0 2; }
    """

    BINDINGS = [
        ("escape", "quit", "Quit"),
        ("q", "quit", "Quit"),
        ("ctrl+l", "clear", "Clear"),
        ("c", "copy", "Copy"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical(id="form"):
            yield Static("Preset network (quick fill):", classes="lbl")
            yield Select([(lbl, val) for lbl, val in core.PRESETS],
                         prompt="Choose a predefined network…",
                         id="preset", allow_blank=True)
            yield Static("Address — IPv4/IPv6, CIDR or mask:", classes="lbl")
            yield Input(value="192.168.1.10/24", id="addr",
                        placeholder="e.g. 192.168.1.10/24 or 2001:db8::1/64")
            yield Static("Split into /N (equal subnets):", classes="lbl")
            yield Input(value="", id="split", placeholder="e.g. 26")
            yield Static("VLSM host counts (overrides split):", classes="lbl")
            yield Input(value="", id="vlsm",
                        placeholder="e.g. sales:50, eng:20, 10")
        yield Static("", id="message")
        yield Static(id="detail")
        yield Static("", id="summary")
        yield DataTable(id="subnets", zebra_stripes=True, cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "IP Subnet Calculator"
        self._cols = None
        self._copy_text = ""
        self.recompute()

    def on_input_changed(self, event: Input.Changed) -> None:
        self.recompute()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.value is not Select.BLANK:
            self.query_one("#addr", Input).value = event.value

    def action_clear(self) -> None:
        for wid in ("addr", "split", "vlsm"):
            self.query_one(f"#{wid}", Input).value = ""

    def action_copy(self) -> None:
        table = self.query_one("#subnets", DataTable)
        text = ""
        if table.display and table.row_count:
            row = table.get_row_at(table.cursor_row)
            text = "\t".join(str(c) for c in row)
        elif self.query_one("#detail", Static).display:
            text = self._copy_text
        if not text:
            self.notify("Nothing to copy", severity="warning")
            return
        if not shutil.which("wl-copy"):
            self.notify("wl-copy not found", severity="error")
            return
        try:
            subprocess.run(["wl-copy"], input=text.encode(), check=True)
            self.notify("Copied to clipboard")
        except Exception as exc:                          # noqa: BLE001
            self.notify(f"Copy failed: {exc}", severity="error")

    # ─────────────────────────── view helpers ───────────────────────────

    def _set_columns(self, cols):
        table = self.query_one("#subnets", DataTable)
        if self._cols != cols:
            table.clear(columns=True)
            table.add_columns(*cols)
            self._cols = cols
        else:
            table.clear()
        return table

    def _show(self, detail=False, table=False):
        self.query_one("#detail", Static).display = detail
        self.query_one("#summary", Static).display = table
        self.query_one("#subnets", DataTable).display = table

    # ─────────────────────────── core update ───────────────────────────

    def recompute(self) -> None:
        msg = self.query_one("#message", Static)
        result, err = core.parse(self.query_one("#addr", Input).value)
        if err:
            msg.update(f"⚠  {err}")
            self._show()
            return

        iface, note = result
        net = iface.network
        version = net.version
        top = core.max_bits(version)
        prefix = net.prefixlen

        vlsm_items, verr = core.parse_vlsm(self.query_one("#vlsm", Input).value)
        if verr:
            msg.update(f"⚠  {verr}")
            self._show()
            return

        split, serr = core.parse_split(
            self.query_one("#split", Input).value, prefix, top)
        if serr and vlsm_items is None:
            msg.update(f"⚠  {serr}")
            self._show()
            return

        msg.update(Text(note or "", style="dim italic"))

        if vlsm_items is not None:
            self._render_vlsm(net, vlsm_items)
        elif split is not None:
            self._render_split(net, prefix, split, version)
        else:
            self.query_one("#detail", Static).update(detail_panel(iface))
            rows, _ = core.describe(iface)
            self._copy_text = "\n".join(
                f"{r[0]}: {r[1]}" for r in rows if r)
            self._show(detail=True)

    def _render_split(self, net, prefix, split, version):
        base = int(net.network_address)
        count = 1 << (split - prefix)
        shown = min(count, MAX_ROWS)
        extra = "" if shown == count else f"   (showing first {shown:,})"
        self.query_one("#summary", Static).update(
            f"{net.network_address}/{prefix}  →  {count:,} subnet(s) of "
            f"/{split}{extra}")

        if version == 6:
            cols = ("#", "Subnet", "First host", "Last host", "Addresses")
        else:
            cols = ("#", "Subnet", "Host range", "Broadcast", "Hosts")
        table = self._set_columns(cols)

        for i in range(shown):
            sn = core.subnet_at(base, split, i, version)
            hmin, hmax, usable = core.host_range(sn)
            if version == 6:
                table.add_row(str(i), str(sn), str(hmin), str(hmax),
                              f"{usable:,}")
            else:
                rng = (str(hmin) if (split >= 31 and hmin == hmax)
                       else f"{hmin} – {hmax}")
                table.add_row(str(i), str(sn), rng,
                              str(sn.broadcast_address), f"{usable:,}")
        self._show(table=True)

    def _render_vlsm(self, net, items):
        allocs = core.vlsm(net, items)
        fitted = sum(1 for a in allocs if a["fits"])
        bad = len(allocs) - fitted
        warn = f"   ⚠ {bad} did not fit" if bad else ""
        self.query_one("#summary", Static).update(
            f"VLSM in {net}  →  {fitted}/{len(allocs)} subnet(s) allocated{warn}")

        cols = ("Name", "Need", "Subnet", "Host range", "Broadcast", "Usable")
        table = self._set_columns(cols)
        for a in allocs:
            if not a["fits"]:
                table.add_row(a["label"], str(a["hosts"]), "—",
                              "DOES NOT FIT", "—", "—")
                continue
            rng = (str(a["hmin"]) if a["hmin"] == a["hmax"]
                   else f"{a['hmin']} – {a['hmax']}")
            table.add_row(a["label"], str(a["hosts"]), str(a["net"]),
                          rng, str(a["broadcast"]), f"{a['usable']:,}")
        self._show(table=True)


if __name__ == "__main__":
    IpCalc().run()
