#!/usr/bin/env python3
"""setup_github.py: create labels, sprint milestones, user stories and task issues
from scripts/backlog.py, and optionally add them all to the GitHub Project board.

Safe to run more than once: existing labels are updated, existing milestones and
issues (same title) are skipped.

Needs the GitHub CLI (`gh`) logged in:  gh auth login
For the board step also:                gh auth refresh -s project

Usage:
    python3 scripts/setup_github.py                  # labels, milestones, issues
    python3 scripts/setup_github.py --project 1      # ...and add all to board no. 1
"""
import argparse
import json
import subprocess
import sys

from backlog import REPO, LABELS, MILESTONES, STORIES, TASKS


def gh(*args, data=None):
    """Run `gh` and return parsed JSON (or None)."""
    cmd = ["gh", *args]
    if data is not None:
        cmd += ["--input", "-"]
    res = subprocess.run(cmd, input=json.dumps(data) if data is not None else None,
                         capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"{' '.join(args[:3])}: {res.stderr.strip()}")
    return json.loads(res.stdout) if res.stdout.strip() else None


def api(method, path, data=None):
    return gh("api", "-X", method, f"repos/{REPO}/{path}", data=data)


def all_pages(path):
    out, page = [], 1
    while True:
        batch = api("GET", f"{path}{'&' if '?' in path else '?'}per_page=100&page={page}")
        out += batch
        if len(batch) < 100:
            return out
        page += 1


def setup_labels():
    existing = {l["name"] for l in all_pages("labels")}
    for name, (color, desc) in LABELS.items():
        body = {"name": name, "color": color, "description": desc}
        if name in existing:
            api("PATCH", f"labels/{name.replace(':', '%3A').replace(' ', '%20')}", body)
            print(f"  label updated   {name}")
        else:
            api("POST", "labels", body)
            print(f"  label created   {name}")


def setup_milestones():
    existing = {m["title"]: m["number"] for m in all_pages("milestones?state=all")}
    for title, (due, desc) in MILESTONES.items():
        if title not in existing:
            m = api("POST", "milestones", {"title": title, "description": desc,
                                           "due_on": f"{due}T23:59:00Z"})
            existing[title] = m["number"]
            print(f"  milestone created {title}")
        else:
            print(f"  milestone exists  {title}")
    return existing


def setup_issues(milestones):
    existing = {i["title"]: i for i in all_pages("issues?state=all") if "pull_request" not in i}
    created = []

    def make(title, body, labels, milestone=None):
        if title in existing:
            print(f"  issue exists  #{existing[title]['number']} {title}")
            return existing[title]
        data = {"title": title, "body": body, "labels": labels}
        if milestone:
            data["milestone"] = milestones[milestone]
        issue = api("POST", "issues", data)
        existing[title] = issue
        created.append(issue)
        print(f"  issue created #{issue['number']} {title}")
        return issue

    story_num = {}
    for key, (title, text, labels) in STORIES.items():
        story_num[key] = make(title, f"{text}\n\nTasks for this story reference it with *Part of #…*.",
                              labels)["number"]

    for sprint, title, labels, story, done in TASKS:
        body = "**Done when**\n" + "\n".join(f"- [ ] {d}" for d in done)
        if story:
            body += f"\n\n**Part of** #{story_num[story]}"
        make(title, body, labels, sprint)

    return list(existing.values())


def add_to_board(project, issues):
    owner = REPO.split("/")[0]
    for issue in issues:
        try:
            gh("project", "item-add", str(project), "--owner", owner,
               "--url", issue["html_url"], "--format", "json")
            print(f"  on board      #{issue['number']}")
        except RuntimeError as e:
            print(f"  board failed  #{issue['number']}: {e}", file=sys.stderr)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--project", type=int, help="GitHub Project number to add all issues to")
    args = p.parse_args()

    print("Labels");      setup_labels()
    print("Milestones");  ms = setup_milestones()
    print("Issues");      issues = setup_issues(ms)
    if args.project:
        print("Board");   add_to_board(args.project, issues)
    print("Done.")


if __name__ == "__main__":
    main()
