# Investigation log — dead ends, pitfalls, and why they don't need repeating

Chronological summary across multiple sessions. The goal of this file is
to stop a future session (yours, with a rooted phone) from re-walking the
same dead ends.

## Session 1-2: cipher structure, confirmed NOT textbook AES

- Early assumption "this is AES-128-ECB" was wrong and cost real time: the
  cipher init function `e_init(ctx, key_ptr, table_ptr)` takes **two**
  16-byte buffers, not one. Textbook AES-128 key expansion takes only a
  key. **Always check a disassembled crypto function's full argument list
  against the real algorithm's signature before assuming a match** — an
  AES-shaped S-box/round-constant table in the disassembly is not proof
  it's standard AES.
- Built a full oracle toolchain to run the vendor's Android `.so` natively
  on a Linux ARM64 host via `dlopen()`:
  - `patch_so.py` strips Android ELF version requirements (`DT_VERNEED`
    etc.) that glibc's dynamic linker rejects.
  - `bionic_compat.c` stubs the handful of bionic-only symbols the lib
    needs (`__sF`, fortified string functions, `__system_property_get`,
    `__errno` as TLS).
  - `liblog_stub.c` stubs `__android_log_print`/`write`.
  - This infra is sound and reusable — confirmed by successfully running
    real vendor code and reproducing its exact logged output.
- Extracted a key/table via `gdb` breakpoints on `e_init`, single-stepping
  the live call during `hl_p2p_init()`. Got real register/memory values,
  cross-validated the cipher implementation as internally correct (our
  reimplementation matched the vendor's own compiled `hl_encrypt` output
  byte-for-byte). **Still did not decrypt real captured ciphertext, even
  with a fresh, 8ms-gap, single-session-synchronized capture.** This
  ruled out "stale/mismatched pairing" as the explanation. Current best
  theory: the key captured at `hl_p2p_init()` time differs from the key
  actually used by a later `hl_p2p_write()` call in a real session (extra
  entropy from the real P2P handshake not replicated in a standalone
  oracle call). See `STATUS.md`.
- Tried a 1836-combination byte-orientation sweep (reversed, upper/lower,
  hex-decoded-from-ASCII, swapped key/table roles) of the gdb-extracted
  values — no match. **Do not repeat this specific style of guessing** —
  the problem is a missing runtime input, not a misread static byte
  layout.

## Session 3: cold-start capture, BLE pairing, Java-layer trace

- `pm clear com.shix.hk365` + re-pair forces the camera's WiFi password
  and a factory device password into `adb logcat` in plaintext (`pairing
  network info:` JSON line). **Never print/store these values** — this
  is a real risk every time you force a cold-start capture on this app.
- Smali-traced `P2PManager.connect(did)` → `NativeCaller.AnPanStartPPPP(did,
  "", "")` — **only the DID is passed from Java**, proving all
  discovery/session state lives entirely in native code, not cached by
  the Java layer or in SharedPreferences. Don't waste time looking for a
  cached port/token value on the Java side.
- Found the `0x2c` cloud-relay registration packet, hypothesized it's a
  required "tell the camera to expect this token" step. Built and tested
  the full discovery→registration→handshake sequence twice (fixing a
  device-blob consistency bug on the second try) — **both times got zero
  reply to the `0x2c` packet itself, and zero reply to the subsequent
  handshake.** Unresolved whether the packet's still-guessed fields are
  simply wrong, or the mechanism needs something else entirely.
- Captured BLE pairing traffic via `adb bugreport`'s bundled btsnoop log
  (no root needed: `settings put secure bluetooth_hci_log 1` + toggle
  bluetooth + re-pair + `adb bugreport`). Decoding the raw GATT chunking
  byte-by-byte was started but not finished — not necessary since the
  app's own logcat already gives the decoded provisioning JSON.

## Session 4: identified the public PPPP protocol family

- Recognized native symbol names (`cs2p2p_PPPP_*`, `PPCS_*`) and a
  `"checkstr":"SHIX"` field as matching the publicly documented PPPP/CS2
  Network protocol family exactly — a huge research shortcut (Wireshark
  dissectors, known PSK tables, a documented-but-weak cipher already
  exist publicly for this family).
- Extracted the exact 64-byte (later found to be 256-byte) cipher table
  directly from the binary via disassembly of
  `__P2P_Proprietary_SelectTableElement` — matched the public reference
  table byte-for-byte once the FULL 256 bytes were read (an early mistake
  only read 64 of 256, which is enough to look identical but not enough
  to actually decrypt anything with real-world byte values above 63).
- Built `decrypt_oracle.c`, calling the REAL
  `cs2p2p__P2P_Proprietary_Decrypt` function directly via the dlopen
  oracle, with PSK `"SHIX"`, against a real, precisely logcat-paired
  `check_user` ciphertext — tried all 20 possible header-strip offsets,
  **no match**. This result held up and was later explained correctly in
  session 6 (wrong function entirely for this message type, not a
  wrong offset).

## Session 5: proved the public blanket cipher IS correct, but only for `0x2c`

- Ported the exact public reference `pppp_decrypt`/`pppp_encrypt`
  algorithm (simple single-byte-chaining XOR keystream — NOT the more
  complex multi-byte state initially guessed from partial disassembly;
  the simple model was right, the issue was the wrong PSK).
- **Validated**: the `0x2c` registration packet decrypts to exactly
  `0xf1` (the universal PPPP magic byte) using PSK `"camera"`. Both the
  algorithm and the extracted table are proven correct.
- **Brute-forced every documented/guessed PSK against the `0x28` query and
  `0x11`/`0x0b` LAN handshake packets — none matched `0xf1`.** This
  **confirms** (not just assumes) those message types are genuinely
  unencrypted custom framing on this vendor fork, not obfuscated.

## Session 6: definitively located the real control-channel cipher call

- Disassembled the real send path precisely: `cs2p2p_PPPP_DRW_Send` writes
  the standard public-protocol envelope (`[0xF1][opcode][len:2BE]` +
  `[0xD1][channel][index:2BE]` + data) and calls `cs2p2p_SendMessage(key,
  ...)`, which conditionally runs the WHOLE packet through
  `cs2p2p__P2P_Proprietary_Encrypt` **only if a non-empty key argument was
  passed by the caller.**
- **Brute-forced ~30 PSK/key candidates (full documented table +
  device-specific guesses + the live gdb-extracted session-1/2 key
  strings + a full 0-255 single-byte sweep) against the complete real
  captured wire packet, checking for the expected decrypted prefix `F1
  D0` — zero matches.** This proves DRW/command packets are NOT sent
  through this specific code path at all.
- Confirmed the device actually uses a DIFFERENT function,
  `HLP2P_Write`→`hl_p2p_write`, which calls `e_init`/`e_c_e_b` directly —
  the SAME function pair from sessions 1-2. This definitively closes the
  "maybe it's the public blanket cipher after all" question: it's the
  vendor's own undocumented `e_init`/`e_c_e_b`, confirmed by tracing the
  actual call graph, not by guessing.

## Net result

Every available static-analysis and offline-dynamic-analysis technique
(disassembly, symbol tracing, smali tracing, native oracle execution,
gdb single-stepping of a standalone call, BLE snoop capture, public
protocol cross-referencing) has been applied and has converged on one
specific, narrow, well-defined remaining question: **what's the real
session key `e_init` uses during an actual live `hl_p2p_write()` call**,
which — because the app is not debuggable and the phone has no root —
cannot be observed without a rooted device. See `STATUS.md`.

## General pitfalls worth remembering for next time

- **Two packets being close in timestamp does not prove one supplied data
  to the other.** A client with a cached value from a previous session
  will fire its next packet before an unrelated, merely-nearby reply
  shows up. Verify causal ordering (does the dependent packet's sender
  actually have the data yet?) before concluding "the handshake used the
  value from this reply."
- **Backgrounding a `sudo` command with `&` breaks the password prompt
  silently** (shows as state `T` in `ps aux`, no error). Run privileged
  commands in the foreground of a terminal the user controls directly.
- **PCAPdroid (and other non-root VPN-based Android capture tools) can
  see nothing from apps that pin sockets via `bindProcessToNetwork()`** —
  symptom: 100% of flows show "Unknown" attribution despite real traffic
  volume. This also hides the discovery/handshake exchange specifically,
  not just steady-state traffic attribution.
- **A host on a `/22` subnet must not broadcast to the `/24` address**
  (`192.168.4.255` is wrong on a `192.168.4.0/22` network) — use
  `255.255.255.255` or the correctly-derived broadcast address.
- **This camera is duty-cycled** (sleeps ~30s, wakes briefly) — a single
  discovery broadcast will often get nothing; repeat continuously.
