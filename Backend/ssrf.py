import socket
import ipaddress
import os
import config

# Known cloud metadata IP networks and addresses to strictly block
BLOCKED_METADATA_NETS = [
    ipaddress.ip_network("169.254.0.0/16"),     # AWS, Azure, GCP, OpenStack link-local metadata
    ipaddress.ip_network("fe80::/10"),          # IPv6 link-local
    ipaddress.ip_network("100.100.100.200/32"), # Alibaba Cloud metadata
]

# Development & local whitelist
DEFAULT_WHITELIST = {"localhost", "127.0.0.1", "host.docker.internal"}

def is_safe_host(host: str) -> bool:
    """
    Guards against SSRF attacks.
    Ensures the provided SAP host resolves to an approved network (private RFC1918 or whitelisted)
    and strictly forbids cloud metadata services (e.g. 169.254.169.254), link-local,
    multicast, and non-whitelisted loopback addresses.
    """
    if not host or not isinstance(host, str):
        return False
        
    cleaned_host = host.strip().lower()
    
    # Strip protocol if accidentally included
    if "://" in cleaned_host:
        cleaned_host = cleaned_host.split("://", 1)[1]
    cleaned_host = cleaned_host.split("/")[0].split(":")[0]

    # Explicit whitelist (for dev/test setups and configured environments)
    whitelist = set(DEFAULT_WHITELIST)
    # Add configured default HANA host from env if available
    if config.HANA_HOST:
        whitelist.add(config.HANA_HOST.strip().lower())
    # Additional allowed hosts via env var (comma-separated)
    env_allowed = os.getenv("CIRA_ALLOWED_SAP_HOSTS", "")
    if env_allowed:
        for h in env_allowed.split(","):
            if h.strip():
                whitelist.add(h.strip().lower())

    try:
        # Resolve all addresses (both IPv4 and IPv6)
        addr_infos = socket.getaddrinfo(cleaned_host, None)
        if not addr_infos:
            return False

        for family, _, _, _, sockaddr in addr_infos:
            ip_str = sockaddr[0]
            ip = ipaddress.ip_address(ip_str)

            # 1. Strictly block all cloud metadata and link-local ranges
            if ip.is_link_local or any(ip in net for net in BLOCKED_METADATA_NETS):
                return False

            # 2. Allow loopback ONLY if the host is explicitly in the whitelist
            # (Note: IPv6 ::1 is both is_loopback and is_reserved in Python ipaddress)
            if ip.is_loopback:
                if cleaned_host in whitelist:
                    continue
                return False

            # 3. Block multicast, reserved non-loopback, and unspecified (0.0.0.0 / ::)
            if ip.is_multicast or ip.is_reserved or ip.is_unspecified:
                return False

            # 4. If host is explicitly whitelisted, accept valid resolved IPs
            if cleaned_host in whitelist:
                continue

            # 5. Allow private networks (RFC1918, Carrier-Grade NAT 100.64.0.0/10)
            if not ip.is_private:
                # Public IP not in whitelist
                return False

        return True

    except (socket.gaierror, socket.herror, ValueError):
        return False
