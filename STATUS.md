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

## UPDATE 2026-11-07: UART confirmed working — full findings in docs/uart-findings.md

The 3-pin `TXD RXD GND` header on the mainboard (`X8-V1.1-26811`) is a
**live, readable debug console at 921600 8N1** (not 115200 — that and
every other common rate gave garbage). Confirmed with an FTDI FT232RL set
to 3.3V, crossed wiring, bare jumper wire push-fit into the unsoldered
holes.

What we got: continuous firmware debug log (Wi-Fi stats, JPEG frame
sizes, P2P/relay state matching `libapTrans_jni.so` internals) and
**plaintext JSON** command/response blobs via `CZ_P2P_JsonSendBackEx`,
giving us real field names/values for cmd IDs 100/101/103/107/111/126/715
and hardware IDs (chip `TXW816`, sensor `GC0307`, factory `CYCZ`,
firmware `AP_TTWO_PONE-8`). Full detail, exact wiring, and the baud-sweep
method: **`docs/uart-findings.md`**.

## UPDATE 2026-11-07 (later same day): UART key hunt CONCLUSIVELY CLOSED

A clean full cold-boot capture succeeded (no corruption this time) and
covered the entire boot sequence including the P2P module's startup and
its full alive/relay state machine. **The control-channel session key
never appears anywhere in the log.** This device's firmware genuinely
does not print it over UART — confirmed, not a wiring/baud-reliability
issue (this capture was clean start to finish). Full detail:
`docs/uart-findings.md`, "second session" section.

**UART is done as a path to the session key. Rooting the phone (below)
is now the only remaining path.** UART remains useful for the plaintext
JSON protocol fields already documented, and as a possible route to dump
the `syscfg` flash partition directly later if needed (config data only,
not expected to contain the session key either).

## Original UART instructions (kept for reference — wiring/baud still correct if reusing this console for protocol/debug work)

1. Get a **3.3V-logic** USB-to-TTL/serial adapter (CP2102, CH340, FTDI —
   confirm it's 3.3V, NOT 5V; 5V on these pins can damage the board).
2. Wire only 3 wires, crossed: adapter `GND`↔board `GND`, adapter
   `RXD`↔board `TXD`, adapter `TXD`↔board `RXD`. **Do not connect the
   adapter's own 5V/VCC pin to the board** — the camera is powered
   separately via its own USB-C port.
3. Open a serial terminal at **921600 baud** (confirmed correct rate —
   see update above; the usual 115200 default does NOT work on this
   board).
4. Power-cycle the camera (unplug/replug its USB-C) while the terminal is
   open and watch for boot log output immediately.
5. If a login prompt appears, try common defaults for this device class:
   `root`/`root`, `root`/(blank), `admin`/`admin`, `root`/`12345`.

Record whatever appears (minus any credential it reveals — see the
redaction note in `docs/protocol.md`).

## The other next step: root the phone

If UART access doesn't pan out, or alongside it: **root the phone** (or
get a rooted/debuggable test device with the same app), then:

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
