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


def build_section(prs: list[dict], days: int) -> str:
    count = len(prs)
    search_url = f"https://github.com/search?q=author%3Aedenfunf+is%3Apr+is%3Amerged&type=pullrequests"

    # Purple "merged" badge linking to PR search
    badge = (
        f'<a href="{search_url}">'
        f'<img src="https://img.shields.io/badge/merged-{count}%20PRs-8957e5?style=flat-square&logo=git-merge&logoColor=white" alt="merged PRs">'
        f"</a>"
    )

    if not prs:
        return badge

    # Deduplicate orgs, preserve order
    seen_orgs: set[str] = set()
    org_logos: list[str] = []
    for pr in prs:
        org = pr["repository"]["owner"]["login"]
        repo = pr["repository"]["nameWithOwner"]
        if org not in seen_orgs:
            seen_orgs.add(org)
            repo_url = f"https://github.com/{repo}"
            logo = f"https://github.com/{org}.png?size=20"
            org_logos.append(
                f'<a href="{repo_url}">'
                f'<img src="{logo}" width="20" alt="{org}" title="{org}">'
                f"</a>"
            )

    logos_line = " &nbsp; ".join(org_logos)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    return (
        f"{badge} &nbsp; {logos_line}\n"
        f"<sub>last {days} days &nbsp;·&nbsp; {today}</sub>"
    )


def update_readme(table_content: str) -> None:
    readme_path = "README.md"
    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    if START_MARKER not in content or END_MARKER not in content:
        raise ValueError(
            f"README.md is missing markers:\n  {START_MARKER}\n  {END_MARKER}"
        )

    start_idx = content.index(START_MARKER) + len(START_MARKER)
    end_idx = content.index(END_MARKER)

    new_content = (
        content[: content.index(START_MARKER)]
        + START_MARKER
        + "\n"
        + table_content
        + "\n"
        + END_MARKER
        + content[end_idx + len(END_MARKER) :]
    )

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(new_content)


def main() -> None:
    parser = argparse.ArgumentParser(description="Update README with merged PRs")
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days to look back (default: 30)",
    )
    args = parser.parse_args()

    username = os.environ.get("GITHUB_USERNAME", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()

    if not username or not token:
        raise EnvironmentError("GITHUB_USERNAME and GITHUB_TOKEN must be set")

    print(f"Fetching merged PRs for @{username} in the last {args.days} days...")
    prs = fetch_merged_prs(username, token, args.days)
    print(f"Found {len(prs)} merged PR(s)")

    table = build_section(prs, args.days)
    update_readme(table)
    print("README.md updated successfully")


if __name__ == "__main__":
    main()
