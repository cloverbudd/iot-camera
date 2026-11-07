# UART findings (2026-11-07)

## Hardware

- Mainboard silkscreen: `X8-V1.1-26811`, 3-pin header labeled `TXD RXD GND`.
- Confirmed **not** a 5V part: this SoC's I/O is 3.3V. Used an FTDI FT232RL
  breakout (3.3V/5V switchable, set to **3.3V**) with three bare jumper
  wires push-fit into the unpopulated through-holes (no header soldered).
- Wiring (crossed): board `TXD` → adapter `RXD`, board `RXD` → adapter
  `TXD`, board `GND` → adapter `GND`. Adapter `VCC` left disconnected —
  the camera is powered via its own USB-C.

## Baud rate

**921600 8N1** is the correct rate for this board's live debug console.
Confirmed by a baud sweep (9600 through 1,500,000) while the camera was
already running — 921600 gave 95%+ printable ASCII and recognizable log
lines; every other rate produced garbage or a consistent-but-garbled
repeating pattern (a sign of a real signal at the wrong rate, not just
electrical noise).

Lower rates (115200 etc.) that are the usual default for boot consoles on
this class of board did **not** work here — this device's whole boot +
app debug stream appears to run at 921600 throughout (we did not catch a
separate, slower bootloader stage — see "Open questions" below).

## Connection reliability (important for next person)

Push-fit bare wire into unsoldered through-holes is **unreliable** at
921600 baud. Symptoms seen across repeated attempts:
- Totally random noise, no structure (classic loose/floating contact —
  most often traced to a shaky `GND`).
- A cleanly repeating ~170-byte garbled block (same bytes recurring) —
  this looked like noise at first but was actually a real signal doing
  something periodic, just interpreted at the wrong baud at the time.
- Corrupted/truncated JSON mid-line even once the right baud was found —
  other debug lines get interleaved into the middle of a JSON blob
  (`CZ_P2P_JsonSendBackEx`) when bytes drop, which happens more at
  921600 than it would at a slower rate.

**Recommendation for the next session: solder a 3-pin male header into
the TXD/RXD/GND holes.** It's a 2-minute job with a cheap iron and turns
an intermittent, hand-held connection into a clean plug-in one — directly
reduces byte-drop/corruption at this baud.

Before trusting any capture, verify the whole chain is sound with a pure
software **loopback test** (jumper the adapter's own TXD to its own RXD,
`camera disconnected entirely`, write a known string, read it back). This
isolates "is my FTDI/driver/capture command even working" from "is the
camera-side wiring OK" — we used this once, it confirmed the FTDI+Linux
side was never the problem, only the camera-side wire quality was.

## What the console shows (steady state)

Confirmed **readable, live firmware debug output**, not just a boot
burst — it keeps streaming continuously while the camera runs normally.
Logs seen include:

- Wi-Fi stack diagnostics: `chip-temperature`, RSSI, TX/RX frame counts,
  throughput, per-STA stats (`sta:<mac>, aid:0, rssi:...`).
- Video pipeline stats: `[JPG_SIZE][JPG0] frames=100 avg=... min=... max=...`
  — confirms this log stream runs concurrently with live video encoding.
- P2P/relay session state, directly matching the `libapTrans_jni.so`
  internals we'd already reverse engineered from the phone side:
  ```
  P2PJNI  :_dev_recv_alive  cmd:34
  P2PJNI  :qwe..._dev_recv_alive()
   alloc_relay=0 one_svr=0 force_one_svr=0 force_tcp=0 state=6 nat=0 idx=0
   svr_alive_arrhythmia_cnt=0 bw_out=4077 bw_in=0
  ```
- Full-device JSON status blobs via `CZ_P2P_JsonSendBackEx` — this is the
  **plaintext** command/response JSON *before* it gets wrapped in
  whatever wire encryption the P2P layer applies. Confirmed field names
  and values for several command IDs:

  | cmd | meaning (inferred) | notable fields |
  |-----|---------------------|-----------------|
  | 100 | device info / capabilities | `admin`, `mode`, `pushMode`, `checkstr:"SHIX"`, `switchResolution`, `supportSD`, `p2pChannel:4`, `isApMode`, **`cloudKey:"183C88"`**, `shareAuth` |
  | 101 | device status | `tz:28800`, `time`, `stream`, `sysver:"AP_TTWO_PONE-8"`, `productName:"AP_TTWO_PONE"`, `rotmir`, `sdstatu`, `mic`, `spk`, `alarmSwitch`, `res:"640*480"`, `vcodec` |
  | 103 | factory/hardware info | `prover`, `factory:"CYCZ"`, `product`, `chip:"TXW816"`, `sensor:"GC0307"` |
  | 107 | (seen, fields not fully captured due to corruption) | |
  | 111 | (seen, fields not fully captured due to corruption) | |
  | 126 | generic ack | `result:0` |
  | 715 | battery push notify | `pro:"notify_bat"`, `batstatus`, `batvalue` |

  Also observed: PIR config fields (`pirDelayTime:180`, `pirPush`,
  `pirenable`, `pirsensitive`, `pirvideotime:60`) and a flash-write
  sequence logged right after cmd 715 (`erase flash`, `write flash`,
  `verify flash ... OK`, `switch syscfg partition ... OK`,
  `syscfg_write OK!`) — confirms device settings are persisted to a
  `syscfg` flash partition, useful if we ever want to read/dump that
  partition directly instead of going through the app.

**Hardware IDs now fully pinned down**: SoC/chip `TXW816`, image sensor
`GC0307`, factory code `CYCZ`, product line `AP_TTWO_PONE`, firmware
`AP_TTWO_PONE-8`.

## Open questions / not yet found

- **No raw session/encryption key material surfaced** in ~2 minutes of
  steady-state + live-app-interaction capture. Two explanations, not yet
  distinguished:
  1. Key derivation happens too fast / too early (e.g. only during the
     very first P2P handshake moment right at boot) and our captures
     started after that window.
  2. The native `.so`'s key material is never printed via this log path
     at all (plausible — the log calls we're seeing are a different,
     higher-level status/JSON layer, not inside `e_init`/`m_init` etc.).
- A cold-boot capture (camera unpowered → power on while capturing →
  immediately open app) did **not** catch useful output — got a short
  noise burst then nothing, consistent with the wire jostling loose
  during the physical plug/unplug action (see reliability notes above),
  not conclusive either way on question 1.
- **Next attempt should use a soldered header** before trying the
  cold-boot window again, to rule out "wire came loose during handling"
  as the reason nothing useful showed up.

## Files

- `logs/uart_steady_state_921600.log` — ~20s steady-state capture,
  99.5% printable, clean.
- `logs/uart_app_interaction_921600.log` — ~90s capture spanning a live
  phone-app connect/view session, 99.3% printable but with some
  mid-stream corruption (see reliability notes).
