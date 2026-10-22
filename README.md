# PR Review Agent

A FastAPI agent that reviews GitHub pull requests and comments on the diff.
Receives the `pull_request` webhook, fetches the diff, asks an LLM for structured
findings, posts inline review comments plus a summary table.

## What it does

- `POST /webhook` - GitHub webhook endpoint. Verifies `X-Hub-Signature-256` (HMAC-SHA256,
  `WEBHOOK_SECRET` env), reacts to opened/synchronize/reopened PRs, reviews in the background.
- `POST /review` - ad-hoc review of a pasted unified diff (handy for demos and tests).
- `GET /health` - reports the active LLM provider.
- Inline comments per finding (file/line/severity); findings that cannot be mapped to a
  diff line are noted in the summary instead of being dropped.

## LLM: free providers with retry + fallback

`app/llm.py` chains Groq (free tier, `GROQ_API_KEY`) -> Gemini (`GEMINI_API_KEY`) ->
local Ollama -> a deterministic offline mock reviewer. Each provider call retries with
backoff; invalid JSON output is retried once, then an honest "unparseable" summary is
returned. The mock reviewer pattern-scans added lines (eval/exec, hardcoded secrets,
bare except, debug prints) so the whole pipeline runs offline and in CI.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export GROQ_API_KEY=...      # or GEMINI_API_KEY, or run Ollama, or skip for mock mode
export GITHUB_TOKEN=...      # fine-grained PAT with Pull requests: read/write
export WEBHOOK_SECRET=...    # optional; required in production
uvicorn app.main:app --reload
```

## Demo (offline, no GitHub needed)

```bash
python demo.py        # reviews a planted-vulnerability sample diff
pytest tests -q       # 8 tests: findings, JSON recovery, fallback, webhook signature
```

## Wiring a real repo

1. Repo -> Settings -> Webhooks -> Add webhook.
2. Payload URL: `https://<your-host>/webhook`, content type `application/json`,
   secret = your `WEBHOOK_SECRET`, event: Pull requests.
3. Open a PR; the agent posts a summary comment (and inline comments where lines map).

## Honest limitations

- Verified end-to-end offline (mock reviewer, TestClient, webhook signature tests) and
  through a live uvicorn run. Real GitHub posting requires a token and a webhook-reachable
  host; the GitHub client code is small and stdlib-only.
- With the mock provider, findings are pattern rules, not semantic analysis - say so if
  you demo without an API key.
