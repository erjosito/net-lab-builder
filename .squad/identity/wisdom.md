---
last_updated: 2026-05-28T12:36:50.596Z
---

# Team Wisdom

Reusable patterns and heuristics learned through work. NOT transcripts — each entry is a distilled, actionable insight.

## Patterns

<!-- Append entries below. Format: **Pattern:** description. **Context:** when it applies. -->

**Pattern:** When a manifest is re-authored after a blocking review, verify all stated corrections against the authoritative design *and* against the original blocking criteria independently -- do not rely solely on the author's corrections summary. A line-by-line checklist against the design spec surfaces any correction applied correctly in the summary but misimplemented in the artifact. **Context:** Any multi-reviewer handoff where the original author is locked out and a second author implements someone else's review feedback.

**Pattern:** Cost guardrail status must distinguish between "pricing not found" (no evidence) and "pricing found but tier mapping unresolved" (partial evidence). The latter requires exposing the full min-max range and blocking deployment until the owner explicitly acknowledges both endpoints. Never collapse a wide cost range to the optimistic end when the pessimistic end exceeds the guardrail. **Context:** Any lab with a managed hardware-tier service whose ARM SKU parameters do not map 1:1 to published pricing tiers (e.g., Azure VNRA `scalingBandwidth` vs Retail API Basic/Standard).
