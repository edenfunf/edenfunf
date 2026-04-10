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


def build_table(prs: list[dict], days: int) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    header_lines = [
        f"### Merged Pull Requests &nbsp;·&nbsp; Last {days} days",
        f"<sub>Updated: {today}</sub>",
        "",
    ]

    if not prs:
        return "\n".join(header_lines) + "\n_No merged PRs in this period._"

    table_lines = [
        "| | Repository | Pull Request | Merged |",
        "|:---:|:---|:---|:---:|",
    ]

    for pr in prs:
        org = pr["repository"]["owner"]["login"]
        repo = pr["repository"]["nameWithOwner"]
        title = pr["title"].replace("|", "\\|")
        url = pr["url"]
        logo = f"https://github.com/{org}.png?size=20"
        merged_month = pr["mergedAt"][:7]  # YYYY-MM

        table_lines.append(
            f'| <img src="{logo}" width="20" alt="{org}"> '
            f"| `{repo}` "
            f"| [{title}]({url}) "
            f"| {merged_month} |"
        )

    return "\n".join(header_lines + table_lines)


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

    table = build_table(prs, args.days)
    update_readme(table)
    print("README.md updated successfully")


if __name__ == "__main__":
    main()
