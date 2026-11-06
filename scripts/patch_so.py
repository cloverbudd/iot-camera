#!/usr/bin/env python3
"""Patch the Android vendor .so so glibc can dlopen it on the rock5a.

Three things block that:
  1. DT_VERNEED requires the Android bionic version node "LIBC", which
     glibc's libc.so.6 does not define  -> loader error
     "version `LIBC' not found".
     Fix: drop DT_VERNEED/DT_VERNEEDNUM/DT_VERSYM and set every
     .gnu.version entry to 1 (*global*, unversioned).
  2. DT_NEEDED names are Android-style ("libc.so", "libm.so", "libdl.so",
     "liblog.so"). glibc only ships libc.so.6/libm.so.6/libdl.so.2.
     Fix: handled outside via LD_LIBRARY_PATH + symlinks (see run dir).
  3. liblog.so does not exist on Linux -> we build a stub.
"""
import struct
import shutil
import sys

SRC = "./libapTrans_jni.so.orig"  # the .so as pulled from the phone/APK
DST = "./libapTrans_jni.so"       # patched, loadable output (dlopen target)

DT_VERSYM = 0x6FFFFFF0
DT_VERNEED = 0x6FFFFFFE
DT_VERNEEDNUM = 0x6FFFFFFF


def patch(path_in, path_out):
    d = bytearray(open(path_in, "rb").read())

    # ---- ELF header ----
    assert d[:4] == b"\x7fELF" and d[4] == 2, "expected ELF64"
    e_shoff, = struct.unpack_from("<Q", d, 0x28)
    e_shentsize, e_shnum, e_shstrndx = struct.unpack_from("<HHH", d, 0x3A)
    e_phoff, = struct.unpack_from("<Q", d, 0x20)
    e_phentsize, e_phnum = struct.unpack_from("<HH", d, 0x36)

    secs = []
    for i in range(e_shnum):
        off = e_shoff + i * e_shentsize
        name, typ, flags, addr, offset, size, link, info, align, entsize = \
            struct.unpack_from("<IIQQQQIIQQ", d, off)
        secs.append(dict(i=i, name=name, typ=typ, flags=flags, addr=addr,
                          offset=offset, size=size, link=link, entsize=entsize,
                          hdr=off))

    shstr = secs[e_shstrndx]
    def sname(s):
        o = shstr["offset"] + s["name"]
        return d[o:d.index(b"\x00", o)].decode()

    # ---- 1. .gnu.version: every entry -> 1 (global / unversioned) ----
    for s in secs:
        if sname(s) == ".gnu.version":
            n = s["size"] // 2
            struct.pack_into("<%dH" % n, d, s["offset"], *([1] * n))
            print(f"  .gnu.version: {n} entries -> 1 (global)")
            ver = s

    # ---- 2. .dynamic: kill DT_VERSYM / DT_VERNEED / DT_VERNEEDNUM ----
    dyn = next(s for s in secs if sname(s) == ".dynamic")
    off, size = dyn["offset"], dyn["size"]
    n = size // 16
    for i in range(n):
        p = off + i * 16
        tag, val = struct.unpack_from("<qQ", d, p)
        if tag in (DT_VERSYM, DT_VERNEED, DT_VERNEEDNUM):
            print(f"  .dynamic: tag 0x{tag:x} -> 0 (was {val})")
            struct.pack_into("<qQ", d, p, 0, 0)
        if tag == 0:
            break

    open(path_out, "wb").write(bytes(d))
    print(f"  wrote {path_out} ({len(d)} bytes)")


if __name__ == "__main__":
    import os
    os.makedirs(os.path.dirname(DST), exist_ok=True)
    patch(SRC, DST)
