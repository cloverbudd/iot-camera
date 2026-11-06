# STATUS — resume here

## The one blocker

The control-channel JSON commands (`check_user`, `get_parms`, `stream`,
etc.) are encrypted with a cipher whose **session key is generated at
runtime** inside the camera app's native library (`libapTrans_jni.so`),
via the functions `hl_p2p_init` → `m_init`/`m_u`/`m_f` → `e_init` →
`e_c_e_b` (internally branded "HLP2P", distinct from the publicly
documented PPPP "blanket cipher" — see `docs/protocol.md` for why we're
sure of this).

We extracted a key/table via `gdb`, breaking at `e_init` while calling
`hl_p2p_init()` standalone (no real camera session). That key did **not**
decrypt real captured ciphertext. The most likely explanation: the real
session key depends on additional entropy from the actual P2P
handshake/punch exchange with the camera, which our standalone native
calls never performed.

## The one next step

**Root the phone** (or get a rooted/debuggable test device with the same
app), then:

1. Install `gdbserver` on the phone (or use `frida` if you prefer — either
   works once you have root/`run-as`).
2. Launch `com.shix.hk365`, attach to the running process.
3. Set a breakpoint on `e_init` inside `libapTrans_jni.so` (same function,
   same approach as our earlier successful standalone gdb session — see
   `docs/investigation-log.md`, "session part 1" for the exact gdb
   commands that worked).
4. Trigger a real command from the app UI (e.g. open live view) while
   simultaneously capturing the wire traffic (PCAPdroid or similar).
5. Dump the actual key/table bytes `e_init` receives AT THAT MOMENT.
6. Test that key against the simultaneously-captured ciphertext using
   `scripts/decrypt_oracle.c`-style direct native calls (NOT a
   reimplementation — call the real `e_c_e_b` function with the extracted
   key, exactly like `scripts/decrypt_oracle.c` does for the other
   cipher).

If that key matches, the control channel is solved and the rest (sending
our own commands, requesting the video stream) is just replaying the
already-fully-understood wire framing in `docs/protocol.md`.

## Secondary unresolved thing (same root cause, probably)

The LAN handshake (client sends a self-generated session token to the
camera's current UDP port) gets no reply even when the port was *just*
learned fresh from the cloud relay and the token is freshly generated.
This may resolve itself once (or alongside) the real key/handshake timing
is observed live on the rooted phone — the real app may be doing an
additional step (e.g. registering the token via the `0x2c` relay packet
with fields we haven't matched) that's easier to see by watching the real
app than by guessing byte layouts. Capture one more full session, this
time on a rooted phone, with simultaneous PCAPdroid + a BTSnoop pairing
capture + the gdb session above, all started together.

## What NOT to re-try (already exhausted, won't help)

- Brute-forcing PSK strings against the control channel — done
  exhaustively (documented PSK table, device-specific guesses, full
  0-255 single-byte sweep). The control channel does not use the
  documented PPPP "blanket cipher" at all; proved by direct disassembly
  of the real send path (`cs2p2p_PPPP_DRW_Send`/`SendMessage`) showing it
  is NOT the function actually called for this device's command channel.
- More static disassembly of `e_init`/`m_init`/`m_u`/`m_f`'s buffer
  layout — two independent full sweeps of slice/offset interpretations
  already failed; the problem is a missing *runtime input*, not a
  misread static structure.
- Replaying old captured handshake/session bytes against a freshly
  queried port — confirmed dead, the port and token are both
  session-specific and rotate.
- Trying to attach `gdb`/`run-as` to the *unrooted* phone's actual running
  app process — confirmed blocked ("package not debuggable", no root
  shell). This is why root is the prerequisite, not optional.
