# Bullet Force Probe

This is an isolated, read-only research utility. It does not modify Bullet Force, attach to its process, create rooms, bypass TLS or authentication, or collect credentials. It only inventories a local installation and analyzes a HAR file exported by the owner's browser.

## 1. Inspect the local installation

From the repository root:

```bash
mkdir -p tools/bullet_force_probe/captures
.venv/bin/python tools/bullet_force_probe/probe.py inspect
```

The command writes `captures/install-scan.json` and prints the detected runtime. It checks common macOS locations, including CrossOver. To select another location without changing the game:

```bash
BFC_BULLET_FORCE_ROOT="$HOME/path/to/Bullet Force" \
  .venv/bin/python tools/bullet_force_probe/probe.py inspect
```

The string scan is limited to networking, room, lobby, matchmaking, region, map, mode, player-limit, ping, and related terms. It does not dump whole binaries.

## 1b. Analyze the confirmed IL2CPP build

For the current Steam install, run this read-only scan:

```bash
.venv/bin/python tools/bullet_force_probe/probe.py analyze-il2cpp \
  --root "/Users/admin/Library/Application Support/CrossOver/Bottles/Steam/drive_c/Program Files (x86)/Steam/steamapps/common/Bullet Force"
```

It reads only `GameAssembly.dll`, `UnityPlayer.dll`, and `Bullet Force_Data/il2cpp_data/Metadata/global-metadata.dat`, then writes `captures/create-match-flow.md`. Nearby printable strings are correlation hints, not proof of execution or call order.

## 1c. Map exact Create Match methods

Run the focused metadata mapper:

```bash
.venv/bin/python tools/bullet_force_probe/probe.py map-create-match \
  --root "/Users/admin/Library/Application Support/CrossOver/Bottles/Steam/drive_c/Program Files (x86)/Steam/steamapps/common/Bullet Force"
```

It pairs the version-31 method, parameter, and type-definition tables in `global-metadata.dat` offline and writes `captures/create-match-method-map.md`. It does not infer native callees or execute the client. `GameAssembly.dll` is recorded as part of the known IL2CPP installation, but no native code is run or instrumented.

## 2. Capture the browser flow

Use a supported Chromium browser and the official web client only. Do not install a certificate, accept a certificate warning, disable TLS checks, or paste tokens/cookies anywhere.

1. Open Bullet Force and sign in normally.
2. Open Developer Tools, choose **Network**, enable **Preserve log**, and clear the existing entries.
3. Start the recording before opening the custom-match screen. Filter for `WS` or `websocket` if a socket appears; otherwise leave the filter empty.
4. Create exactly one private test lobby with name `BFC-PROBE-001`, mode TDM, map Outpost, region Europe, max players 6, maximum max ping, and Hardcore off.
5. Select the request that occurred at that moment. For HTTP, use **Save all as HAR with content**. For WebSocket, inspect **Messages/Frames** and use the browser's copy control for the relevant outgoing frame only. Do not copy headers, cookies, local storage, or the full page.
6. Save the HAR as `tools/bullet_force_probe/captures/bfc-probe-001.har`. If the marker is visible only in a WebSocket frame, copy only the relevant outgoing frame(s), one per line, to `tools/bullet_force_probe/captures/bfc-probe-001-frames.jsonl`; omit all headers and unrelated frames.

For copied WebSocket frames, run:

```bash
.venv/bin/python tools/bullet_force_probe/probe.py analyze-frames \
  tools/bullet_force_probe/captures/bfc-probe-001-frames.jsonl
```

Send back `captures/bfc-probe-001-analysis.json` for HTTP or `captures/bfc-probe-001-frame-analysis.json` for WebSocket frames, along with `captures/install-scan.json`.

HAR files can include sensitive data even after the analyzer redacts it. Keep the original local and send only the generated analysis file. The analyzer redacts headers and fields whose names indicate cookies, authorization, tokens, sessions, secrets, credentials, or passwords.

Run:

```bash
.venv/bin/python tools/bullet_force_probe/probe.py analyze-har \
  tools/bullet_force_probe/captures/bfc-probe-001.har
```

Send back only `tools/bullet_force_probe/captures/bfc-probe-001-analysis.json` and `tools/bullet_force_probe/captures/install-scan.json`. If the browser exposes only WebSocket frames and no HAR request contains the marker, send a manually created text file containing just the copied outgoing frame, with sensitive headers omitted; do not include cookies or tokens. The current analyzer will then need a small follow-up adapter for that frame format.

## Safety boundary

The output can identify whether the client uses Mono/IL2CPP, Photon/WebSocket-related artifacts, and the request/frame carrying the test room marker. It intentionally does not replay, mutate, or generate any request. A protocol that requires authenticated proprietary services, signed state, or server-side authorization is not considered externally reproducible merely because its fields are visible.