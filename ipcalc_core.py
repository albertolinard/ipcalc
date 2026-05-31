"""
ipcalc_core.py — pure IPv4/IPv6 subnet-calculation helpers (no UI).

Only the Python standard library (ipaddress) is used here, so this module is
trivially testable and reusable by any front-end.
"""

import ipaddress


def max_bits(version):
    return 128 if version == 6 else 32


def parse(text):
    """Turn user text into an ip_interface, or (None, error).

    IPv4: 'ip/cidr', 'ip/dotted-mask', 'ip dotted-mask', bare ip (→ /24).
    IPv6: 'addr/prefix', bare addr (→ /64).
    """
    text = text.strip()
    if not text:
        return None, "Enter an IP address, e.g. 192.168.1.10/24 or 2001:db8::1/64"

    note = None
    is_v6 = ":" in text

    if "/" in text:
        ip_s, _, mask_s = text.partition("/")
    elif " " in text and not is_v6:
        ip_s, _, mask_s = text.partition(" ")
    else:
        ip_s, mask_s = text, ("64" if is_v6 else "24")
        note = f"no prefix given — assuming /{mask_s}"

    ip_s, mask_s = ip_s.strip(), mask_s.strip()

    try:
        addr = ipaddress.ip_address(ip_s)
    except ValueError:
        return None, f"'{ip_s}' is not a valid IP address"

    top = max_bits(addr.version)

    if "." in mask_s and addr.version == 4:        # dotted IPv4 netmask
        try:
            prefix = ipaddress.IPv4Network(f"0.0.0.0/{mask_s}").prefixlen
        except ValueError:
            return None, f"'{mask_s}' is not a valid netmask"
    else:
        if not mask_s.isdigit() or not (0 <= int(mask_s) <= top):
            return None, f"prefix must be 0-{top}, got '{mask_s}'"
        prefix = int(mask_s)

    iface = ipaddress.ip_interface(f"{ip_s}/{prefix}")
    return (iface, note), None


def parse_split(text, prefix, top):
    """Parse the optional split field. Returns (new_prefix|None, error|None)."""
    text = text.strip().lstrip("/").strip()
    if not text:
        return None, None
    if not text.isdigit() or not (0 <= int(text) <= top):
        return None, f"split /N must be 0-{top}, got '{text}'"
    n = int(text)
    if n < prefix:
        return None, f"split /{n} can't be larger than the network /{prefix}"
    return n, None


def host_range(net):
    """(first_host, last_host, usable_count).

    IPv4 honors the network/broadcast reservation, plus /31 (RFC 3021) and /32.
    IPv6 has no broadcast, so the whole range is usable.
    """
    p, num = net.prefixlen, net.num_addresses
    if net.version == 6:
        if p == 128:
            return net.network_address, net.network_address, 1
        return net.network_address, net.broadcast_address, num
    if p == 32:
        return net.network_address, net.network_address, 1
    if p == 31:
        return net.network_address, net.broadcast_address, 2
    return net.network_address + 1, net.broadcast_address - 1, num - 2


def subnet_at(base_int, new_prefix, i, version=4):
    """The i-th /new_prefix subnet of a network starting at base_int. O(1)."""
    block = 1 << (max_bits(version) - new_prefix)
    cls = ipaddress.IPv6Network if version == 6 else ipaddress.IPv4Network
    return cls((base_int + i * block, new_prefix))


def ipclass(addr):
    if addr.version == 6:
        return "—"                                  # classes are IPv4-only
    o = int(addr) >> 24
    if o < 128:   return "A"
    if o < 192:   return "B"
    if o < 224:   return "C"
    if o < 240:   return "D (multicast)"
    return "E (reserved)"


def kind_of(addr):
    if addr.is_loopback:     return "Loopback"
    if addr.is_link_local:   return "Link-local"
    if addr.is_multicast:    return "Multicast"
    if getattr(addr, "is_site_local", False):
        return "Site-local"
    # IPv6 unique-local fc00::/7 reports is_private but not the others
    if addr.version == 6 and addr.is_private and not addr.is_link_local:
        return "Unique-local (ULA)" if int(addr) >> 121 == 0x7e else "Private"
    if addr.is_private:      return "Private"
    if addr.is_reserved:     return "Reserved"
    return "Global" if addr.version == 6 else "Public"


def describe(iface):
    """Rows of (label, value, ip_or_None) for the single-network detail view."""
    addr, net = iface.ip, iface.network
    p = net.prefixlen
    hmin, hmax, usable = host_range(net)

    if net.version == 6:
        return [
            ("Address",   str(addr),                       addr),
            ("Full form", addr.exploded,                   None),
            ("Prefix",    f"/{p}",                          None),
            None,
            ("Network",   f"{net.network_address}/{p}",     net.network_address),
            ("HostMin",   str(hmin),                        hmin),
            ("HostMax",   str(hmax),                        hmax),
            None,
            ("Addresses", f"{usable:,}",                    None),
            ("Type",      kind_of(addr),                    None),
        ], p

    return [
        ("Address",   str(addr),                       addr),
        ("Netmask",   f"{net.netmask} = /{p}",          net.netmask),
        ("Wildcard",  str(net.hostmask),                net.hostmask),
        None,
        ("Network",   f"{net.network_address}/{p}",     net.network_address),
        ("HostMin",   str(hmin),                        hmin),
        ("HostMax",   str(hmax),                        hmax),
        ("Broadcast", str(net.broadcast_address),       net.broadcast_address),
        None,
        ("Hosts/Net", f"{usable:,}  (total {net.num_addresses:,})", None),
        ("Class",     ipclass(addr),                    None),
        ("Type",      kind_of(addr),                    None),
    ], p


def bits(ip):
    """32-bit binary, octets dot-separated (IPv4 only): 11000000.10101000..."""
    return ".".join(f"{b:08b}" for b in ip.packed)


# ─────────────────────────── VLSM ───────────────────────────

def _next_pow2(n):
    return 1 if n <= 1 else 1 << (n - 1).bit_length()


def parse_vlsm(text):
    """Parse 'name:50, 20, web:10' into [(label, hosts), ...] or (None, error)."""
    text = text.strip()
    if not text:
        return None, None
    items = []
    for i, tok in enumerate(t for t in text.replace(",", " ").split() if t):
        label, sep, num = tok.partition(":")
        if not sep:
            label, num = f"net{i + 1}", tok
        if not num.isdigit() or int(num) < 1:
            return None, f"'{tok}' — host count must be a positive integer"
        items.append((label, int(num)))
    if not items:
        return None, "list one or more host counts, e.g. 50, 20, 10"
    return items, None


def vlsm(net, reqs):
    """Allocate subnets (largest first) for [(label, hosts), ...] within net.

    Returns a list of dicts. Entries that don't fit have fits=False.
    IPv4 reserves network+broadcast; IPv6 treats the whole block as usable.
    """
    version = net.version
    top = max_bits(version)
    base = int(net.network_address)
    end = base + net.num_addresses                  # exclusive
    cursor = base

    out = []
    for label, hosts in sorted(reqs, key=lambda r: r[1], reverse=True):
        need = hosts + (2 if version == 4 else 0)
        block = _next_pow2(need)
        if cursor % block:                          # align up to block boundary
            cursor += block - (cursor % block)
        if cursor + block > end:
            out.append({"label": label, "hosts": hosts, "fits": False})
            continue
        p = top - (block.bit_length() - 1)
        sn = subnet_at(cursor, p, 0, version)
        hmin, hmax, usable = host_range(sn)
        out.append({
            "label": label, "hosts": hosts, "fits": True, "net": sn,
            "prefix": p, "hmin": hmin, "hmax": hmax, "usable": usable,
            "broadcast": sn.broadcast_address, "size": block,
        })
        cursor += block
    return out
