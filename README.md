# ipcalc — terminal IP subnet calculator

A fast, keyboard-driven IPv4/IPv6 subnet calculator for the terminal, built
with [Textual](https://textual.textualize.io/). No browser required.

## Features

- **IPv4 & IPv6** — address, netmask/wildcard, network, host range, broadcast,
  usable/total counts, class, and type (Private/Public/ULA/Link-local/…).
- **Binary view** — IPv4 addresses in binary with network bits and host bits
  color-coded at the prefix boundary.
- **Equal split** — divide a network into `/N` subnets, listed in a scrollable,
  zebra-striped table.
- **VLSM** — give a list of host requirements (`sales:50, eng:20, 10`) and get
  right-sized subnets allocated largest-first, with overflow flagged.
- **Clipboard** — press `c` to copy the highlighted row (or the detail view)
  via `wl-copy`.

## Install

```bash
./install.sh
```

This creates a self-contained virtualenv under `~/.local/share/ipcalc` and a
launcher at `~/.local/bin/ipcalc`. Then just run:

```bash
ipcalc
```

Upgrade by re-running `./install.sh`; remove with `./install.sh --uninstall`.

> If `~/.local/bin` isn't on your `PATH`, add
> `export PATH="$HOME/.local/bin:$PATH"` to your shell rc.

## Usage

| Field | Example | Result |
|-------|---------|--------|
| Address | `192.168.1.10/24`, `10.0.0.1 255.0.0.0`, `2001:db8::1/64` | Network detail |
| Split into /N | `26` | Equal `/26` subnets |
| VLSM host counts | `sales:50, eng:20, 10` | Right-sized subnets |

**Keys:** `Tab` switch field · `c` copy · `Ctrl+L` clear · `q`/`Esc` quit ·
arrows / PgUp / PgDn scroll the table.

## Layout

- `ipcalc.py` — Textual UI.
- `ipcalc_core.py` — pure calculation logic (standard library only); import and
  unit-test it without the UI.
- `install.sh` — installer/uninstaller.

## License

[MIT](LICENSE) © Alberto Linard
