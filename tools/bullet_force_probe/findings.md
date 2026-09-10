# Bullet Force probe findings

This document is intentionally a research record, not an implementation of room creation. It will be updated from the generated reports in `captures/` after the owner runs the probe.

## Current local evidence

- Networking technology: not established. The discovered path is `/Users/admin/Applications/CrossOver/Steam/Bullet Force.app`; it contains only a CrossOver `Menu Helper` wrapper and localized resources, with no Photon, WebSocket, Unity, Mono, or IL2CPP artifact in the scanned 46 files.
- Runtime: not established from this path. The scanner distinguishes strong Mono indicators (`Assembly-CSharp.dll`/Managed artifacts) from IL2CPP indicators (`GameAssembly.dll`/`global-metadata.dat`). A CrossOver wrapper alone is not evidence of either runtime. The actual Steam/CrossOver bottle or browser client still needs to be located if native inspection is required.
- Room creation origin: not established yet. Analyze the browser HAR or the narrowly copied outgoing WebSocket frame after creating `BFC-PROBE-001` manually.
- Relevant room properties: not established yet. Record exact keys and value types from the redacted analysis, including name, mode, map, region, max players, max ping, and hardcore state.
- Legitimate external reproduction: unknown. Visibility of a client message does not imply that an external service may replay it; authentication, signatures, ownership, protocol version, and server authorization must remain unresolved until documented by the game provider.

## Unknowns to resolve

- Whether the browser uses Photon directly, a WebSocket gateway, or an HTTPS API that then drives a game socket.
- Whether `BFC-PROBE-001` appears in a create-room request, a room-properties update, or only in a later server response.
- Which values are client-selected versus assigned by the service.
- Whether the service rejects messages from anything other than the official authenticated client.

No room-creation code belongs in this research utility.