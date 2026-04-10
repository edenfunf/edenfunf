import os
import argparse
import requests
from datetime import datetime, timedelta, timezone


GRAPHQL_URL = "https://api.github.com/graphql"

QUERY = """
query($q: String!) {
  search(query: $q, type: ISSUE, first: 30) {
    nodes {
      ... on PullRequest {
        title
        url
        mergedAt
        repository {
          nameWithOwner
          owner {
            login
          }
        }
      }
    }
  }
}
"""

START_MARKER = "<!-- MERGED_PRS_START -->"
END_MARKER = "<!-- MERGED_PRS_END -->"

# Color palette for org circles
PALETTE = [
    "#58a6ff",
    "#3fb950",
    "#d2a8ff",
    "#ffa657",
    "#ff7b72",
    "#79c0ff",
    "#56d364",
    "#bc8cff",
    "#f78166",
    "#ffa198",
]


def fetch_merged_prs(username: str, token: str, days: int) -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    search_query = f"author:{username} is:pr is:merged merged:>{since}"

    headers = {"Authorization": f"Bearer {token}"}
    response = requests.post(
        GRAPHQL_URL,
        json={"query": QUERY, "variables": {"q": search_query}},
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()

    data = response.json()
    if "errors" in data:
        raise RuntimeError(f"GraphQL errors: {data['errors']}")

    return data["data"]["search"]["nodes"]


def org_color(org: str) -> str:
    idx = sum(ord(c) for c in org) % len(PALETTE)
    return PALETTE[idx]


def generate_svg(prs: list[dict], days: int, username: str) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Group by repo, preserve first-seen order
    repo_counts: dict[str, int] = {}
    repo_org: dict[str, str] = {}
    for pr in prs:
        repo = pr["repository"]["nameWithOwner"]
        org = pr["repository"]["owner"]["login"]
        repo_counts[repo] = repo_counts.get(repo, 0) + 1
        repo_org[repo] = org

    sorted_repos = sorted(repo_counts.items(), key=lambda x: -x[1])
    max_count = max(repo_counts.values()) if repo_counts else 1
    total = len(prs)

    # Layout constants
    W = 440
    PAD = 20
    HEADER_H = 62
    ROW_H = 38
    FOOTER_H = 30
    H = HEADER_H + max(len(sorted_repos), 1) * ROW_H + FOOTER_H
    BAR_X = 256
    BAR_MAX_W = 120
    # ── rows ──────────────────────────────────────────────────────────────
    rows: list[str] = []
    if not sorted_repos:
        rows.append(
            f'<text x="{PAD}" y="{HEADER_H + 22}" '
            f'font-family="system-ui,sans-serif" font-size="12" fill="#484f58">'
            f"No merged PRs in this period.</text>"
        )
    else:
        for i, (repo, count) in enumerate(sorted_repos):
            org = repo_org[repo]
            color = org_color(org)
            initial = org[0].upper()
            y = HEADER_H + i * ROW_H
            cy = y + ROW_H // 2
            bar_w = max(6, int((count / max_count) * BAR_MAX_W))
            label = repo if len(repo) <= 26 else repo[:23] + "…"

            rows.append(f"""
  <circle cx="{PAD + 11}" cy="{cy}" r="11" fill="{color}1a" stroke="{color}" stroke-width="1.5"/>
  <text x="{PAD + 11}" y="{cy + 4}" text-anchor="middle"
    font-family="system-ui,sans-serif" font-size="10" font-weight="700" fill="{color}">{initial}</text>
  <text x="{PAD + 30}" y="{cy + 4}"
    font-family="ui-monospace,SFMono-Regular,monospace" font-size="12" fill="#8b949e">{label}</text>
  <rect x="{BAR_X}" y="{cy - 7}" width="{bar_w}" height="14" rx="3" fill="{color}" opacity="0.25"/>
  <rect x="{BAR_X}" y="{cy - 7}" width="{bar_w}" height="14" rx="3" fill="{color}" opacity="0.55"/>
  <text x="{BAR_X + bar_w + 8}" y="{cy + 5}"
    font-family="system-ui,sans-serif" font-size="12" font-weight="600" fill="#e6edf3">{count}</text>""")

    # ── assemble ──────────────────────────────────────────────────────────
    return f"""<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">

  <!-- card background -->
  <rect width="{W}" height="{H}" rx="8" fill="#0d1117" stroke="#30363d" stroke-width="1"/>

  <!-- header title -->
  <text x="{PAD}" y="26"
    font-family="system-ui,-apple-system,sans-serif" font-size="14" font-weight="600" fill="#e6edf3">Open Source Contributions</text>

  <!-- merged badge -->
  <rect x="{PAD}" y="34" width="56" height="18" rx="9" fill="#8957e51a" stroke="#8957e5" stroke-width="1"/>
  <text x="{PAD + 28}" y="47" text-anchor="middle"
    font-family="system-ui,sans-serif" font-size="10" fill="#d2a8ff">merged</text>
  <text x="{PAD + 66}" y="47"
    font-family="system-ui,sans-serif" font-size="12" font-weight="600" fill="#e6edf3">{total} PRs</text>
  <text x="{W - PAD}" y="47" text-anchor="end"
    font-family="system-ui,sans-serif" font-size="11" fill="#484f58">last {days} days</text>

  <!-- divider -->
  <line x1="{PAD}" y1="{HEADER_H - 4}" x2="{W - PAD}" y2="{HEADER_H - 4}" stroke="#21262d" stroke-width="1"/>

  {"".join(rows)}

  <!-- footer -->
  <text x="{W - PAD}" y="{H - 10}" text-anchor="end"
    font-family="system-ui,sans-serif" font-size="10" fill="#484f58">Updated: {today}</text>
</svg>
"""


def update_readme(svg_filename: str) -> None:
    readme_path = "README.md"
    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    if START_MARKER not in content or END_MARKER not in content:
        raise ValueError(
            f"README.md is missing markers:\n  {START_MARKER}\n  {END_MARKER}"
        )

    replacement = f"{START_MARKER}\n![Open Source Contributions]({svg_filename})\n{END_MARKER}"
    start = content.index(START_MARKER)
    end = content.index(END_MARKER) + len(END_MARKER)

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(content[:start] + replacement + content[end:])


def main() -> None:
    parser = argparse.ArgumentParser(description="Update README with merged PRs SVG card")
    parser.add_argument("--days", type=int, default=30,
                        help="Number of days to look back (default: 30)")
    args = parser.parse_args()

    username = os.environ.get("GITHUB_USERNAME", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()

    if not username or not token:
        raise EnvironmentError("GITHUB_USERNAME and GITHUB_TOKEN must be set")

    print(f"Fetching merged PRs for @{username} in the last {args.days} days...")
    prs = fetch_merged_prs(username, token, args.days)
    print(f"Found {len(prs)} merged PR(s)")

    svg_filename = "merged-prs.svg"
    svg = generate_svg(prs, args.days, username)

    with open(svg_filename, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"Generated {svg_filename}")

    update_readme(svg_filename)
    print("README.md updated successfully")


if __name__ == "__main__":
    main()
