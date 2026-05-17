---
name: feedback-honest-verification
description: "User pushes back on confident claims that weren't fully verified — answer \"didn't verify\" honestly"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 2b184b19-1809-4a2e-bad8-ec19ea9ee94c
---

When I declared "claude-context-core indexing is fully functional ✅" after a single smoke test, the user replied: *"did you verify claude-context indexing to be fully functional?"* — meaning they could tell I was overclaiming. The actual verification was partial (indexing reported success but Milvus row count was 0 due to lazy stats; I had to flush + query to prove 177 rows were really there).

**Why:** the user is calibrating whether to trust my reports of system state. False positives cost trust faster than honest "haven't verified" admissions.

**How to apply:**
1. When I say "X works" or "X verified," I must have actually exercised X end-to-end with output I can quote — not "the function returned without raising."
2. When I haven't done that level of verification, say "I haven't verified — only the smoke test passed; I'd need to do A/B/C to be sure" rather than ✅.
3. If the user pushes back, re-do the verification with stricter checks and report what was actually run vs what was inferred.
4. Avoid 🎯 and ✅ in summaries unless the matching verification is in the transcript.
