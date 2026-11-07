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

## UPDATE 2026-11-07 (second session): full cold boot captured — key hunt via UART is CONCLUSIVELY CLOSED

A clean, complete cold-boot capture succeeded (~19KB, 99.5% printable,
no corruption) covering: full RF/PHY init, the camera's own Wi-Fi
association + WPA 4-way handshake to the home AP, sensor/CSI init,
`hgSDK-v2.5.1.7-26693` banner, `fw: AP_TTWO_PONE v8 boot 692ms`, P2P
module startup (`P2PJNI :--->20260811-1`), and the full P2P
alive/relay state machine cycling through `state=2` → `3` → `4` → `5` →
`6` (`alloc_relay`/`nat`/`force_tcp` flags) exactly as seen in
steady-state logs.

**The control-channel / P2P session encryption key never appears
anywhere in this log**, including through the entire P2P init sequence.
The only key material logged at all is the camera's own **Wi-Fi WPA
PTK/GTK** (`hgkey: cipher=... keylen=16 key=...`, `RSN: added PMKID: ...`)
for its connection to the home router — unrelated to the P2P/cloud
cipher we need, and redacted from the committed log
(`logs/uart_coldboot_redacted.log`) since it's real (if ephemeral,
session-derived) key material for a real network.

**Conclusion: UART is not a viable path to the P2P/control-channel
session key.** The vendor's `P2PJNI`/`libapTrans_jni.so` logging only
ever prints status codes and public JSON fields over this console, never
key bytes — this isn't a capture-reliability problem (this run was
clean), it's that the firmware genuinely doesn't log it here. **Root the
phone — see "The other next step" below — is now the only remaining
path for the session key.**

What UART *is* still useful for, independent of the key:
- Confirming/debugging the device's Wi-Fi connection state live.
- The plaintext JSON protocol fields (still valuable, see table above).
- Dumping the `syscfg` flash region directly if we ever want the
  persisted (non-ephemeral) config without going through the key at all
  — observed read at boot (`syscfg: invalid magic_num=0, addr=fe000` →
  `syscfg_read OK!`) and writes at `addr:fe000`/`addr:ff000` (alternating,
  likely A/B wear-leveling), `crc`-checked, 1012 bytes. This is a
  possible alternate path worth a dedicated flash-dump session later if
  the phone-root path stalls, but it's config data, not a crypto key —
  don't expect the session key to live here either.

## Files

- `logs/uart_steady_state_921600.log` — ~20s steady-state capture,
  99.5% printable, clean.
- `logs/uart_app_interaction_921600.log` — ~90s capture spanning a live
  phone-app connect/view session, 99.3% printable but with some
  mid-stream corruption (see reliability notes).
- `logs/uart_coldboot_redacted.log` — full clean cold-boot capture
  (~19KB, 99.5% printable). **Wi-Fi WPA PTK/GTK key bytes and the home
  AP's SSID are redacted** (`[REDACTED-KEY-MATERIAL]` /
  `[REDACTED-SSID]`) before commit — this is real, if ephemeral,
  session key material for a real network and must never be published
  verbatim. Everything else (boot banner, P2P init, JSON command dumps,
  flash writes) is left intact.
