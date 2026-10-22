"""FastAPI webhook surface for the PR review agent."""
import hashlib
import hmac
import os

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from pydantic import BaseModel

from . import reviewer
from .github import GitHubClient
from .llm import LLMClient

app = FastAPI(title="PR Review Agent", version="1.0.0")
llm = LLMClient()


class ReviewRequest(BaseModel):
    diff: str


def _verify_signature(secret: str, body: bytes, signature: str | None):
    if not secret:
        return True  # no secret configured: accept (local dev)
    if not signature or not signature.startswith("sha256="):
        return False
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={digest}", signature)


def _handle_pr(owner, repo, number, sha):
    gh = GitHubClient()
    diff = gh.fetch_diff(owner, repo, number)
    review, provider = reviewer.review_diff(diff, llm)
    posted, failed = gh.post_review_comments(owner, repo, number, sha, review["findings"])
    summary = reviewer.format_summary_comment(review, provider)
    if failed:
        summary += f"\n\n_Note: {len(failed)} inline comment(s) could not be mapped to diff lines._"
    gh.post_comment(owner, repo, number, summary)


@app.get("/health")
def health():
    return {"status": "ok", "provider": llm.active.name}


@app.post("/review")
def review_adhoc(body: ReviewRequest):
    """Ad-hoc review of a pasted diff (used by demo.py and tests)."""
    review, provider = reviewer.review_diff(body.diff, llm)
    return {"provider": provider, **review}


@app.post("/webhook")
async def webhook(request: Request, background: BackgroundTasks):
    body = await request.body()
    sig = request.headers.get("X-Hub-Signature-256")
    if not _verify_signature(os.getenv("WEBHOOK_SECRET", ""), body, sig):
        raise HTTPException(status_code=401, detail="bad signature")
    event = request.headers.get("X-GitHub-Event", "")
    if event != "pull_request":
        return {"ignored": event}
    payload = await request.json()
    if payload.get("action") not in ("opened", "synchronize", "reopened"):
        return {"ignored": payload.get("action")}
    pr = payload["pull_request"]
    owner = payload["repository"]["owner"]["login"]
    repo = payload["repository"]["name"]
    background.add_task(_handle_pr, owner, repo, pr["number"], pr["head"]["sha"])
    return {"queued": pr["number"]}
