from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Any

try:
    import pytesseract
except Exception:  # pragma: no cover - optional runtime dependency
    pytesseract = None


@dataclass
class ParsedMatchResult:
    outcome: str | None
    player_stats: dict[int, dict[str, int]]


def parse_match_result_from_image(image_bytes: bytes, players: list[Any]) -> ParsedMatchResult:
    if pytesseract is None:
        raise RuntimeError(
            "OCR support is not available yet. Install pytesseract and a local Tesseract binary, then retry."
        )

    try:
        from PIL import Image, UnidentifiedImageError

        image = Image.open(io.BytesIO(image_bytes))
        text = pytesseract.image_to_string(image, config="--psm 6")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise RuntimeError("That attachment is not a readable image.") from exc
    except Exception as exc:
        raise RuntimeError("I could not OCR that screenshot.") from exc

    return parse_match_result_text(text, players)


def parse_match_result_text(text: str, players: list[Any]) -> ParsedMatchResult:
    normalized_lines = [line.strip() for line in text.splitlines() if line.strip()]
    normalized_text = "\n".join(normalized_lines).lower()

    outcome = _infer_outcome(normalized_text)
    player_stats: dict[int, dict[str, int]] = {}

    for player in players:
        player_stats[player.discord_user_id] = _extract_player_stats(player.ign, normalized_lines)

    return ParsedMatchResult(outcome=outcome, player_stats=player_stats)


def _infer_outcome(normalized_text: str) -> str | None:
    won_patterns = (
        "your team has won",
        "you won",
        "your team won",
        "team won",
        "victory",
        "won",
    )
    lost_patterns = (
        "your team has lost",
        "you lost",
        "your team lost",
        "team lost",
        "defeat",
        "lost",
    )

    if any(pattern in normalized_text for pattern in won_patterns):
        return "won"
    if any(pattern in normalized_text for pattern in lost_patterns):
        return "lost"
    return None


def _extract_player_stats(ign: str, lines: list[str]) -> dict[str, int]:
    ign_lower = ign.lower()

    for index, line in enumerate(lines):
        lowered_line = line.lower()
        if ign_lower not in lowered_line:
            continue

        for candidate in [line, *lines[index + 1 : index + 3]]:
            stats = _parse_stats_from_candidate(candidate, ign)
            if stats is not None:
                return {"kills": stats[0], "deaths": stats[1]}

    return {"kills": 0, "deaths": 0}


def _parse_stats_from_candidate(candidate: str, ign: str) -> tuple[int, int] | None:
    ign_lower = ign.lower()
    lowered = candidate.lower()

    if ign_lower not in lowered:
        return None

    digits = re.findall(r"\d+", candidate)
    if len(digits) < 2:
        return None

    try:
        kills = int(digits[0])
        deaths = int(digits[1])
    except (TypeError, ValueError):
        return None

    return kills, deaths
