#!/usr/bin/env python3
"""Read-only Bullet Force installation and browser capture probe."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import struct
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


KEYWORDS = (
    "photon", "websocket", "room", "lobby", "matchmaking", "custom",
    "region", "map", "mode", "maxplayers", "max_players", "ping",
    "hardcore", "roomproperties", "roomprops", "create room", "joinroom",
)
IL2CPP_TERMS = (
    "FishNet", "NetworkManager", "ServerManager", "ClientManager", "TransportManager",
    "Transport", "StartConnection", "StartServer", "StartHost", "Tugboat", "Bayou",
    "Multipass", "FishySteamworks", "Steamworks", "Facepunch", "Lobby", "LobbyManager",
    "Matchmaking", "CreateMatch", "CreateLobby", "CustomMatch", "GameSettings",
    "MatchSettings", "RoomSettings", "Play", "password", "region", "map", "mode",
    "TDM", "max players", "maxplayers", "max ping", "score limit", "hardcore",
    "allowed weapons", "weapon restrictions", "weaponrestriction",
)
SECRET_KEY = re.compile(
    r"(?:authorization|cookie|set-cookie|token|secret|password|passwd|session|"
    r"auth|credential|x-api-key|access[_-]?token|refresh[_-]?token)", re.I
)
MARKER = "BFC-PROBE-001"
TARGET_METHODS = (
    "CreateMatch",
    "CreateMatchWithCoroutine",
    "SetMatchPassword",
    "SelectRegion",
    "SetIsNotJoiningToAMatch",
)


def candidate_roots() -> list[Path]:
    roots = []
    configured = os.environ.get("BFC_BULLET_FORCE_ROOT")
    if configured:
        roots.append(Path(configured).expanduser())
    home = Path.home()
    roots.extend(
        [
            home / "Applications/CrossOver/Steam/Bullet Force.app",
            home / "Library/Application Support/Steam/steamapps/common/Bullet Force",
            home / "Library/Application Support/Steam/steamapps/common/Bullet Force.app",
            home / "Applications/Bullet Force.app",
            Path("/Applications/Bullet Force.app"),
        ]
    )
    return list(dict.fromkeys(path for path in roots if path.exists()))


def files_under(root: Path) -> Iterable[Path]:
    if root.is_file():
        yield root
        return
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink():
            yield path


def classify(root: Path, paths: list[Path]) -> dict[str, Any]:
    names = {path.name.lower() for path in paths}
    has_mono = any(name in names for name in ("assembly-csharp.dll", "managed"))
    has_il2cpp = "gameassembly.dll" in names or "global-metadata.dat" in names
    networking = [
        str(path.relative_to(root))
        for path in paths
        if any(term in path.name.lower() for term in ("photon", "websocket", "network", "socket"))
    ]
    if has_il2cpp:
        runtime = "IL2CPP (strong indicators found)"
    elif has_mono:
        runtime = "Mono (strong indicators found)"
    else:
        runtime = "Unknown (wrapper or incomplete installation)"
    return {"root": str(root), "runtime": runtime, "networking_files": networking[:100]}


def strings_from_file(path: Path) -> Iterable[str]:
    try:
        data = path.read_bytes()
    except OSError:
        return
    ascii_strings = re.findall(rb"[\x20-\x7e]{4,}", data)
    utf16_strings = re.findall(rb"(?:[\x20-\x7e]\x00){4,}", data)
    for item in ascii_strings:
        yield item.decode("ascii", "replace")
    for item in utf16_strings:
        yield item.decode("utf-16le", "replace")


def ordered_strings(path: Path) -> list[str]:
    try:
        data = path.read_bytes()
    except OSError:
        return []
    values: list[tuple[int, str]] = []
    for match in re.finditer(rb"[\x20-\x7e]{3,}", data):
        values.append((match.start(), match.group().decode("ascii", "replace")))
    for match in re.finditer(rb"(?:[\x20-\x7e]\x00){3,}", data):
        values.append((match.start(), match.group().decode("utf-16le", "replace")))
    return [value for _, value in sorted(values)]


def il2cpp_paths(root: Path) -> list[Path]:
    candidates = [
        root / "GameAssembly.dll",
        root / "UnityPlayer.dll",
        root / "Bullet Force_Data/il2cpp_data/Metadata/global-metadata.dat",
    ]
    return [path for path in candidates if path.is_file()]


def is_readable(value: str, native: bool) -> bool:
    if not 3 <= len(value) <= 160 or any(ord(char) < 32 for char in value):
        return False
    if native and not re.fullmatch(r"[A-Za-z0-9_.$:/\\()<> -]+", value):
        return False
    return sum(char.isalpha() for char in value) >= 3


def term_matches(value: str, term: str) -> bool:
    if len(term) <= 3:
        return value == term
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", value, re.I) is not None


def matching_context(values: list[str], terms: tuple[str, ...], radius: int = 5) -> list[dict[str, Any]]:
    results = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for index, value in enumerate(values):
        if not any(term_matches(value, term) for term in terms):
            continue
        context = tuple(values[max(0, index - radius): index + radius + 1])
        key = (value, context)
        if key in seen:
            continue
        seen.add(key)
        results.append({"match": value, "nearby_strings": list(context)})
    return results


def markdown_bullets(items: list[dict[str, Any]], limit: int = 14) -> str:
    if not items:
        return "- No matching printable strings were found."
    lines = []
    for item in items[:limit]:
        lines.append(f"- `{item['match']}`; nearby: " + ", ".join(f"`{value}`" for value in item["nearby_strings"]))
    if len(items) > limit:
        lines.append(f"- ... {len(items) - limit} additional contexts omitted from this concise report.")
    return "\n".join(lines)


def analyze_il2cpp(root: Path, output: Path) -> None:
    paths = il2cpp_paths(root)
    all_matches: dict[str, list[dict[str, Any]]] = {}
    readable_values: list[str] = []
    for path in paths:
        values = [value for value in ordered_strings(path) if is_readable(value, path.name != "global-metadata.dat")]
        readable_values.extend(values)
        all_matches[str(path.relative_to(root))] = matching_context(values, IL2CPP_TERMS)

    flat = [item for matches in all_matches.values() for item in matches]
    fishnet_terms = IL2CPP_TERMS[:15]
    lobby_terms = IL2CPP_TERMS[15:25]
    settings_terms = IL2CPP_TERMS[25:]
    def has_any(item: dict[str, Any], terms: tuple[str, ...]) -> bool:
        return any(term_matches(item["match"], term) for term in terms)

    fishnet = [item for item in flat if has_any(item, fishnet_terms) and has_any(item, ("FishNet", "FishyUnityTransport", "Bayou.dll", "NetworkManager", "ServerManager", "ClientManager", "TransportManager", "StartConnection", "StartServer", "StartHost"))]
    lobby = [item for item in flat if has_any(item, ("CustomMatchMakerUI", "CreateMatch", "Matchmaking", "MatchMaker", "LobbyManager", "SteamAPI_ISteamMatchmaking_CreateLobby", "Steamworks|Lobby"))]
    settings = [item for item in flat if has_any(item, ("SetMatchPassword", "SelectRegion", "roomCustom", "selectedGameMode", "hardcoreToggle", "enableBotsToggle", "createMatchWithCustomMap", "ScoreLimits", "allowedWeapons", "GameSettingsLocal", "GamemodeSettings", "MaxPlayers", "maxPlayers"))]
    ui = [item for item in flat if has_any(item, ("CreateMatch", "CustomMatch", "MatchSettings", "GameSettings", "RoomSettings", "Play_CreateMatch"))]
    play = [item for item in flat if has_any(item, ("Play_CreateMatch", "Play_JoinMatch", "Header_PlayButton", "Play_Quickplay"))]
    fishy_unity = any("fishyunitytransport" in value.lower() for value in readable_values)
    fishy_steam = any("fishysteamworks" in value.lower() for value in readable_values)
    transport_summary = "Static evidence points to FishyUnityTransport." if fishy_unity else "No FishyUnityTransport string was found."
    if fishy_steam:
        transport_summary += " FishySteamworks is also present, so runtime selection remains unresolved."
    else:
        transport_summary += " No FishySteamworks string was found in the curated results, but this does not prove it is absent from all assets."
    evidence = "\n".join(
        f"- `{path}`: {len(matches)} relevant string contexts"
        for path, matches in all_matches.items()
    ) or "- None of the three expected IL2CPP files was found."
    report = f"""# Create Match flow: static IL2CPP evidence

This report was generated by a read-only scan of the supplied Bullet Force installation. Printable strings are evidence of embedded names or text only; they do not establish that a method executes, nor do they prove call order.

Scanned files:
{evidence}

FishNet transport:
{transport_summary} FishNet class names and a transport dependency are confirmed by metadata; the selected runtime transport still requires observing the configured component or connection path.

{markdown_bullets(fishnet)}

Lobby/matchmaking system:
The following strings are the static candidates for lobby, matchmaking, and custom-match ownership. No exact owner is asserted unless a class/method name is explicitly present in the evidence.

{markdown_bullets(lobby)}

Create Match UI/controller:
Static candidates containing `CreateMatch`, `CustomMatch`, `MatchSettings`, `GameSettings`, or related names are listed below. IL2CPP metadata may preserve type/method names, but this scanner cannot prove which Unity object owns the visible menu.

{markdown_bullets(ui)}

PLAY button handler:
No exact handler is claimed from string proximity alone. Search results containing `Play` are included as raw evidence below; `Play` is a common UI label and needs a runtime observation or a complete IL2CPP metadata-to-method mapping to identify the handler.

{markdown_bullets(play)}

Likely call chain:
UI → [unknown Create Match controller] → [unknown lobby/matchmaking service] → [unknown server/session step] → FishNet connection/startup. The static scan does not establish these edges or their order.

Client-hosted or dedicated-hosted:
Unknown from static strings. A FishNet transport dependency does not determine hosting topology. This requires observing whether the client invokes a server-start/host path locally or only receives connection/session details from a backend.

Match settings object:
Potential setting/type names and nearby strings are listed here. Values, field IDs, and serialization format are not established by this scan.

{markdown_bullets(settings)}

Known internal setting names/IDs:
No setting IDs are asserted. The exact strings found near the requested terms are the only confirmed names:

{markdown_bullets(settings, limit=80)}

Authentication/session requirement:
Unknown from static metadata. Presence of Steamworks/Firebase/auth-related strings can show dependencies, but cannot prove whether lobby creation requires a running authenticated client.

Confidence:
- High: the listed strings are embedded in one of the scanned files.
- Low: ownership, execution, call order, host topology, setting values, and authentication conclusions.

Unknowns:
- Exact PLAY handler and immediate callees.
- Whether lobby registration/listing is backend HTTP, Steamworks, FishNet server code, or a combination.
- Selected FishNet transport and its runtime configuration.
- Setting field names/IDs and serialization.
- Whether the client starts a local host or joins a dedicated server.

Safest next diagnostic step:
Use only the owner's client and one newly created private lobby. Record a timestamped screen capture and the client's own outbound connection metadata with an OS-level connection listing, without TLS interception, process injection, token extraction, or replay. Compare the connection endpoints immediately before and after pressing PLAY, then provide only redacted metadata and the generated static scan. Do not capture cookies, authorization headers, session IDs, access tokens, or other players' traffic.
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(f"Scanned {len(paths)} IL2CPP files; wrote {output}")


class MetadataReader:
    """Decode the version-31 metadata tables needed by the focused mapper."""

    def __init__(self, path: Path) -> None:
        self.data = path.read_bytes()
        self.sanity, self.version = struct.unpack_from("<II", self.data, 0)
        self.tables = [struct.unpack_from("<II", self.data, index * 4) for index in range(2, 60, 2)]
        self.string_offset, self.string_size = self.tables[2]
        self.method_offset, self.method_size = self.tables[5]
        self.parameter_offset, self.parameter_size = self.tables[10]
        self.type_offset, self.type_size = self.tables[19]
        self.field_offset, self.field_size = self.tables[11]

    def string(self, index: int) -> str:
        if index >= self.string_size:
            return f"<string-index 0x{index:x}>"
        end = self.data.find(b"\0", self.string_offset + index)
        if end < 0:
            return f"<unterminated-string 0x{index:x}>"
        return self.data[self.string_offset + index:end].decode("utf-8", "replace")

    def type_record(self, index: int) -> tuple[Any, ...] | None:
        size = 88
        if index < 0 or self.type_offset + (index + 1) * size > len(self.data):
            return None
        return struct.unpack_from("<17I8H I", self.data, self.type_offset + index * size)

    def type_name(self, index: int) -> str:
        record = self.type_record(index)
        if record is None:
            return f"<type-index 0x{index:x}>"
        name, namespace = self.string(record[0]), self.string(record[1])
        return f"{namespace}.{name}" if namespace else name

    def type_by_value_index(self, index: int) -> str | None:
        for type_index in range(self.type_size // 88):
            record = self.type_record(type_index)
            if record is not None and record[2] == index:
                return self.type_name(type_index)
        return None

    def method_record(self, index: int) -> tuple[Any, ...]:
        return struct.unpack_from("<7I4H", self.data, self.method_offset + index * 36)

    def methods(self) -> Iterable[tuple[int, tuple[Any, ...]]]:
        for index in range(self.method_size // 36):
            yield index, self.method_record(index)

    def parameter(self, index: int) -> tuple[int, int, int]:
        return struct.unpack_from("<3I", self.data, self.parameter_offset + index * 12)

    def method_info(self, index: int, record: tuple[Any, ...]) -> dict[str, Any]:
        name_index, declaring, return_type, _, parameter_start, _, token, flags, iflags, slot, parameter_count = record
        parameters = []
        for parameter_index in range(parameter_start, parameter_start + parameter_count):
            name, type_index, parameter_token = self.parameter(parameter_index)
            parameters.append(
                {
                    "name": self.string(name),
                    "type_index": type_index,
                    "type": self.type_by_value_index(type_index) or f"<unresolved type-index 0x{type_index:x}>",
                    "token": f"0x{parameter_token:08x}",
                }
            )
        return {
            "index": index,
            "name": self.string(name_index),
            "declaring_index": declaring,
            "declaring_type": self.type_name(declaring),
            "return_type_index": return_type,
            "return_type": self.type_by_value_index(return_type) or f"<unresolved type-index 0x{return_type:x}>",
            "parameter_start": parameter_start,
            "parameter_count": parameter_count,
            "parameters": parameters,
            "token": f"0x{token:08x}",
            "flags": flags,
            "slot": slot,
        }

    def target_methods(self) -> dict[str, list[dict[str, Any]]]:
        result = {name: [] for name in TARGET_METHODS}
        for index, record in self.methods():
            name = self.string(record[0])
            if name in result:
                result[name].append(self.method_info(index, record))
        return result

    def methods_for_type(self, declaring_index: int) -> list[dict[str, Any]]:
        return [self.method_info(index, record) for index, record in self.methods() if record[1] == declaring_index]

    def field_candidates(self) -> list[dict[str, str]]:
        terms = ("matchname", "matchpassword", "maxplayers", "roomcustom", "selectedgamemode", "hardcore", "allowedweapons", "scorelimit", "region", "map", "mode", "player", "ping", "weapon", "match")
        candidates = []
        for index in range(self.field_size // 12):
            name_index, type_index, token = struct.unpack_from("<3I", self.data, self.field_offset + index * 12)
            name = self.string(name_index)
            if any(term in name.lower() for term in terms):
                candidates.append({
                    "name": name,
                    "type_index": f"0x{type_index:x}",
                    "type": self.type_by_value_index(type_index) or "<unresolved>",
                    "token": f"0x{token:08x}",
                })
        return sorted(candidates, key=lambda item: (not any(item["name"].lower() == term for term in terms), item["name"].lower()))

    def enum_candidates(self) -> list[str]:
        terms = ("map", "region", "mode", "score", "limit", "game")
        names = []
        for index in range(self.type_size // 88):
            name = self.type_name(index)
            if any(term in name.lower() for term in terms) and name not in names:
                names.append(name)
        return names


def format_signature(method: dict[str, Any]) -> str:
    parameters = ", ".join(f"{item['type']} {item['name']}" for item in method["parameters"])
    return f"{method['return_type']} {method['declaring_type']}.{method['name']}({parameters})"


def map_create_match(root: Path, output: Path) -> None:
    metadata_path = root / "Bullet Force_Data/il2cpp_data/Metadata/global-metadata.dat"
    reader = MetadataReader(metadata_path)
    if reader.version != 31:
        raise ValueError(f"Unsupported metadata version {reader.version}; expected 31")
    targets = reader.target_methods()
    primary = targets["CreateMatch"][0] if targets["CreateMatch"] else None
    coroutine = targets["CreateMatchWithCoroutine"][0] if targets["CreateMatchWithCoroutine"] else None
    declaring_index = primary["declaring_index"] if primary else (coroutine["declaring_index"] if coroutine else -1)
    same_type = reader.methods_for_type(declaring_index) if declaring_index >= 0 else []
    ordered_names = [method["name"] for method in same_type]
    method_position = {method["name"]: index for index, method in enumerate(same_type)}
    nearby = []
    if "CreateMatchWithCoroutine" in method_position:
        position = method_position["CreateMatchWithCoroutine"]
        nearby = same_type[max(0, position - 5):position + 6]
    fields = reader.field_candidates()
    field_lines = "\n".join(
        f"- UNKNOWN association: `{field['name']}`; type `{field['type']}`; type index `{field['type_index']}`; token `{field['token']}`"
        for field in fields[:40]
    ) or "- No matching field names found."
    enum_lines = "\n".join(f"- UNKNOWN enum/type candidate: `{name}`" for name in reader.enum_candidates()[:40]) or "- No matching enum/type names found."
    def method_block(name: str) -> str:
        methods = targets[name]
        if not methods:
            return f"UNKNOWN: no metadata method named `{name}` was found."
        return "\n".join(
            f"- CONFIRMED: metadata index `{method['index']}`, declaring type `{method['declaring_type']}` (type index `{method['declaring_index']}`), signature `{format_signature(method)}`, token `{method['token']}`, parameter count `{method['parameter_count']}`."
            for method in methods
        )

    report = f"""# Create Match method map

This report is generated offline from `global-metadata.dat` version `{reader.version}`. It does not execute, modify, inject into, or attach to Bullet Force. Metadata names and table relationships are marked confirmed; runtime execution, native addresses, and call edges are not inferred from string proximity.

CreateMatch declaring type:
{('CONFIRMED: `' + primary['declaring_type'] + '` (type index `' + str(primary['declaring_index']) + '`).') if primary else 'UNKNOWN.'}

Signature:
{('CONFIRMED: `' + format_signature(primary) + '`.') if primary else 'UNKNOWN.'}

CreateMatchWithCoroutine declaring type:
{('CONFIRMED: `' + coroutine['declaring_type'] + '` (type index `' + str(coroutine['declaring_index']) + '`).') if coroutine else 'UNKNOWN.'}

Signature:
{('CONFIRMED: `' + format_signature(coroutine) + '`.') if coroutine else 'UNKNOWN.'}

Relevant setters:
{method_block('SetMatchPassword')}
{method_block('SelectRegion')}
{method_block('SetIsNotJoiningToAMatch')}

Relevant fields:
{field_lines}
The field table exposes names, raw type indexes, and tokens, but this parser cannot prove that every candidate belongs to `CustomMatchMakerUI`; that class-to-field range is therefore UNKNOWN rather than guessed.

Relevant enums:
{enum_lines}
These are name matches only. Enum underlying values and actual use by the target methods are UNKNOWN.

Likely next call/service:
UNKNOWN from metadata-only method definitions. CONFIRMED adjacent method names in the same declaring type include:
{chr(10).join(f"- `{method['name']}`; signature `{format_signature(method)}`" for method in nearby)}

Immediate method ordering around `CreateMatchWithCoroutine`:
CONFIRMED metadata order is:
{chr(10).join(f"- `{method['index']}` `{method['name']}`" for method in nearby)}
Ordering is not a call graph. No FishNet, HTTP/WebSocket, Steam lobby, allocation, address, or port callee is confirmed by this table alone.

Native method/callee mapping:
UNKNOWN. Pairing the metadata with `GameAssembly.dll` is not enough by itself to prove calls without a native disassembler and reliable method-pointer registration mapping. This utility intentionally does not execute or instrument the game.

Authentication/session requirement:
UNKNOWN from static metadata. The presence of `BFRoomAuth`, `SendAuthRequest`, and `GetPasswordFromInput` near FishNet-related names is STRONG INFERENCE of an authenticated/session-aware path, not proof that external lobby creation is permitted.

Confidence:
- CONFIRMED: metadata version 31; target method names; declaring type index/name; return type names where the type table resolves them; parameter counts; method tokens; adjacent metadata ordering.
- STRONG INFERENCE: `CustomMatchMakerUI` is the Create Match controller and the method cluster is its UI/matchmaking surface; the class has FishNet-related fields/methods nearby.
- UNKNOWN: exact parameter types for the two setters where raw encoded type references do not resolve; field ownership; PLAY event binding; immediate callees; selected transport at runtime; host topology; backend protocol; authentication enforcement.

Unknowns before a Discord command could legitimately cause the authenticated client to create this match:
- Which authenticated client-side API or UI event must be invoked.
- How the Discord command would communicate with that already-running client without injection or bypassing authentication.
- Exact serialized settings keys/values and the server authorization/session handshake.
- Whether the client hosts locally or requests/joins a dedicated server.
- Whether any supported official integration exists; no external room-creation API has been established.
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(f"Mapped {sum(len(items) for items in targets.values())} target methods; wrote {output}")


def inspect_installation(root: Path, output: Path) -> None:
    paths = list(files_under(root))
    result = classify(root, paths)
    matches: list[dict[str, str]] = []
    for path in paths:
        if path.stat().st_size > 250 * 1024 * 1024:
            continue
        for value in strings_from_file(path):
            lowered = value.lower()
            if any(keyword in lowered for keyword in KEYWORDS):
                matches.append({"file": str(path.relative_to(root)), "value": value[:500]})
    result["file_count"] = len(paths)
    result["string_matches"] = matches[:5000]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("root", "runtime", "file_count", "networking_files")}, indent=2))
    print(f"String matches written to {output}")


def redact_url(value: str) -> str:
    parts = urlsplit(value)
    query = [(key, "[REDACTED]" if SECRET_KEY.search(key) else item) for key, item in parse_qsl(parts.query, keep_blank_values=True)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "[REDACTED]" if SECRET_KEY.search(str(key)) else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        value = re.sub(r"(?i)(bearer\s+)[^\s,]+", r"\1[REDACTED]", value)
        return value.replace(MARKER, MARKER)
    return value


def redact_headers(headers: Any) -> Any:
    if not isinstance(headers, list):
        return redact(headers)
    result = []
    for header in headers:
        if isinstance(header, dict) and SECRET_KEY.search(str(header.get("name", ""))):
            result.append({key: "[REDACTED]" if key.lower() == "value" else redact(item) for key, item in header.items()})
        else:
            result.append(redact(header))
    return result


def contains_marker(value: Any) -> bool:
    if isinstance(value, str):
        return MARKER.lower() in value.lower()
    if isinstance(value, dict):
        return any(contains_marker(key) or contains_marker(item) for key, item in value.items())
    if isinstance(value, list):
        return any(contains_marker(item) for item in value)
    return False


def parse_body(value: str) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


def analyze_har(source: Path, output: Path) -> None:
    document = json.loads(source.read_text(encoding="utf-8"))
    findings = []
    for entry in document.get("log", {}).get("entries", []):
        request = entry.get("request", {})
        response = entry.get("response", {})
        body = parse_body(request.get("postData", {}).get("text", ""))
        candidate = {"request": request, "postData": body, "response": response}
        if contains_marker(candidate):
            findings.append(
                {
                    "method": request.get("method"),
                    "url": redact_url(request.get("url", "")),
                    "headers": redact_headers(request.get("headers", [])),
                    "postData": redact(body),
                    "status": response.get("status"),
                }
            )
    result = {"marker": MARKER, "matches": findings, "match_count": len(findings)}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


def analyze_frames(source: Path, output: Path) -> None:
    matches = []
    for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = parse_body(line)
        if contains_marker(value):
            matches.append({"line": line_number, "frame": redact(value)})
    result = {"marker": MARKER, "matches": matches, "match_count": len(matches)}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only Bullet Force probe")
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect = subparsers.add_parser("inspect", help="Inventory one local installation")
    inspect.add_argument("--root", type=Path, help="Installation root; defaults to known macOS locations")
    inspect.add_argument("--output", type=Path, default=Path("tools/bullet_force_probe/captures/install-scan.json"))
    har = subparsers.add_parser("analyze-har", help="Find the marker in a DevTools HAR")
    har.add_argument("source", type=Path)
    har.add_argument("--output", type=Path, default=Path("tools/bullet_force_probe/captures/bfc-probe-001-analysis.json"))
    frames = subparsers.add_parser("analyze-frames", help="Find the marker in copied WebSocket frames, one per line")
    frames.add_argument("source", type=Path)
    frames.add_argument("--output", type=Path, default=Path("tools/bullet_force_probe/captures/bfc-probe-001-frame-analysis.json"))
    il2cpp = subparsers.add_parser("analyze-il2cpp", help="Scan IL2CPP metadata and native strings")
    il2cpp.add_argument("--root", type=Path, required=True)
    il2cpp.add_argument("--output", type=Path, default=Path("tools/bullet_force_probe/captures/create-match-flow.md"))
    mapper = subparsers.add_parser("map-create-match", help="Map exact Create Match methods from IL2CPP metadata")
    mapper.add_argument("--root", type=Path, required=True)
    mapper.add_argument("--output", type=Path, default=Path("tools/bullet_force_probe/captures/create-match-method-map.md"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "inspect":
        root = args.root.expanduser() if args.root else (candidate_roots()[0] if candidate_roots() else None)
        if root is None:
            print("No installation found. Set BFC_BULLET_FORCE_ROOT or pass --root.", file=sys.stderr)
            return 2
        inspect_installation(root, args.output)
    elif args.command == "analyze-har":
        analyze_har(args.source.expanduser(), args.output)
    elif args.command == "analyze-frames":
        analyze_frames(args.source.expanduser(), args.output)
    elif args.command == "analyze-il2cpp":
        analyze_il2cpp(args.root.expanduser(), args.output)
    else:
        map_create_match(args.root.expanduser(), args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())