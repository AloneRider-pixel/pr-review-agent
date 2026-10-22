import hashlib
import hmac
import json
import os

os.environ["AGENT_LLM"] = "mock"

from fastapi.testclient import TestClient

from app.llm import LLMClient, MockProvider
from app.main import app, _verify_signature
from app.reviewer import review_diff, format_summary_comment, extract_json

SAMPLE_DIFF = """--- a/app.py
+++ b/app.py
@@ -1,4 +1,9 @@
 import os
+
+password = "hunter2"
+
 def run(user_code):
-    return None
+    print("running")
+    result = eval(user_code)
+    return result
"""

CLEAN_DIFF = """--- a/util.py
+++ b/util.py
@@ -1,2 +1,3 @@
 def add(a, b):
+    # validated inputs
     return a + b
"""


def test_mock_review_finds_planted_issues():
    review, provider = review_diff(SAMPLE_DIFF, LLMClient(providers=[MockProvider()]))
    assert provider == "mock/offline-deterministic"
    assert len(review["findings"]) >= 3
    kinds = {f["comment"] for f in review["findings"]}
    assert any("credential" in c or "secret" in c for c in kinds)
    assert any("eval" in c for c in kinds)
    assert all(f["line"] > 0 and f["file"] == "app.py" for f in review["findings"])


def test_clean_diff_yields_no_findings():
    review, _ = review_diff(CLEAN_DIFF, LLMClient(providers=[MockProvider()]))
    assert review["findings"] == []


def test_dirty_json_recovery():
    class Dirty(MockProvider):
        def complete(self, prompt):
            return "Here you go:\n```json\n" + super().complete(prompt) + "\n```"
    review, _ = review_diff(SAMPLE_DIFF, LLMClient(providers=[Dirty()]))
    assert review["findings"]  # parser recovered through the fences


def test_unparseable_llm_output_falls_back():
    class Garbage(MockProvider):
        def complete(self, prompt):
            return "sorry, cannot review"
    review, _ = review_diff(SAMPLE_DIFF, LLMClient(providers=[Garbage()]))
    assert review["findings"] == []
    assert "could not be parsed" in review["summary"]


def test_api_review_endpoint():
    client = TestClient(app)
    r = client.post("/review", json={"diff": SAMPLE_DIFF})
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "mock/offline-deterministic"
    assert len(body["findings"]) >= 3


def test_summary_comment_format():
    review, provider = review_diff(SAMPLE_DIFF, LLMClient(providers=[MockProvider()]))
    md = format_summary_comment(review, provider)
    assert "| File | Line | Severity | Comment |" in md
    assert "app.py" in md


def test_webhook_signature_verification():
    secret = "s3cret"
    body = b'{"action":"opened"}'
    good = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert _verify_signature(secret, body, good)
    assert not _verify_signature(secret, body, "sha256=deadbeef")
    assert not _verify_signature(secret, body, None)
    assert _verify_signature("", body, None)  # no secret configured: local dev passes


def test_webhook_ignores_non_pr_events():
    client = TestClient(app)
    r = client.post("/webhook", json={"action": "opened"}, headers={"X-GitHub-Event": "push"})
    assert r.status_code == 200 and r.json()["ignored"] == "push"
