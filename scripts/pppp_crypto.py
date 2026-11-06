#!/usr/bin/env python3
"""pppp_crypto.py — the public PPPP protocol family's "blanket cipher".

Ported from the magicus/pppp-dissector project (pppp_dissect.lua) and
palant.info's "Analysis of PPPP encryption" writeup. This is a simple
single-byte-chaining XOR keystream, NOT a strong cipher — treat any key
recovered via this scheme as a toy-level secret, not real security.

Validated against real captured traffic from an HK365/SHIX camera: the
camera's cloud-relay "0x2c" registration packet decrypts to exactly the
universal PPPP magic byte 0xF1 when using PSK "camera" (see
docs/protocol.md). This is NOT the cipher used for this device's actual
JSON command channel (see docs/protocol.md + docs/investigation-log.md
for why) -- it IS confirmed correct for the 0x2c message type, and is a
useful reference implementation for ANY camera in this protocol family
(try the documented default PSKs "camera"/"SHIX"/"SSD@cs2-network." first).
"""
from __future__ import annotations

# Full 256-byte shuffle table. Verified byte-for-byte identical whether
# extracted independently from the native .so (file offset 0x2a8d0, via
# disassembly of __P2P_Proprietary_SelectTableElement) or taken from the
# public magicus/pppp-dissector project's pppp_dissect.lua.
SHUFFLE_TABLE = bytes.fromhex("""
7C 9C E8 4A 13 DE DC B2 2F 21 23 E4 30 7B 3D 8C
BC 0B 27 0C 3C F7 9A E7 08 71 96 00 97 85 EF C1
1F C4 DB A1 C2 EB D9 01 FA BA 3B 05 B8 15 87 83
28 72 D1 8B 5A D6 DA 93 58 FE AA CC 6E 1B F0 A3
88 AB 43 C0 0D B5 45 38 4F 50 22 66 20 7F 07 5B
14 98 1D 9B A7 2A B9 A8 CB F1 FC 49 47 06 3E B1
0E 04 3A 94 5E EE 54 11 34 DD 4D F9 EC C7 C9 E3
78 1A 6F 70 6B A4 BD A9 5D D5 F8 E5 BB 26 AF 42
37 D8 E1 02 0A AE 5F 1C C5 73 09 4E 69 24 90 6D
12 B3 19 AD 74 8A 29 40 F5 2D BE A5 59 E0 F4 79
D2 4B CE 89 82 48 84 25 C6 91 2B A2 FB 8F E9 A6
B0 9E 3F 65 F6 03 31 2E AC 0F 95 2C 5C ED 39 B7
33 6C 56 7E B4 A0 FD 7A 81 53 51 86 8D 9F 77 FF
6A 80 DF E2 BF 10 D7 75 64 57 76 F3 55 CD D0 C8
18 E6 36 41 62 CF 99 F2 32 4C 67 60 61 92 CA D3
EA 63 7D 16 B6 8E D4 68 35 C3 52 9D 46 44 1E 17
""".replace("\n", " ").strip())
assert len(SHUFFLE_TABLE) == 256


def psk_hash(psk: bytes) -> list[int]:
    """Reduce an arbitrary-length PSK to a 4-byte effective key."""
    h = [0, 0, 0, 0]
    for b in psk:
        h[0] = (h[0] + b) & 255
        h[1] = (h[1] - b) & 255
        h[2] = (h[2] + b // 3) & 255
        h[3] = (h[3] ^ b) & 255
    return h


def _lookup(h: list[int], byte: int) -> int:
    idx = byte & 3
    index = (h[idx] + byte) & 255
    return SHUFFLE_TABLE[index]


def pppp_decrypt(psk: bytes, enc: bytes) -> bytes:
    h = psk_hash(psk)
    prev = 0
    out = bytearray(len(enc))
    for i, old in enumerate(enc):
        out[i] = old ^ _lookup(h, prev)
        prev = old  # chain on the CIPHERTEXT byte when decrypting
    return bytes(out)


def pppp_encrypt(psk: bytes, clear: bytes) -> bytes:
    h = psk_hash(psk)
    prev = 0
    out = bytearray(len(clear))
    for i, old in enumerate(clear):
        new = old ^ _lookup(h, prev)
        out[i] = new
        prev = new  # chain on the newly-produced CIPHERTEXT byte
    return bytes(out)


# Known default PSKs the public dissector tries automatically when none is
# configured (see pppp_dissect.lua's magic-byte heuristic).
KNOWN_DEFAULT_PSKS = {
    0x2C: b"camera",
    0x9F: b"SHIX",
    0xB1: b"SSD@cs2-network.",
}


def guess_psk_from_magic(first_byte: int) -> bytes | None:
    return KNOWN_DEFAULT_PSKS.get(first_byte)


if __name__ == "__main__":
    # Self-test against real captured traffic from the HK365/SHIX camera.
    req2c = bytes.fromhex(
        "2c494f5441d6bf0500aad6dd3083972b9a26a98639000000000000000001020000"
        "000200005a0000005a000100c0a80463"
    )
    dec = pppp_decrypt(b"camera", req2c)
    print("decrypted:", dec.hex())
    assert dec[0] == 0xF1, f"expected 0xf1, got {dec[0]:#x}"
    print("OK: first byte is the universal PPPP magic 0xF1, as expected.")

    # Round-trip check.
    re_enc = pppp_encrypt(b"camera", dec)
    assert re_enc == req2c, "encrypt(decrypt(x)) != x"
    print("OK: encrypt(decrypt(x)) == x (round-trip verified).")
