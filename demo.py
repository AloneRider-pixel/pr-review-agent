"""Offline demo: review a sample diff through the real pipeline (no GitHub needed)."""
from app.llm import LLMClient
from app.reviewer import review_diff, format_summary_comment

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

if __name__ == "__main__":
    llm = LLMClient()
    review, provider = review_diff(SAMPLE_DIFF, llm)
    print(f"provider: {provider}")
    print(format_summary_comment(review, provider))
