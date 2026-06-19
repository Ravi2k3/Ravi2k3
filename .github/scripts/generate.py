#!/usr/bin/env python3
"""Generate the profile README SVG panels."""

from __future__ import annotations

import argparse
import base64
import binascii
import html
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


GRAPHQL_ENDPOINT: str = "https://api.github.com/graphql"
LOGIN: str = "Ravi2k3"

INK: str = "#c9d1d9"
ORANGE: str = "#D97757"
MUTE: str = "#6e7681"
BG: str = "#0d1117"
HAIR: str = "#30363d"

# Curated values, manually updated because they are not reliably fetchable.
INSTALLS: str = "7.7k"
YEARS: str = "4+"

CONTRIBUTIONS_QUERY: str = (
    "query($login:String!){ user(login:$login){ contributionsCollection{ "
    "contributionCalendar{ totalContributions weeks{ contributionDays{ "
    "contributionCount } } } } } }"
)
LANGUAGES_QUERY: str = (
    "query($login:String!){ user(login:$login){ repositories(first:100, "
    "ownerAffiliations:OWNER, isFork:false){ nodes{ languages(first:10){ "
    "edges{ size node{ name color } } } } } } }"
)

JsonObject = Dict[str, Any]


@dataclass(frozen=True)
class LanguageStat:
    name: str
    color: str
    size: int
    percent: float


@dataclass(frozen=True)
class ProfileData:
    contributions: int
    languages: List[LanguageStat]
    calendar_weeks: List[List[int]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate profile SVG panels.")
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Use sample layout data without network access.",
    )
    parser.add_argument(
        "--require-live",
        action="store_true",
        help="Fail instead of falling back to sample data when no token is set (use in CI).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory for SVG panels.",
    )
    return parser.parse_args()


def resolve_paths(
    output_directory: Optional[Path],
) -> Tuple[Path, Path]:
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parents[1]
    out_dir = output_directory.resolve() if output_directory else repo_root / "assets"
    font_path = script_dir / "lexvf.b64"
    return out_dir, font_path


def read_font_data(
    font_path: Path,
) -> str:
    if not font_path.exists():
        raise FileNotFoundError(f"Font base64 file is missing: {font_path}")

    font_data = "".join(font_path.read_text(encoding="utf-8").split())
    if not font_data:
        raise ValueError(f"Font base64 file is empty: {font_path}")

    try:
        base64.b64decode(font_data, validate=True)
    except binascii.Error as error:
        raise ValueError(f"Font base64 file is invalid: {font_path}") from error

    return font_data


def graphql_request(
    token: str,
    query: str,
    variables: JsonObject,
) -> JsonObject:
    payload = json.dumps(
        {"query": query, "variables": variables},
        separators=(",", ":"),
    ).encode("utf-8")
    request = urllib.request.Request(
        GRAPHQL_ENDPOINT,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "profile-generator",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = response.getcode()
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"GitHub GraphQL HTTP {error.code}: {body[:500]}"
        ) from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"GitHub GraphQL request failed: {error.reason}") from error

    if status != 200:
        raise RuntimeError(f"GitHub GraphQL HTTP {status}: {body[:500]}")

    try:
        decoded = json.loads(body)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"GitHub GraphQL returned invalid JSON: {body[:500]}") from error

    if not isinstance(decoded, dict):
        raise RuntimeError("GitHub GraphQL returned a non-object JSON payload.")

    errors = decoded.get("errors")
    if errors:
        raise RuntimeError(
            f"GitHub GraphQL returned errors: {json.dumps(errors)[:500]}"
        )

    return decoded


def require_object(
    value: Any,
    path: str,
) -> JsonObject:
    if not isinstance(value, dict):
        raise RuntimeError(f"Invalid GitHub response: expected object at {path}.")
    return value


def require_list(
    value: Any,
    path: str,
) -> List[Any]:
    if not isinstance(value, list):
        raise RuntimeError(f"Invalid GitHub response: expected list at {path}.")
    return value


def require_int(
    value: Any,
    path: str,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeError(f"Invalid GitHub response: expected integer at {path}.")
    return value


def require_str(
    value: Any,
    path: str,
) -> str:
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"Invalid GitHub response: expected string at {path}.")
    return value


def extract_user(
    response: JsonObject,
    context: str,
) -> JsonObject:
    data = require_object(response.get("data"), f"{context}.data")
    user = data.get("user")
    if user is None:
        raise RuntimeError(f"Invalid GitHub response: data.user is missing for {context}.")
    return require_object(user, f"{context}.data.user")


def fetch_contributions_and_calendar(
    token: str,
) -> Tuple[int, List[List[int]]]:
    response = graphql_request(
        token=token,
        query=CONTRIBUTIONS_QUERY,
        variables={"login": LOGIN},
    )
    user = extract_user(response, "contributions")
    collection = require_object(
        user.get("contributionsCollection"),
        "contributions.data.user.contributionsCollection",
    )
    calendar = require_object(
        collection.get("contributionCalendar"),
        "contributions.data.user.contributionsCollection.contributionCalendar",
    )
    total = require_int(
        calendar.get("totalContributions"),
        "contributions.data.user.contributionsCollection.contributionCalendar.totalContributions",
    )
    weeks_raw = require_list(
        calendar.get("weeks"),
        "contributions.data.user.contributionsCollection.contributionCalendar.weeks",
    )
    weeks: List[List[int]] = []
    for week_index, week in enumerate(weeks_raw):
        week_object = require_object(week, f"calendar.weeks[{week_index}]")
        days = require_list(
            week_object.get("contributionDays"),
            f"calendar.weeks[{week_index}].contributionDays",
        )
        weeks.append(
            [
                require_int(
                    require_object(day, f"calendar.weeks[{week_index}].days[{day_index}]").get(
                        "contributionCount"
                    ),
                    f"calendar.weeks[{week_index}].days[{day_index}].contributionCount",
                )
                for day_index, day in enumerate(days)
            ]
        )
    return total, weeks


def normalize_language_stats(
    sizes_by_name: Dict[str, int],
    colors_by_name: Dict[str, str],
) -> List[LanguageStat]:
    ordered = sorted(
        sizes_by_name.items(),
        key=lambda item: item[1],
        reverse=True,
    )[:6]
    total_size = sum(size for _, size in ordered)
    if total_size <= 0:
        raise RuntimeError("GitHub returned no language byte counts for owner repositories.")

    return [
        LanguageStat(
            name=name,
            color=colors_by_name.get(name, MUTE),
            size=size,
            percent=(size / total_size) * 100,
        )
        for name, size in ordered
    ]


def fetch_languages(
    token: str,
) -> List[LanguageStat]:
    response = graphql_request(
        token=token,
        query=LANGUAGES_QUERY,
        variables={"login": LOGIN},
    )
    user = extract_user(response, "languages")
    repositories = require_object(
        user.get("repositories"),
        "languages.data.user.repositories",
    )
    nodes = require_list(
        repositories.get("nodes"),
        "languages.data.user.repositories.nodes",
    )

    sizes_by_name: Dict[str, int] = {}
    colors_by_name: Dict[str, str] = {}

    for repository_index, repository in enumerate(nodes):
        repository_object = require_object(
            repository,
            f"languages.data.user.repositories.nodes[{repository_index}]",
        )
        languages = require_object(
            repository_object.get("languages"),
            f"languages.data.user.repositories.nodes[{repository_index}].languages",
        )
        edges = require_list(
            languages.get("edges"),
            f"languages.data.user.repositories.nodes[{repository_index}].languages.edges",
        )
        for edge_index, edge in enumerate(edges):
            edge_path = (
                "languages.data.user.repositories.nodes"
                f"[{repository_index}].languages.edges[{edge_index}]"
            )
            edge_object = require_object(edge, edge_path)
            size = require_int(edge_object.get("size"), f"{edge_path}.size")
            node = require_object(edge_object.get("node"), f"{edge_path}.node")
            name = require_str(node.get("name"), f"{edge_path}.node.name")
            color_value = node.get("color")

            if size <= 0:
                continue
            if color_value is None:
                color = MUTE
            else:
                color = require_str(color_value, f"{edge_path}.node.color")

            sizes_by_name[name] = sizes_by_name.get(name, 0) + size
            colors_by_name.setdefault(name, color)

    return normalize_language_stats(sizes_by_name, colors_by_name)


def load_live_profile_data(
    token: str,
) -> ProfileData:
    contributions, calendar_weeks = fetch_contributions_and_calendar(token)
    return ProfileData(
        contributions=contributions,
        languages=fetch_languages(token),
        calendar_weeks=calendar_weeks,
    )


def load_sample_profile_data() -> ProfileData:
    return ProfileData(
        contributions=1372,
        languages=normalize_language_stats(
            sizes_by_name={
                "Python": 382,
                "TypeScript": 244,
                "Dart": 171,
                "C++": 83,
                "HTML": 65,
                "CSS": 55,
            },
            colors_by_name={
                "Python": "#3572A5",
                "TypeScript": "#3178c6",
                "Dart": "#00B4AB",
                "C++": "#f34b7d",
                "HTML": "#e34c26",
                "CSS": "#663399",
            },
        ),
        calendar_weeks=sample_calendar_weeks(),
    )


def sample_calendar_weeks() -> List[List[int]]:
    weeks: List[List[int]] = []
    state = 20260619
    for column in range(53):
        week: List[int] = []
        density = 0.08 + (column / 53) * 0.55
        for _ in range(7):
            state = (state * 1103515245 + 12345) & 0x7FFFFFFF
            roll = state / 0x7FFFFFFF
            state = (state * 1103515245 + 12345) & 0x7FFFFFFF
            week.append(int(1 + (state / 0x7FFFFFFF) * 30) if roll < density else 0)
        weeks.append(week)
    return weeks


def escape_text(
    value: str,
) -> str:
    return html.escape(value, quote=False)


def escape_attr(
    value: str,
) -> str:
    return html.escape(value, quote=True)


def format_svg_number(
    value: float,
) -> str:
    formatted = f"{value:.3f}".rstrip("0").rstrip(".")
    return "0" if formatted == "-0" else formatted


def format_percent(
    value: float,
) -> str:
    return f"{value:.1f}%"


def font_defs(
    font_data: str,
) -> str:
    return (
        "<defs><style>\n"
        "@font-face { font-family:'Lex'; src:url(data:font/woff2;base64,"
        f"{font_data}) format('woff2'); font-weight:100 900; font-style:normal; }}\n"
        "text { font-family:'Lex', system-ui, -apple-system, sans-serif; }\n"
        "</style></defs>"
    )


def svg_open(
    width: int,
    height: int,
    aria_label: str,
    font_data: str,
) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{escape_attr(aria_label)}">\n'
        f"  {font_defs(font_data)}"
    )


def svg_text(
    x: float,
    y: float,
    font_size: float,
    fill: str,
    font_weight: int,
    content: str,
    letter_spacing: Optional[float] = None,
    text_anchor: Optional[str] = None,
) -> str:
    attributes = [
        f'x="{format_svg_number(x)}"',
        f'y="{format_svg_number(y)}"',
        f'font-size="{format_svg_number(font_size)}"',
        f'font-weight="{font_weight}"',
        f'fill="{fill}"',
    ]
    if letter_spacing is not None:
        attributes.append(f'letter-spacing="{format_svg_number(letter_spacing)}"')
    if text_anchor is not None:
        attributes.append(f'text-anchor="{escape_attr(text_anchor)}"')
    return f"  <text {' '.join(attributes)}>{escape_text(content)}</text>"


def build_banner_svg(
    font_data: str,
) -> str:
    parts = [
        svg_open(
            width=1200,
            height=360,
            aria_label=(
                "Ravi Krishna, Product Manager. I design the boundaries between products."
            ),
            font_data=font_data,
        ),
        f'  <rect width="1200" height="360" fill="{BG}"/>',
        "",
        f'  <rect x="64" y="74" width="16" height="16" fill="{ORANGE}"/>',
        svg_text(
            x=92,
            y=89,
            font_size=14,
            fill=MUTE,
            font_weight=600,
            content="PRODUCT MANAGER · COLLIGENCE",
            letter_spacing=3,
        ),
        "",
        (
            f'  <text x="60" y="198" font-size="74" font-weight="700" '
            f'letter-spacing="-2" fill="{INK}">I design the '
            f'<tspan fill="{ORANGE}">boundaries</tspan></text>'
        ),
        svg_text(
            x=60,
            y=274,
            font_size=74,
            fill=INK,
            font_weight=700,
            content="between products.",
            letter_spacing=-2,
        ),
        "",
        svg_text(
            x=64,
            y=328,
            font_size=16,
            fill=MUTE,
            font_weight=450,
            content=(
                "the protocols, permissions, and identity layers that let separate apps "
                "work together"
            ),
        ),
        "</svg>",
    ]
    return "\n".join(parts)


def build_building_svg(
    font_data: str,
) -> str:
    rows = [
        (
            "Aikyat Mail",
            "40+ providers · 92.7% recall@10",
            (
                "AI email client across Gmail, Outlook, and 40+ providers, built solo. "
                "FastAPI · pgvector · Flutter."
            ),
        ),
        (
            "The reference-card protocol",
            "the banner above",
            (
                "I designed the spec: a cited reference opens in the reader's "
                "permissions, never the sender's."
            ),
        ),
        (
            "Throughline",
            "0 ACL leaks @ 100k · 0.987 recall",
            "Permission-safe semantic search. The nearest neighbor is denied if it isn't yours.",
        ),
    ]
    parts = [
        svg_open(
            width=1200,
            height=396,
            aria_label=(
                "What Ravi is building: Aikyat Mail, the reference-card protocol, Throughline"
            ),
            font_data=font_data,
        ),
        f'  <rect width="1200" height="396" fill="{BG}"/>',
        f'  <rect x="64" y="42" width="14" height="14" fill="{ORANGE}"/>',
        svg_text(
            x=90,
            y=56,
            font_size=13,
            fill=MUTE,
            font_weight=600,
            content="CURRENTLY BUILDING",
            letter_spacing=3,
        ),
    ]

    y = 118
    for index, (name, metric, description) in enumerate(rows):
        parts.extend(
            [
                svg_text(
                    x=64,
                    y=y,
                    font_size=27,
                    fill=INK,
                    font_weight=700,
                    content=name,
                    letter_spacing=-0.5,
                ),
                svg_text(
                    x=1136,
                    y=y - 2,
                    font_size=14,
                    fill=ORANGE,
                    font_weight=500,
                    content=metric,
                    text_anchor="end",
                ),
                svg_text(
                    x=64,
                    y=y + 28,
                    font_size=15,
                    fill=MUTE,
                    font_weight=450,
                    content=description,
                ),
            ]
        )
        if index < len(rows) - 1:
            parts.append(
                f'  <rect x="64" y="{y + 54}" width="1072" height="1" fill="{HAIR}"/>'
            )
        y += 96

    parts.append("</svg>")
    return "\n".join(parts)


def build_stats_svg(
    profile_data: ProfileData,
    font_data: str,
) -> str:
    stats = [
        (f"{profile_data.contributions:,}", "contributions, last year"),
        (INSTALLS, "moonlight-ai installs"),
        (YEARS, "years shipping, since 2021"),
    ]
    parts = [
        svg_open(
            width=1200,
            height=212,
            aria_label=(
                f"By the numbers: {profile_data.contributions:,} contributions last year, "
                f"{INSTALLS} moonlight-ai installs, {YEARS} years shipping"
            ),
            font_data=font_data,
        ),
        f'  <rect width="1200" height="212" fill="{BG}"/>',
        f'  <rect x="64" y="44" width="14" height="14" fill="{ORANGE}"/>',
        svg_text(
            x=90,
            y=58,
            font_size=13,
            fill=MUTE,
            font_weight=600,
            content="BY THE NUMBERS",
            letter_spacing=3,
        ),
    ]

    for (number, label), x in zip(stats, [64, 458, 852]):
        parts.extend(
            [
                svg_text(
                    x=x,
                    y=146,
                    font_size=58,
                    fill=ORANGE,
                    font_weight=700,
                    content=number,
                    letter_spacing=-1.5,
                ),
                svg_text(
                    x=x + 2,
                    y=176,
                    font_size=14,
                    fill=MUTE,
                    font_weight=450,
                    content=label,
                ),
            ]
        )

    parts.append("</svg>")
    return "\n".join(parts)


def build_language_bar_segments(
    languages: List[LanguageStat],
) -> List[str]:
    bar_x = 64.0
    bar_y = 92.0
    bar_width = 1072.0
    bar_height = 18.0
    gap = 2.0 if len(languages) > 1 else 0.0
    color_width = bar_width - (gap * (len(languages) - 1))
    total_size = sum(language.size for language in languages)
    if total_size <= 0:
        raise RuntimeError("Cannot render language bar with zero total size.")

    parts = [
        "  <clipPath id=\"language-bar-clip\">",
        (
            f'    <rect x="{format_svg_number(bar_x)}" y="{format_svg_number(bar_y)}" '
            f'width="{format_svg_number(bar_width)}" height="{format_svg_number(bar_height)}" '
            f'rx="{format_svg_number(bar_height / 2)}" ry="{format_svg_number(bar_height / 2)}"/>'
        ),
        "  </clipPath>",
        '  <g clip-path="url(#language-bar-clip)">',
        f'    <rect x="64" y="92" width="1072" height="18" fill="{BG}"/>',
    ]

    consumed_color_width = 0.0
    for index, language in enumerate(languages):
        if index == len(languages) - 1:
            segment_width = color_width - consumed_color_width
        else:
            segment_width = color_width * (language.size / total_size)
        segment_x = bar_x + consumed_color_width + (gap * index)
        parts.append(
            f'    <rect x="{format_svg_number(segment_x)}" y="{format_svg_number(bar_y)}" '
            f'width="{format_svg_number(segment_width)}" height="{format_svg_number(bar_height)}" '
            f'fill="{escape_attr(language.color)}"/>'
        )
        consumed_color_width += segment_width

    parts.append("  </g>")
    return parts


def build_language_legend(
    languages: List[LanguageStat],
) -> List[str]:
    if not languages:
        raise RuntimeError("Cannot render language legend without languages.")

    slot_width = 1072.0 / len(languages)
    parts: List[str] = []
    for index, language in enumerate(languages):
        legend_x = 64.0 + (slot_width * index)
        text_x = legend_x + 18.0
        label = escape_text(language.name)
        percent = escape_text(format_percent(language.percent))
        parts.extend(
            [
                (
                    f'  <circle cx="{format_svg_number(legend_x + 5)}" cy="145" r="5" '
                    f'fill="{escape_attr(language.color)}"/>'
                ),
                (
                    f'  <text x="{format_svg_number(text_x)}" y="150" font-size="14" '
                    f'font-weight="450" fill="{INK}">{label} '
                    f'<tspan fill="{MUTE}">{percent}</tspan></text>'
                ),
            ]
        )
    return parts


def build_languages_svg(
    profile_data: ProfileData,
    font_data: str,
) -> str:
    language_summary = ", ".join(
        f"{language.name} {format_percent(language.percent)}"
        for language in profile_data.languages
    )
    parts = [
        svg_open(
            width=1200,
            height=196,
            aria_label=f"Languages: {language_summary}",
            font_data=font_data,
        ),
        f'  <rect width="1200" height="196" fill="{BG}"/>',
        f'  <rect x="64" y="44" width="14" height="14" fill="{ORANGE}"/>',
        svg_text(
            x=90,
            y=58,
            font_size=13,
            fill=MUTE,
            font_weight=600,
            content="LANGUAGES",
            letter_spacing=3,
        ),
    ]
    parts.extend(build_language_bar_segments(profile_data.languages))
    parts.extend(build_language_legend(profile_data.languages))
    parts.append("</svg>")
    return "\n".join(parts)


# Car-crash contribution panel. GitHub renders SVGs as <img>, so the whole
# animation is baked into CSS @keyframes (no JavaScript runs). A coral car drives
# across the real contribution grid and the filled cells launch off as it reaches
# their column, then the graph redraws and it loops.
CAR_EMPTY: str = "#161b22"
CAR_GREENS: List[str] = ["#0e4429", "#006d32", "#26a641", "#39d353"]
CAR_DARK: str = "#b75e43"
CAR_HEADLIGHT: str = "#FDE68A"
CAR_TAILLIGHT: str = "#FF5F56"
CAR_TIRE: str = "#0a0c10"
CAR_HUB: str = "#2a2f37"

CAR_WIDTH: int = 1200
CAR_HEIGHT: int = 240
CAR_CELL: int = 15
CAR_GAP: int = 4
CAR_PITCH: int = CAR_CELL + CAR_GAP
CAR_ORIGIN_X: int = 98
CAR_ORIGIN_Y: int = 58
CAR_ROWS: int = 7
CAR_PERIOD_S: float = 7.0
CAR_CROSS_END: float = 0.78  # phase at which the car has fully exited to the right
CAR_RESET_START: float = 0.92  # phase where the graph begins fading back in


def contribution_level(
    count: int,
) -> int:
    if count <= 0:
        return -1
    if count <= 3:
        return 0
    if count <= 9:
        return 1
    if count <= 29:
        return 2
    return 3


def deterministic_rng(
    seed: int,
):
    state = (seed * 1103515245 + 12345) & 0x7FFFFFFF

    def nxt() -> float:
        nonlocal state
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        return state / 0x7FFFFFFF

    return nxt


def car_arrival_phase(
    cell_center_x: float,
) -> float:
    phase = CAR_CROSS_END * (cell_center_x + 150.0) / 1500.0
    return max(0.0, min(CAR_CROSS_END, phase))


def car_cell_keyframes(
    name: str,
    fly_start_pct: float,
    dx: float,
    dy: float,
    rot: float,
) -> str:
    fly_peak = min(CAR_RESET_START * 100 - 4, fly_start_pct + 5)
    fly_end = min(CAR_RESET_START * 100 - 1, fly_start_pct + 12)
    reset_pct = CAR_RESET_START * 100
    return (
        f"@keyframes {name}{{"
        f"0%,{fly_start_pct:.2f}%{{transform:translate(0,0) rotate(0);opacity:1}}"
        f"{fly_peak:.2f}%{{transform:translate({dx * 0.45:.0f}px,{dy * 0.5:.0f}px) rotate({rot * 0.5:.0f}deg);opacity:1}}"
        f"{fly_end:.2f}%{{transform:translate({dx:.0f}px,{dy:.0f}px) rotate({rot:.0f}deg);opacity:0}}"
        f"{reset_pct:.2f}%{{transform:translate({dx:.0f}px,{dy:.0f}px) rotate({rot:.0f}deg);opacity:0}}"
        f"{reset_pct + 0.5:.2f}%{{transform:translate(0,0) rotate(0);opacity:0}}"
        f"100%{{transform:translate(0,0) rotate(0);opacity:1}}"
        f"}}"
    )


def build_car_group() -> str:
    car_w = 132
    half = car_w / 2
    body = (
        f'<path d="M{-half},0 L{-half + 12},-20 L-14,-25 L9,-46 L46,-46 '
        f'L62,-23 L{half},-18 L{half},0 Z" fill="{ORANGE}"/>'
    )
    body_shade = f'<path d="M{-half},0 L{-half + 12},-20 L-14,-25 L-14,0 Z" fill="{CAR_DARK}"/>'
    window = f'<path d="M11,-44 L43,-44 L57,-25 L16,-25 Z" fill="{BG}"/>'
    headlight = f'<rect x="{half - 7}" y="-16" width="7" height="7" rx="1.5" fill="{CAR_HEADLIGHT}"/>'
    taillight = f'<rect x="{-half}" y="-16" width="5" height="8" rx="1.5" fill="{CAR_TAILLIGHT}"/>'
    wheels = "".join(
        f'<circle cx="{wx}" cy="2" r="15" fill="{CAR_TIRE}"/>'
        f'<circle cx="{wx}" cy="2" r="6" fill="{CAR_HUB}"/>'
        for wx in (-half + 28, half - 28)
    )
    glow = f'<ellipse cx="0" cy="6" rx="96" ry="30" fill="{ORANGE}" opacity="0.18" filter="url(#carsoft)"/>'
    speed = "".join(
        f'<rect x="{-half - 18 - i * 26}" y="{-20 + i * 9}" width="20" height="2.5" rx="1.25" '
        f'fill="{ORANGE}" opacity="{0.5 - i * 0.09:.2f}"/>'
        for i in range(4)
    )
    return (
        f'<g class="car">{glow}{speed}{body}{body_shade}{window}'
        f"{headlight}{taillight}{wheels}</g>"
    )


def build_car_svg(
    weeks: List[List[int]],
) -> str:
    keyframes: List[str] = []
    cells: List[str] = []
    base_y = CAR_ORIGIN_Y + CAR_ROWS * CAR_PITCH - CAR_GAP
    rand = deterministic_rng(20260619)
    fly_index = 0

    for col, week in enumerate(weeks):
        cx = CAR_ORIGIN_X + col * CAR_PITCH
        phase = car_arrival_phase(cx + CAR_CELL / 2)
        for row, count in enumerate(week):
            cy = CAR_ORIGIN_Y + row * CAR_PITCH
            level = contribution_level(count)
            if level < 0:
                cells.append(
                    f'<rect x="{cx}" y="{cy}" width="{CAR_CELL}" height="{CAR_CELL}" '
                    f'rx="3" fill="{CAR_EMPTY}"/>'
                )
                continue
            forward = 30 + rand() * 120
            lateral = forward if rand() > 0.18 else -(20 + rand() * 70)
            dy = -(150 + rand() * 150)
            rot = (rand() * 2 - 1) * 240
            name = f"f{fly_index}"
            keyframes.append(car_cell_keyframes(name, phase * 100, lateral, dy, rot))
            cells.append(
                f'<rect class="cell" style="animation-name:{name}" x="{cx}" y="{cy}" '
                f'width="{CAR_CELL}" height="{CAR_CELL}" rx="3" fill="{CAR_GREENS[level]}"/>'
            )
            fly_index += 1

    drive = (
        "@keyframes drive{"
        "0%{transform:translate(-150px,0)}"
        "18%{transform:translate(180px,-2px)}"
        "40%{transform:translate(620px,0)}"
        "60%{transform:translate(980px,-2px)}"
        f"{CAR_CROSS_END * 100:.0f}%{{transform:translate(1350px,0)}}"
        "100%{transform:translate(1350px,0)}}"
    )
    style = (
        "<style>"
        ".cell{transform-box:fill-box;transform-origin:center;"
        f"animation-duration:{CAR_PERIOD_S}s;animation-iteration-count:infinite;"
        "animation-timing-function:ease-out}"
        f".car{{animation:drive {CAR_PERIOD_S}s linear infinite;transform:translate(-150px,0)}}"
        + drive
        + "".join(keyframes)
        + "</style>"
    )
    defs = (
        '<defs><filter id="carsoft" x="-50%" y="-50%" width="200%" height="200%">'
        '<feGaussianBlur stdDeviation="8"/></filter></defs>'
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{CAR_WIDTH}" height="{CAR_HEIGHT}" '
        f'viewBox="0 0 {CAR_WIDTH} {CAR_HEIGHT}" role="img" '
        f'aria-label="A car driving across the contribution graph, knocking the days off">'
        f"{defs}{style}"
        f'<rect width="{CAR_WIDTH}" height="{CAR_HEIGHT}" fill="{BG}"/>'
        f'<g>{"".join(cells)}</g>'
        f'<g transform="translate(0,{base_y + 6})">{build_car_group()}</g>'
        f"</svg>"
    )


def write_svg(
    output_path: Path,
    svg: str,
) -> None:
    output_path.write_text(f"{svg}\n", encoding="utf-8")
    print(f"wrote {output_path}")


def render_panels(
    profile_data: ProfileData,
    font_data: str,
    out_dir: Path,
) -> List[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs = [
        (out_dir / "banner.svg", build_banner_svg(font_data)),
        (out_dir / "building.svg", build_building_svg(font_data)),
        (out_dir / "stats.svg", build_stats_svg(profile_data, font_data)),
        (out_dir / "languages.svg", build_languages_svg(profile_data, font_data)),
        (out_dir / "car.svg", build_car_svg(profile_data.calendar_weeks)),
    ]

    written_paths: List[Path] = []
    for output_path, svg in outputs:
        write_svg(output_path, svg)
        written_paths.append(output_path)
    return written_paths


def main() -> int:
    args = parse_args()
    out_dir, font_path = resolve_paths(args.out)
    font_data = read_font_data(font_path)
    token = os.environ.get("GH_TOKEN", "").strip()

    if args.require_live and not token:
        raise RuntimeError(
            "Live mode requires GH_TOKEN, but it is empty. Set the STATS_TOKEN secret "
            "so private repositories are included; refusing to publish sample data."
        )

    use_sample = args.sample or not token

    if use_sample:
        print(
            "WARNING: sample data, not real, do not publish languages.svg from sample mode",
            file=sys.stderr,
        )
        profile_data = load_sample_profile_data()
    else:
        profile_data = load_live_profile_data(token)

    render_panels(
        profile_data=profile_data,
        font_data=font_data,
        out_dir=out_dir,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
