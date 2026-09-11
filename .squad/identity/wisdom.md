---
last_updated: 2026-09-11T12:40:00.000Z
---

# Team Wisdom

Reusable patterns and heuristics learned through work. NOT transcripts — each entry is a distilled, actionable insight.

## Patterns

<!-- Append entries below. Format: **Pattern:** description. **Context:** when it applies. -->

**Pattern:** When a manifest is re-authored after a blocking review, verify all stated corrections against the authoritative design *and* against the original blocking criteria independently -- do not rely solely on the author's corrections summary. A line-by-line checklist against the design spec surfaces any correction applied correctly in the summary but misimplemented in the artifact. **Context:** Any multi-reviewer handoff where the original author is locked out and a second author implements someone else's review feedback.

**Pattern:** Cost guardrail status must distinguish between "pricing not found" (no evidence) and "pricing found but tier mapping unresolved" (partial evidence). The latter requires exposing the full min-max range and blocking deployment until the owner explicitly acknowledges both endpoints. Never collapse a wide cost range to the optimistic end when the pessimistic end exceeds the guardrail. **Context:** Any lab with a managed hardware-tier service whose ARM SKU parameters do not map 1:1 to published pricing tiers (e.g., Azure VNRA `scalingBandwidth` vs Retail API Basic/Standard).

**Pattern:** Verify the check before reporting the defect. A narrow grep scope, a case-sensitive match, a line-wrapped quote and a wrong resource name all produce output identical to a genuine regression: zero hits. When a verification step says something is missing, first prove the check itself can find a thing you know exists. In one session four separate "defects" in a reviewed artifact were all faults in the verifying regex, and one of them briefly suggested that surviving backups had been deleted. **Context:** Any independent verification of delegated work, especially automated sweeps for constants, filenames or required phrases.

**Pattern:** A hedging sentence has a shelf life, and it will not appear in the diff when it expires. Statements like "not yet measured", "unproven" or "we did not test X" are correct when written and silently become false the moment the evidence lands. Whenever new evidence arrives, grep the artifact for the hedging vocabulary before publishing, and retract by replacing the sentence with the finding rather than deleting it. **Context:** Any long-lived document written alongside in-flight experiments, particularly when work is delegated and the instruction that produced the hedge came from a now-outdated brief.

**Pattern:** Success status is not payload verification. Operations report `Succeeded` or `Online` while carrying nothing: a restored database reported healthy, produced a plausible linear timing fit, and contained zero rows. The fit looked better than the honest one. Gate on the payload (row count, checksum, byte length read back from the destination), never on the operation's own status, and never fit a model to data that has not passed that gate. **Context:** Restore, copy, import and replication operations, and any measurement derived from them.

**Pattern:** A limitation recalled from memory is a hypothesis, not a fact, and it is the most expensive kind of error because it closes off a viable path before anyone tests it. Two confident statements in one project ("this service cannot be stopped" and "this identity cannot cross a tenant boundary") were both wrong, and the second would have forced an unnecessary architecture had it not been checked. Verify a stated constraint against primary documentation before it propagates into a design or a customer message, and correct it explicitly and in writing when it turns out to be wrong. **Context:** Any moment you assert that something is impossible or unsupported, especially in fast-moving areas where a capability may have reached GA since you last looked.
