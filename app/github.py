"""Minimal GitHub API client for PR diffs and comments (stdlib only)."""
import json
import os
import urllib.request


class GitHubClient:
    def __init__(self, token=None, api_base="https://api.github.com"):
        self.token = token or os.getenv("GITHUB_TOKEN", "")
        self.api_base = api_base.rstrip("/")

    def _request(self, method, path, payload=None, accept="application/vnd.github+json"):
        req = urllib.request.Request(
            self.api_base + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": accept,
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            })
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
            return json.loads(body) if body else {}

    def fetch_diff(self, owner, repo, pr_number):
        req = urllib.request.Request(
            f"{self.api_base}/repos/{owner}/{repo}/pulls/{pr_number}",
            headers={"Authorization": f"Bearer {self.token}",
                     "Accept": "application/vnd.github.v3.diff"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode()

    def post_comment(self, owner, repo, pr_number, body):
        return self._request(
            "POST", f"/repos/{owner}/{repo}/issues/{pr_number}/comments", {"body": body})

    def post_review_comments(self, owner, repo, pr_number, commit_sha, findings):
        """Post inline review comments; falls back per-finding so one bad line
        mapping never loses the rest."""
        posted, failed = [], []
        for f in findings:
            try:
                self._request("POST", f"/repos/{owner}/{repo}/pulls/{pr_number}/comments",
                              {"body": f"**{f['severity']}**: {f['comment']}",
                               "commit_id": commit_sha, "path": f["file"],
                               "line": f["line"], "side": "RIGHT"})
                posted.append(f)
            except Exception as exc:  # noqa: BLE001 - e.g. line not in diff
                failed.append((f, str(exc)))
        return posted, failed
