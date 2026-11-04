#!/usr/bin/env python3
"""Generate the profile README SVG panels."""

from __future__ import annotations

import argparse
import dataclasses
import html
import json
import math
import os
import sys
import textwrap
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

GRAPHQL_ENDPOINT: str = "https://api.github.com/graphql"
LOGIN: str = "Ravi2k3"
LANGUAGES_QUERY: str = (
    "query($login:String!){ user(login:$login){ repositories(first:100, "
    "ownerAffiliations:OWNER, isFork:false){ nodes{ languages(first:10, "
    "orderBy:{field:SIZE, direction:DESC}){ edges{ size node{ name } } } } } } }"
)
ACTIVITY_QUERY: str = (
    "query($login:String!){ user(login:$login){ contributionsCollection{ "
    "contributionCalendar{ totalContributions "
    "weeks{ contributionDays{ contributionCount } } } } } }"
)

# Left out of the language panel by choice, so percentages cover what remains.
HIDDEN_LANGUAGES: Tuple[str, ...] = ("Dart",)
MAX_LANGUAGES: int = 6

DESKTOP_WIDTH: int = 1200
MOBILE_WIDTH: int = 720
DESKTOP_ROW_TEXT_X: int = 290
DESKTOP_ROW_CHARS: int = 70
MOBILE_ROW_CHARS: int = 46
MOBILE_GRAPH_WEEKS: int = 27

RUN_START_SECONDS: float = 0.8
RUN_SECONDS: float = 4.2
INTENSITY_THRESHOLDS: Tuple[int, ...] = (5, 15, 30)

HEADLINE: str = "I'm Ravi. I'm a PM who builds AI agents."
INTRO: str = (
    "I work at Colligence on Aikyat, an AI email and chat suite. "
    "I wrote most of the Mail backend and client before I moved into product."
)


@dataclass(frozen=True)
class Theme:
    name: str
    ink: str
    mute: str
    accent: str
    empty: str
    heat: Tuple[str, ...]
    language_colors: Tuple[str, ...]


@dataclass(frozen=True)
class Project:
    slug: str
    name: str
    text: str
    public: bool = False


@dataclass(frozen=True)
class LanguageStat:
    name: str
    percent: float


@dataclass(frozen=True)
class Activity:
    total: int
    weeks: List[List[int]]


THEMES: Tuple[Theme, ...] = (
    Theme(
        name="dark",
        ink="#e6edf3",
        mute="#9198a1",
        accent="#ff5a1f",
        empty="#161b22",
        heat=("#5a1f0a", "#a3330c", "#e5470f", "#ff5a1f"),
        language_colors=("#ff5a1f", "#ff8a4c", "#ffb38a", "#ffe3d6", "#8f2f0c", "#d9420f"),
    ),
    Theme(
        name="light",
        ink="#1f2328",
        mute="#59636e",
        accent="#d63900",
        empty="#f0f2f4",
        heat=("#ffd4c2", "#ff9a6b", "#f2601f", "#d63900"),
        language_colors=("#d63900", "#f2601f", "#ff9a6b", "#a32b00", "#ffc4a8", "#6e1e00"),
    ),
)

NOW_PROJECTS: Tuple[Project, ...] = (
    Project(
        slug="aikyat-mail",
        name="Aikyat Mail",
        text=(
            "Search your inbox in plain English across Gmail, Outlook, Yahoo and any IMAP "
            "account. The first version used one retriever and kept missing emails people "
            "expected to find, so we replaced it."
        ),
    ),
    Project(
        slug="aikyat-chat",
        name="Aikyat Chat",
        text=(
            "Pre-release. We nearly folded it into Mail. I argued to keep it separate, with a "
            "widget inside Mail, because the AI agent that works across our products has to "
            "live somewhere."
        ),
    ),
    Project(
        slug="reference-cards",
        name="Reference cards",
        text=(
            "Cite an email in chat and the other person gets a live card, which opens with "
            "their own permissions. Every new Aikyat product has to integrate this way."
        ),
    ),
)

BEFORE_PROJECTS: Tuple[Project, ...] = (
    Project(
        slug="moonlight",
        name="MoonLight",
        text=(
            "Agent SDK from Automa, the startup I co-founded with Gautam. I led the product "
            "and the agent loop, where the agent writes its own next action. Gautam published "
            "it. It's sunset now because the big providers' own SDKs do more."
        ),
        public=True,
    ),
    Project(
        slug="lv-outreach",
        name="LV Outreach",
        text=(
            "Cold email tool that writes each email from the lead and your product docs. A "
            "second model call rejects drafts with AI tells, like em dashes and filler "
            "adjectives, and makes it try again."
        ),
        public=True,
    ),
    Project(
        slug="facespace",
        name="FaceSpace",
        text=(
            "200+ video streams on one GPU, using multiprocessing to get around NVIDIA's "
            "single-process limit. My GPU funding request got rejected, so I found an RTX 3090 "
            "on campus and won the admins over with a demo."
        ),
    ),
    Project(
        slug="berghain",
        name="Berghain Challenge",
        text=(
            "70th of 1,330 on the Listen Labs leaderboard. Linear programming to predict "
            "rejections, plus heuristics recalculated every 50 admits."
        ),
    ),
)

# Every moving part uses CSS animation so they share one clock, including when a tab loads in the background.
HERO_MOTION_CSS: str = (
    ".lit{animation:ignite .22s linear both;}"
    "@keyframes ignite{from{fill:var(--e);}}"
    f".trace{{animation:walk {RUN_SECONDS}s linear both,settle .8s linear forwards;}}"
    "@keyframes walk{from{stroke-dashoffset:1;}to{stroke-dashoffset:0;}}"
    "@keyframes settle{to{opacity:.16;}}"
    f".head{{opacity:0;offset-rotate:0deg;animation:run {RUN_SECONDS}s linear both,show .01s linear forwards;}}"
    "@keyframes run{from{offset-distance:0%;}to{offset-distance:100%;}}"
    "@keyframes show{to{opacity:1;}}"
    ".alive{opacity:0;transform-box:fill-box;transform-origin:center;animation:ping 1.8s ease-out infinite;}"
    "@keyframes ping{from{opacity:.9;transform:scale(1);}to{opacity:0;transform:scale(3);}}"
    "@media (prefers-reduced-motion:reduce){.lit{animation:none;}.trace{animation:none;opacity:.16;}.head,.alive{display:none;}}"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate profile SVG panels.")
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output directory for SVG panels.",
    )
    return parser.parse_args()


def read_font_data(
    font_path: Path,
) -> str:
    font_data = "".join(font_path.read_text(encoding="utf-8").split())
    if not font_data:
        raise ValueError(f"Font base64 file is empty: {font_path}")
    return font_data


def graphql_user(
    token: str,
    query: str,
) -> Dict[str, Any]:
    payload = json.dumps({"query": query, "variables": {"login": LOGIN}}).encode("utf-8")
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
            decoded = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"GitHub GraphQL HTTP {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"GitHub GraphQL request failed: {error.reason}") from error

    if decoded.get("errors"):
        raise RuntimeError(f"GitHub GraphQL returned errors: {json.dumps(decoded['errors'])[:500]}")
    return decoded["data"]["user"]


def fetch_languages(
    token: str,
) -> List[LanguageStat]:
    repositories = graphql_user(token, LANGUAGES_QUERY)["repositories"]["nodes"]
    sizes_by_name: Dict[str, int] = {}
    for repository in repositories:
        for edge in repository["languages"]["edges"]:
            name = edge["node"]["name"]
            sizes_by_name[name] = sizes_by_name.get(name, 0) + int(edge["size"])
    return summarize_languages(sizes_by_name)


def summarize_languages(
    sizes_by_name: Dict[str, int],
) -> List[LanguageStat]:
    visible = sorted(
        (item for item in sizes_by_name.items() if item[0] not in HIDDEN_LANGUAGES),
        key=lambda item: item[1],
        reverse=True,
    )[:MAX_LANGUAGES]
    total_size = sum(size for _, size in visible)
    if total_size <= 0:
        raise RuntimeError("GitHub returned no language byte counts for owner repositories.")
    return [LanguageStat(name=name, percent=(size / total_size) * 100) for name, size in visible]


def fetch_activity(
    token: str,
) -> Activity:
    calendar = graphql_user(token, ACTIVITY_QUERY)["contributionsCollection"]["contributionCalendar"]
    weeks = [[day["contributionCount"] for day in week["contributionDays"]] for week in calendar["weeks"]]
    if not any(any(week) for week in weeks):
        raise RuntimeError("GitHub returned an empty contribution calendar.")
    return Activity(total=calendar["totalContributions"], weeks=weeks)


def svg_document(
    width: int,
    height: int,
    label: str,
    font_data: str,
    body: List[str],
    extra_css: str = "",
) -> str:
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
            f'width="{width}" height="{height}" role="img" aria-label="{html.escape(label, quote=True)}">',
            "<style>",
            f"@font-face{{font-family:'Google Sans Flex';src:url(data:font/woff2;base64,{font_data}) format('woff2');"
            "font-weight:100 900;}",
            "text{font-family:'Google Sans Flex',system-ui,-apple-system,sans-serif;}",
            extra_css,
            "</style>",
            *body,
            "</svg>",
        ]
    )


def text_node(
    x: int,
    y: int,
    content: str,
    size: int,
    fill: str,
    weight: int = 400,
    tracking: float = 0.0,
) -> str:
    return (
        f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{fill}" '
        f'letter-spacing="{tracking}">{html.escape(content)}</text>'
    )


def text_lines(
    lines: List[str],
    x: int,
    y: int,
    line_height: int,
    size: int,
    fill: str,
) -> List[str]:
    return [text_node(x, y + index * line_height, line, size, fill) for index, line in enumerate(lines)]


def heat_color(
    count: int,
    theme: Theme,
) -> str:
    return theme.heat[sum(count >= threshold for threshold in INTENSITY_THRESHOLDS)]


def run_graph(
    weeks: List[List[int]],
    theme: Theme,
    y: int,
    width: int,
    radius: int,
) -> Tuple[List[str], int]:
    """Draw active days lighting up as one path walks through them in date order."""
    x = 3
    pitch = width / len(weeks)
    cell = pitch * 0.84
    active: List[Tuple[float, float, int]] = []
    nodes: List[str] = []
    for column, week in enumerate(weeks):
        for row, count in enumerate(week):
            cell_x = x + column * pitch
            cell_y = y + row * pitch
            if count:
                active.append((cell_x, cell_y, count))
            else:
                nodes.append(
                    f'<rect x="{cell_x:.1f}" y="{cell_y:.1f}" width="{cell:.1f}" height="{cell:.1f}" '
                    f'rx="{radius}" fill="{theme.empty}"/>'
                )

    centers = [(cell_x + cell / 2, cell_y + cell / 2) for cell_x, cell_y, _ in active]
    distances = [0.0]
    for previous, current in zip(centers, centers[1:]):
        distances.append(distances[-1] + math.dist(previous, current))
    route_length = distances[-1] or 1.0

    for (cell_x, cell_y, count), distance in zip(active, distances):
        delay = RUN_START_SECONDS + RUN_SECONDS * distance / route_length
        nodes.append(
            f'<rect class="lit" x="{cell_x:.1f}" y="{cell_y:.1f}" width="{cell:.1f}" height="{cell:.1f}" '
            f'rx="{radius}" fill="{heat_color(count, theme)}" style="--e:{theme.empty};animation-delay:{delay:.2f}s"/>'
        )

    route = "M" + " L".join(f"{center_x:.1f} {center_y:.1f}" for center_x, center_y in centers)
    last_x, last_y = centers[-1]
    end_time = RUN_START_SECONDS + RUN_SECONDS
    nodes.extend(
        [
            f'<path class="trace" d="{route}" fill="none" stroke="{theme.ink}" stroke-width="1.6" '
            f'stroke-linejoin="round" pathLength="1" stroke-dasharray="1" '
            f'style="animation-delay:{RUN_START_SECONDS}s,{end_time}s"/>',
            f'<circle class="head" r="{cell * 0.42:.1f}" fill="{theme.ink}" '
            f"style=\"offset-path:path('{route}');animation-delay:{RUN_START_SECONDS}s,{RUN_START_SECONDS}s\"/>",
            f'<circle class="alive" cx="{last_x:.1f}" cy="{last_y:.1f}" r="{cell * 0.5:.1f}" fill="none" '
            f'stroke="{theme.accent}" stroke-width="2.5" style="animation-delay:{end_time}s"/>',
        ]
    )
    return nodes, int(pitch * 7)


def activity_caption(
    activity: Activity,
) -> str:
    # GitHub's private-contribution count depends on the token asking (the CI token gets 0), so no number here.
    return f"My last year on GitHub. Most of these {activity.total:,} contributions are in private repos."


def build_hero_desktop(
    activity: Activity,
    theme: Theme,
    font_data: str,
) -> str:
    size = 104
    style = f'font-size="{size}" font-weight="650" letter-spacing="{-size * 0.03}"'
    graph_y = 262
    graph, graph_height = run_graph(activity.weeks, theme, graph_y, DESKTOP_WIDTH - 6, 3)
    caption_y = graph_y + graph_height + 46
    intro_lines = textwrap.wrap(INTRO, 72)
    intro_y = caption_y + 66
    return svg_document(
        DESKTOP_WIDTH,
        intro_y + (len(intro_lines) - 1) * 44 + 30,
        f"{HEADLINE} {activity_caption(activity)} {INTRO}",
        font_data,
        [
            f'<text x="0" y="98" {style} fill="{theme.accent}"><tspan fill="{theme.ink}">I\'m Ravi.</tspan> I\'m a PM who</text>',
            f'<text x="0" y="216" {style} fill="{theme.accent}">builds AI agents.</text>',
            *graph,
            text_node(0, caption_y, activity_caption(activity), 26, theme.mute),
            *text_lines(intro_lines, 0, intro_y, 44, 32, theme.ink),
        ],
        HERO_MOTION_CSS,
    )


def build_hero_mobile(
    activity: Activity,
    theme: Theme,
    font_data: str,
) -> str:
    size = 78
    tracking = -size * 0.03
    graph_y = 304
    graph, graph_height = run_graph(activity.weeks[-MOBILE_GRAPH_WEEKS:], theme, graph_y, MOBILE_WIDTH - 6, 4)
    caption_y = graph_y + graph_height + 48
    caption_lines = textwrap.wrap(activity_caption(activity), 48)
    intro_y = caption_y + len(caption_lines) * 40 + 36
    intro_lines = textwrap.wrap(INTRO, 44)
    return svg_document(
        MOBILE_WIDTH,
        intro_y + (len(intro_lines) - 1) * 46 + 28,
        f"{HEADLINE} {activity_caption(activity)} {INTRO}",
        font_data,
        [
            text_node(0, 78, "I'm Ravi.", size, theme.ink, 650, tracking),
            text_node(0, 168, "I'm a PM who", size, theme.accent, 650, tracking),
            text_node(0, 258, "builds AI agents.", size, theme.accent, 650, tracking),
            *graph,
            *text_lines(caption_lines, 0, caption_y, 40, 29, theme.mute),
            *text_lines(intro_lines, 0, intro_y, 46, 33, theme.ink),
        ],
        HERO_MOTION_CSS,
    )


def open_arrow(
    x: int,
    y: int,
    size: int,
    color: str,
) -> str:
    return (
        f'<path d="M{x} {y} L{x + size} {y - size} M{x + size * 0.28:.1f} {y - size} L{x + size} {y - size} '
        f'L{x + size} {y - size * 0.28:.1f}" fill="none" stroke="{color}" stroke-width="2.4" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
    )


def build_section_label(
    label: str,
    theme: Theme,
    font_data: str,
    width: int,
    size: int,
) -> str:
    return svg_document(width, size + 34, label, font_data, [text_node(0, size + 16, label, size, theme.accent, 600)])


def build_project_desktop(
    project: Project,
    theme: Theme,
    font_data: str,
) -> str:
    baseline = 38
    line_height = 37
    lines = textwrap.wrap(project.text, DESKTOP_ROW_CHARS)
    body = [
        text_node(0, baseline, project.name, 27, theme.ink, 600),
        *text_lines(lines, DESKTOP_ROW_TEXT_X, baseline, line_height, 26, theme.mute),
    ]
    if project.public:
        body.append(open_arrow(250, baseline - 2, 13, theme.accent))
    height = baseline + (len(lines) - 1) * line_height + 30
    return svg_document(DESKTOP_WIDTH, height, f"{project.name}: {project.text}", font_data, body)


def build_project_mobile(
    project: Project,
    theme: Theme,
    font_data: str,
) -> str:
    text_y = 90
    line_height = 41
    lines = textwrap.wrap(project.text, MOBILE_ROW_CHARS)
    body = [
        text_node(0, 44, project.name, 33, theme.ink, 600),
        *text_lines(lines, 0, text_y, line_height, 30, theme.mute),
    ]
    if project.public:
        body.append(open_arrow(MOBILE_WIDTH - 20, 42, 15, theme.accent))
    height = text_y + (len(lines) - 1) * line_height + 30
    return svg_document(MOBILE_WIDTH, height, f"{project.name}: {project.text}", font_data, body)


def build_languages(
    languages: List[LanguageStat],
    theme: Theme,
    font_data: str,
    width: int,
    columns: int,
) -> str:
    bar_y = 66
    bar_height = 10
    gap = 3
    legend_y = 122
    row_height = 40
    usable_width = width - gap * (len(languages) - 1)
    body = [text_node(0, 44, "Languages", 26, theme.accent, 600)]
    cursor = 0.0
    for index, language in enumerate(languages):
        color = theme.language_colors[index]
        segment_width = usable_width * language.percent / 100
        body.append(f'<rect x="{cursor:.2f}" y="{bar_y}" width="{segment_width:.2f}" height="{bar_height}" fill="{color}"/>')
        cursor += segment_width + gap
        cell_x = (index % columns) * (width // columns)
        cell_y = legend_y + (index // columns) * row_height
        body.append(f'<circle cx="{cell_x + 7}" cy="{cell_y - 8}" r="7" fill="{color}"/>')
        body.append(
            f'<text x="{cell_x + 24}" y="{cell_y}" font-size="25" fill="{theme.ink}">{html.escape(language.name)} '
            f'<tspan fill="{theme.mute}">{language.percent:.1f}%</tspan></text>'
        )
    summary = ", ".join(f"{item.name} {item.percent:.1f}%" for item in languages)
    rows = math.ceil(len(languages) / columns)
    return svg_document(width, legend_y + rows * row_height, f"Languages: {summary}", font_data, body)


def build_panels(
    activity: Activity,
    languages: List[LanguageStat],
    theme: Theme,
    font_data: str,
) -> Dict[str, str]:
    panels: Dict[str, str] = {
        f"hero-{theme.name}": build_hero_desktop(activity, theme, font_data),
        f"hero-{theme.name}-mobile": build_hero_mobile(activity, theme, font_data),
        f"languages-{theme.name}": build_languages(languages, theme, font_data, DESKTOP_WIDTH, 3),
        f"languages-{theme.name}-mobile": build_languages(languages, theme, font_data, MOBILE_WIDTH, 2),
    }
    for label, slug in (("Now", "now"), ("Before", "before")):
        panels[f"{slug}-{theme.name}"] = build_section_label(label, theme, font_data, DESKTOP_WIDTH, 26)
        panels[f"{slug}-{theme.name}-mobile"] = build_section_label(label, theme, font_data, MOBILE_WIDTH, 31)
    for project in (*NOW_PROJECTS, *BEFORE_PROJECTS):
        panels[f"{project.slug}-{theme.name}"] = build_project_desktop(project, theme, font_data)
        panels[f"{project.slug}-{theme.name}-mobile"] = build_project_mobile(project, theme, font_data)
    return panels


def main() -> int:
    args = parse_args()
    token = os.environ.get("GH_TOKEN", "").strip()
    if not token:
        raise RuntimeError("GH_TOKEN is empty. Set the STATS_TOKEN secret so private repositories are counted.")
    font_data = read_font_data(Path(__file__).resolve().parent / "google-sans-flex.b64")
    activity = fetch_activity(token)
    languages = fetch_languages(token)
    out_dir: Path = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    for theme in THEMES:
        for panel_name, svg in build_panels(activity, languages, theme, font_data).items():
            (out_dir / f"{panel_name}.svg").write_text(f"{svg}\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
