# scripts/

## `cloud_query.py`
Run directly (`python3 cloud_query.py`) on any machine with internet
access. Queries the vendor's cloud relay servers and prints the camera's
current session port. No phone, no LAN access, no root needed. The
device-identity blob inside it is specific to the one camera this was
reverse-engineered against (`HK-IOTA00376790BFJNP`); for a different
device, capture one `0x28` request (see `docs/protocol.md`) and
substitute the device-identity blob bytes.

## `pppp_crypto.py`
Pure-Python implementation of the public PPPP "blanket cipher". Run
directly (`python3 pppp_crypto.py`) to self-test against a real captured
packet. Import `pppp_decrypt`/`pppp_encrypt` for your own use. This is
useful for ANY camera in the PPPP/CS2/iLnk protocol family, not just this
one device — try the three documented default PSKs first
(`KNOWN_DEFAULT_PSKS`).

## `decrypt_oracle.c` + `bionic_compat.c` + `liblog_stub.c` + `patch_so.py`
Together these let you run the camera app's REAL compiled native library
(`libapTrans_jni.so`, an Android/bionic ARM64 `.so`) directly on a Linux
ARM64 host via `dlopen()`, so you can call its actual cipher functions
instead of risking a subtly-wrong reimplementation. **The vendor's `.so`
file itself is not included here** (it's the camera vendor's copyrighted
binary) — pull it yourself from the phone:

```sh
adb shell pm path com.shix.hk365   # find the arm64 split path
adb pull /data/app/.../com.shix.hk365-xxxx/split_config.arm64_v8a.apk
unzip -j split_config.arm64_v8a.apk 'lib/arm64-v8a/libapTrans_jni.so'
```

Then, on a Linux **aarch64** host (NOT x86_64 — the vendor .so is ARM64):

```sh
python3 patch_so.py          # produces a loadable libapTrans_jni.so next to this script
gcc -o decrypt_oracle decrypt_oracle.c bionic_compat.c -ldl \
    -U_FORTIFY_SOURCE -D_FORTIFY_SOURCE=0 -rdynamic
gcc -shared -o liblog.so liblog_stub.c          # Android liblog.so stub
mkdir -p lib
ln -s /lib/aarch64-linux-gnu/libc.so.6 lib/libc.so
ln -s /lib/aarch64-linux-gnu/libm.so.6 lib/libm.so
ln -s /lib/aarch64-linux-gnu/libdl.so.2 lib/libdl.so
cp liblog.so lib/
LD_LIBRARY_PATH=./lib ./decrypt_oracle <hex-encoded-ciphertext>
```

`patch_so.py` has a hardcoded `SRC`/`DST` path at the top — edit those to
point at your pulled `.so` and desired output location before running.

`decrypt_oracle.c` as shipped calls
`cs2p2p__P2P_Proprietary_Decrypt` with PSK `"SHIX"` — already proven NOT
to be this device's command-channel cipher (see `docs/protocol.md`), but
kept as a working, tested example of the dlopen-oracle technique. To
chase the REAL blocker (the `e_init`/`e_c_e_b` session key — see
`STATUS.md`), adapt this file to call `e_init`/`e_c_e_b` instead, or
better: attach `gdb` to the running oracle process and single-step the
real call live (this is how the key-structure facts in `docs/protocol.md`
were originally obtained).
