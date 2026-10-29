#!/usr/bin/env python3
"""Rewrite the contributions section of this profile README from GitHub search: merged pull requests into
repositories that are neither the author's nor the employer's. Repositories are sorted by stars, highest first.
Runs daily in GitHub Actions. Standard library only."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

AUTHOR = "jay23606"
EXCLUDE = ["-user:jay23606", "-org:UltraSignup1"]  # own repositories, and the employer's organisation
START, END = "<!-- contributions:start -->", "<!-- contributions:end -->"
TOP = 5  # repositories named in the summary line
README = Path(__file__).resolve().parent.parent / "README.md"


def merged_prs() -> list:
    cmd = ["gh", "search", "prs", "--author", AUTHOR, "--merged", "--limit", "1000",
           "--json", "repository,number,title,url,closedAt", "--", *EXCLUDE]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout or "[]")


def stars(full: str):
    """Stargazer count, or None for a missing repository (HTTP 404)."""
    result = subprocess.run(["gh", "api", f"repos/{full}", "--jq", ".stargazers_count"],
                            capture_output=True, text=True)
    if result.returncode != 0:
        if re.search(r"\bHTTP 404\b", result.stderr or ""):
            return None
        raise RuntimeError(f"Cannot fetch stars for {full} (gh exit {result.returncode})")
    text = result.stdout.strip()
    if not text.isdigit():
        raise ValueError(f"Invalid stargazer count for {full}")
    return int(text)


def cell(text: str) -> str:
    """One line, with pipes escaped so a title cannot break the table."""
    return " ".join(text.replace("|", "\\|").split())


def repo_cell(full: str, count) -> str:
    stars_text = f" · ★ {count:,}" if count is not None else ""
    return f"[{full}](https://github.com/{full}){stars_text}"


def section(prs: list) -> str:
    """The contributions body, without the date line. It is compared with the README to decide whether to write."""
    if not prs:
        return "No merged pull requests found yet."
    by_repo = defaultdict(list)
    for pr in prs:
        by_repo[pr["repository"]["nameWithOwner"]].append(pr)
    star_counts = {r: stars(r) for r in by_repo}
    repos = sorted(by_repo, key=lambda r: (-(star_counts[r] or 0), -len(by_repo[r]), r.lower()))
    top = ", ".join(repo_cell(r, star_counts[r]) for r in repos[:TOP])
    rows = []
    for r in repos:
        merged = sorted(by_repo[r], key=lambda p: p["closedAt"], reverse=True)
        for i, pr in enumerate(merged):
            name = repo_cell(r, star_counts[r]) if i == 0 else ""  # repository name once per group
            rows.append(f"| {name} | [#{pr['number']} {cell(pr['title'])}]({pr['url']}) |")
    return "\n".join([
        f"**{len(prs)} merged pull requests** across **{len(repos)} repositories**. Most starred: {top}.",
        "",
        "<details>",
        f"<summary>Show all {len(repos)} repositories</summary>",
        "",
        "| Repository | Pull request |",
        "| --- | --- |",
        *rows,
        "",
        "</details>",
    ])


def block(body: str, stamp: str) -> str:
    return f"{START}\n{body}\n\n_Updated {stamp} (UTC) by a scheduled GitHub Action._\n{END}"


def current_body(text: str) -> str | None:
    """The body currently in the README, or None when the section has never been written."""
    m = re.search(re.escape(START) + r"\n(.*?)\n\n_Updated .*?_\n" + re.escape(END), text, re.S)
    return m.group(1) if m else None


def replace_section(text: str, body: str, stamp: str) -> str:
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if pattern.search(text):
        return pattern.sub(lambda _: block(body, stamp), text, count=1)
    return text.rstrip() + "\n\n" + block(body, stamp) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="Refresh the merged contributions list in README.md.")
    ap.add_argument("--print", action="store_true", help="print the section and leave README.md alone")
    args = ap.parse_args()
    body = section(merged_prs())
    if args.print:
        sys.stdout.reconfigure(encoding="utf-8")  # the star symbol is not in every console code page
        print(body)
        return
    text = README.read_text(encoding="utf-8")
    if current_body(text) == body:
        print("no change")  # no daily no-op commits: the history only shows real changes
        return
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    README.write_text(replace_section(text, body, stamp), encoding="utf-8")
    print("updated README.md")


if __name__ == "__main__":
    main()
