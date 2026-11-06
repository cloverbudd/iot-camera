#!/usr/bin/env python3
"""cloud_query.py — query the HK365/SHIX vendor's cloud rendezvous server
directly from the rock5a to learn the camera's current ephemeral port,
without needing the phone at all.

Decoded from a fresh paired capture (fresh.pcap):
  App sends (UDP, 37 bytes) to EACH of 3 relay servers on port 65200:
    28 fc97293d8ac81db6474fe3cbd48a8c1b <seq_nibble> 522ff3401de0 <phone_ip:4B> <?:4B> 00 <nonce:4B>
  Relay replies:
    2 bytes  "28 <id>"                 - ack
    8 bytes  "28 <id> <port:LE16> <wan_ip:4B>"  - the camera's current port + WAN IP

The 16-byte blob "fc97293d8ac81db6474fe3cbd48a8c1b" (device identifier,
derived from the camera's DID) and the "522ff3401" fragment are CONSTANT
for this specific camera (HK-IOTA00376790BFJNP) and were extracted directly
from the capture. The low nibble after the 16-byte blob increments per
request attempt (b0/b1/b2.../b4/b5/b6...) but servers accept any reasonable
value, so we just reuse what was observed.
"""
import socket
import struct
import sys
import time

RELAYS = ["47.242.56.11", "125.122.23.54", "120.78.4.128"]
RELAY_PORT = 65200

# Captured constant request body (device-identifying bytes), minus the
# phone-IP field which we substitute with our own.
DEVICE_BLOB = bytes.fromhex("fc97293d8ac81db6474fe3cbd48a8c1b05")  # 17 bytes incl. fixed counter nibble
TAIL_CONST = bytes.fromhex("22ff3401de0d")  # 6 bytes, verified byte-exact offsets


def my_lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.168.4.99", 1))
        return s.getsockname()[0]
    finally:
        s.close()


def build_request():
    ip = my_lan_ip()
    ip_bytes = bytes(int(o) for o in ip.split("."))
    # 37-byte frame: 1(type) + 17(device blob) + 6(tail const) + 4(my ip)
    # + 4(unknown) + 1(0x00) + 4(nonce) = 37
    unknown4 = bytes.fromhex("286ae002")  # constant in capture; meaning unclear
    nonce = struct.pack("<I", int(time.time()) & 0xFFFFFFFF)
    req = b"\x28" + DEVICE_BLOB + TAIL_CONST + ip_bytes + unknown4 + b"\x00" + nonce
    return req


def query(relay, timeout=3.0):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    sock.bind(("0.0.0.0", 0))
    req = build_request()
    print(f"  -> {relay}:{RELAY_PORT}  req({len(req)}B)={req.hex()}")
    sock.sendto(req, (relay, RELAY_PORT))
    results = []
    t_end = time.time() + timeout
    while time.time() < t_end:
        try:
            data, addr = sock.recvfrom(4096)
        except socket.timeout:
            break
        print(f"  <- {addr}  ({len(data)}B) {data.hex()}")
        results.append((addr, data))
        if len(data) == 8:
            port = struct.unpack_from("<H", data, 2)[0]
            ip = ".".join(str(b) for b in data[4:8])
            print(f"     ==> decoded: port={port}  wan_ip={ip}")
    sock.close()
    return results


def main():
    print(f"local LAN IP: {my_lan_ip()}")
    for relay in RELAYS:
        print(f"\n=== querying {relay} ===")
        query(relay)


if __name__ == "__main__":
    sys.exit(main() or 0)
