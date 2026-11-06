# iot-camera — HK365/SHIX P2P camera, local access without the cloud

Goal: talk directly to a cheap WiFi IP camera (brand "HK365"/"SHIX", app
`com.shix.hk365`) over the LAN — live view, control, and eventually
NAS-side recording — without the vendor app or any cloud subscription.

**Status: blocked on one specific, well-understood thing.** Everything
about the wire protocol is mapped. The only missing piece is the live
session encryption key used by the device's native library, and the one
remaining way to get it needs a **rooted phone** (or a rooted/debuggable
build of the vendor app) to live-debug the real app process at the moment
it sends a command. See [`STATUS.md`](STATUS.md) for the exact next step.

If you're picking this back up: read `STATUS.md` first, then
`docs/protocol.md` for the full technical reference, then look at
`scripts/` for working, reusable code.

## What already works today, no root needed

- **Cloud-relay discovery** (`scripts/cloud_query.py`) — learns the
  camera's current session port directly from the vendor's cloud relay
  servers, from any machine on the internet, no phone or LAN access
  required.
- **Video channel is cleartext MJPEG** — no cipher needed at all once a
  session is open.
- **The `0x2c` cloud-registration packet's cipher is fully solved and
  validated** (`scripts/pppp_crypto.py`) — this is the one part of the
  documented public "PPPP" protocol family's blanket cipher that we proved
  this device actually uses, and it checks out byte-for-byte against the
  public reference implementation.

## What's blocked

- The actual control-channel (JSON command) cipher is a different,
  vendor-specific, **session-derived** key (`e_init`/`e_c_e_b`, branded
  internally as "HLP2P"). The key material is NOT hardcoded — it's
  generated at runtime inside the native library, and we were only able
  to extract it via `gdb` at one specific moment (library init), which did
  not match the key actually used when a real session sends a real
  command. Resolving this needs the real phone app, live, mid-command —
  see `STATUS.md`.
- The exact LAN handshake acceptance rule (why a freshly-generated session
  token sent straight to the camera gets no reply) is also unresolved,
  likely for a related reason.

## Repo layout

```
README.md          — this file
STATUS.md          — exact current blocker + the one next step
docs/
  protocol.md       — full wire protocol reference (frame formats, opcodes,
                       cloud relay, handshake, cipher analysis)
  investigation-log.md — chronological findings, every dead end and why,
                       so nobody repeats them
scripts/
  cloud_query.py     — query the cloud relay for the camera's live port
  pppp_crypto.py     — the validated PPPP "blanket cipher" (decrypt/encrypt)
  decrypt_oracle.c   — call the REAL vendor .so's cipher function directly
                        (dlopen-on-Linux oracle), bypassing reimplementation risk
  bionic_compat.c    — glibc shims so the oracle can dlopen() the Android .so
  liblog_stub.c      — Android liblog.so stub for the oracle
  patch_so.py        — strips Android ELF version requirements so the vendor
                        .so loads under glibc
```

## Credentials / privacy note

No real camera login password, WiFi password, or account credential is
stored in this repo. Device identifiers (DID) are not secrets (printed on
the physical device) and are included for reference; anything that WAS a
real secret observed during capture has been redacted or generalized.
