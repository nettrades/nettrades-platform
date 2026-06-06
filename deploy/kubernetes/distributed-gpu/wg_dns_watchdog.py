# -*- coding: utf-8 -*-
# =============================================================================
# Section H – WireGuard DNS Re-Resolution Watchdog
# =============================================================================
# WireGuard resolves the endpoint hostname to an IP address only once, at
# startup.  If the peer's public IP changes (common for freelancers with
# dynamic IPs), the tunnel freezes because WireGuard keeps sending packets
# to the old IP.
#
# This watchdog runs as a lightweight daemon thread inside the NETTRADES
# agent.  Every 30 seconds it:
#   1. Reads the latest handshake time for the configured peer.
#   2. If the handshake is older than 135 seconds (no recent communication),
#      it re-resolves the DNS hostname and updates the WireGuard endpoint.
#   3. If DNS resolution fails 3 consecutive times, it restarts the WireGuard
#      interface to force a full re-initialisation.
#
# This implements the same logic as the official wireguard-tools
# reresolve-dns.sh script (GPL-2.0), adapted for Python to run inside
# the agent process without an external cron job.
# =============================================================================
import subprocess, socket, re, logging, time, threading, os
from pathlib import Path

_logger = logging.getLogger(__name__)

# ---- Configuration ----
WG_CONFIG = "/etc/wireguard/wg0.conf"
WG_INTERFACE = "wg0"
WATCHDOG_INTERVAL = 30       # seconds between checks
STALE_HANDSHAKE_SECS = 135   # re-resolve if handshake older than this
MAX_DNS_FAILURES = 3          # consecutive DNS failures before interface restart


def _parse_wg_config(config_path: str = WG_CONFIG) -> dict:
    """
    Parse the WireGuard config file and return the first [Peer] section's
    domain, port, and public key.  Returns an empty dict if no domain-based
    endpoint is found (e.g. a static IP was used).
    """
    if not os.path.exists(config_path):
        return {}

    peer_section = False
    result = {"public_key": "", "endpoint_domain": "", "endpoint_port": "51820"}

    with open(config_path, "r") as f:
        for line in f:
            stripped = line.split("#")[0].strip()
            if not stripped:
                continue

            # Section header
            if stripped.startswith("[") and stripped.endswith("]"):
                peer_section = (stripped == "[Peer]")
                continue

            if not peer_section:
                continue

            if "=" not in stripped:
                continue

            key, _, value = stripped.partition("=")
            key = key.strip()
            value = value.strip()

            if key == "PublicKey":
                result["public_key"] = value
            elif key == "Endpoint":
                # Endpoint can be domain:port or ip:port
                match = re.match(r"^([^:]+):(\d+)$", value)
                if match:
                    host = match.group(1)
                    port = match.group(2)
                    result["endpoint_port"] = port
                    # Only track domain endpoints (not static IPs)
                    if not re.match(r"^\d+\.\d+\.\d+\.\d+$", host):
                        result["endpoint_domain"] = host

    if not result["public_key"] or not result["endpoint_domain"]:
        return {}   # No domain endpoint to watch

    return result


def _get_latest_handshake(public_key: str, interface: str = WG_INTERFACE) -> int:
    """
    Return the Unix timestamp of the last handshake for the given peer,
    or 0 if the peer is not found or has never shaken hands.
    """
    try:
        output = subprocess.run(
            ["wg", "show", interface, "latest-handshakes"],
            capture_output=True, text=True, timeout=5
        )
        for line in output.stdout.splitlines():
            if public_key in line:
                parts = line.strip().split()
                # Format: <public_key>  <epoch_seconds>
                if len(parts) >= 2:
                    return int(parts[-1])
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError) as e:
        _logger.warning("Failed to read WireGuard handshake: %s", e)
    return 0


def _resolve_domain(domain: str) -> str | None:
    """
    Resolve a domain name to its IPv4 address.  Returns None on failure.
    """
    try:
        addrs = socket.getaddrinfo(domain, None, socket.AF_INET, socket.SOCK_DGRAM)
        for addr in addrs:
            ip = addr[4][0]
            if ip:
                return ip
    except socket.gaierror as e:
        _logger.warning("DNS resolution failed for %s: %s", domain, e)
    return None


def _update_endpoint(public_key: str, new_ip: str, port: str, interface: str = WG_INTERFACE):
    """
    Update the WireGuard peer endpoint using `wg set`.
    """
    new_endpoint = f"{new_ip}:{port}"
    try:
        subprocess.run(
            ["wg", "set", interface, "peer", public_key, "endpoint", new_endpoint],
            capture_output=True, text=True, check=True, timeout=10
        )
        _logger.info("Updated WireGuard endpoint for peer %s → %s", public_key[:16], new_endpoint)
    except subprocess.CalledProcessError as e:
        _logger.error("Failed to update WireGuard endpoint: %s", e.stderr)


def _restart_interface(interface: str = WG_INTERFACE):
    """
    Bring the WireGuard interface down and back up to force a full re-init.
    """
    try:
        subprocess.run(["wg-quick", "down", interface], capture_output=True, timeout=15)
        subprocess.run(["wg-quick", "up", interface], capture_output=True, check=True, timeout=15)
        _logger.info("WireGuard interface %s restarted.", interface)
    except subprocess.CalledProcessError as e:
        _logger.error("Failed to restart WireGuard interface: %s", e.stderr)


def dns_watchdog_loop():
    """
    Main watchdog loop.  Runs forever as a daemon thread.
    Checks handshake staleness and re-resolves DNS when needed.
    """
    _logger.info("DNS watchdog started (interval=%ds, stale=%ds).",
                 WATCHDOG_INTERVAL, STALE_HANDSHAKE_SECS)

    consecutive_dns_failures = 0

    while True:
        try:
            peer = _parse_wg_config()
            if not peer:
                _logger.debug("No domain endpoint configured. Watchdog sleeping.")
                time.sleep(WATCHDOG_INTERVAL)
                continue

            handshake = _get_latest_handshake(peer["public_key"])
            now = int(time.time())

            if handshake == 0 or (now - handshake) > STALE_HANDSHAKE_SECS:
                _logger.info("Handshake stale (last=%s). Re-resolving %s...",
                             "never" if handshake == 0 else f"{now - handshake}s ago",
                             peer["endpoint_domain"])

                new_ip = _resolve_domain(peer["endpoint_domain"])
                if new_ip:
                    consecutive_dns_failures = 0
                    _update_endpoint(peer["public_key"], new_ip, peer["endpoint_port"])
                else:
                    consecutive_dns_failures += 1
                    _logger.warning("DNS failure %d/%d for %s",
                                    consecutive_dns_failures, MAX_DNS_FAILURES,
                                    peer["endpoint_domain"])
                    if consecutive_dns_failures >= MAX_DNS_FAILURES:
                        _logger.error("Max DNS failures reached. Restarting WireGuard interface.")
                        _restart_interface()
                        consecutive_dns_failures = 0

        except Exception:
            _logger.exception("Unexpected error in DNS watchdog loop.")

        time.sleep(WATCHDOG_INTERVAL)


def start_dns_watchdog():
    """
    Launch the DNS watchdog as a daemon thread.  Safe to call multiple times.
    """
    thread = threading.Thread(target=dns_watchdog_loop, daemon=True, name="wg-dns-watchdog")
    thread.start()
    _logger.info("DNS watchdog thread started (TID=%s).", thread.ident)
    return thread