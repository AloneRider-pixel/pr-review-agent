"""Turn a unified diff into validated review findings via the LLM."""
import json
import re

REVIEW_PROMPT = """REVIEW_JSON:
You are a senior code reviewer. Review this unified diff and reply with ONE JSON object
(no prose, no markdown):
{{
  "summary": "one paragraph overall assessment",
  "findings": [{{"file": "path", "line": 12, "severity": "high|medium|low",
                 "comment": "what is wrong and how to fix it"}}]
}}
Only report real defects, security issues, or clear maintainability problems introduced
by this diff. If there are none, return an empty findings list.
DIFF:
{diff}
"""


def extract_json(text):
    if not text:
        return None
    cleaned = re.sub(r"```(?:json)?", "", text)
    start = cleaned.find("{")
    if start == -1:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(cleaned[start:])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _valid(review):
    sev = {"high", "medium", "low"}
    return (
        isinstance(review.get("summary"), str)
        and isinstance(review.get("findings"), list)
        and all(isinstance(f, dict) and f.get("file") and f.get("comment")
                and str(f.get("severity", "")).lower() in sev
                and isinstance(f.get("line"), int) and f["line"] > 0
                for f in review["findings"])
    )


def review_diff(diff, llm, retries=1):
    """Returns (review_dict, provider_name). Retries invalid LLM output once,
    then falls back to an empty-but-honest review marked as unparseable."""
    prompt = REVIEW_PROMPT.format(diff=diff)
    for _ in range(retries + 1):
        raw = llm.complete(prompt)
        review = extract_json(raw)
        if review and _valid(review):
            for f in review["findings"]:
                f["severity"] = f["severity"].lower()
            return review, llm.active.name
        prompt += "\nPrevious reply was not valid review JSON. Reply with JSON only."
    return {"summary": "LLM output could not be parsed; no automated findings. Manual review needed.",
            "findings": []}, llm.active.name


def format_summary_comment(review, provider):
    lines = [f"**Automated PR review** (provider: {provider})", "", review["summary"], ""]
    if review["findings"]:
        lines.append("| File | Line | Severity | Comment |")
        lines.append("|---|---|---|---|")
        for f in review["findings"]:
            lines.append(f"| {f['file']} | {f['line']} | {f['severity']} | {f['comment']} |")
    else:
        lines.append("No issues found by the automated pass.")
    return "\n".join(lines)
