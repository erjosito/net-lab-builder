# SQL LTR Lab Calibration Session Log

**Session:** 2026-09-10T09:35:25Z  
**Topic:** sql-ltr-lab-calibration  
**Agents:** Oracle, Tank, Coordinator

## Summary

Lab calibration session completed. Oracle rewrote README with comprehensive context and diagrams. Tank measured BACPAC compression (validated 4.0x for realistic data; 1.04x to 145x range) and export throughput (0.36 + 0.159 * SizeGb formula, R-squared 0.9995). Coordinator verified VM creation recovery and private networking end-to-end.

## Key Outcomes

- BACPAC compression validated: 4.0x is accurate for realistic data; safe floor is 1.04x for incompressible data
- Export formula established with high confidence (R-squared 0.9995)
- LTR constraints documented: no auto-pause + LTR coexistence; LTR policy doesn't trigger immediate PITR backup copy
- README now includes non-DBA context, scoping questions, caveats, and process recommendations
- Two commits merged; no outstanding infrastructure changes

## Decisions Merged

1. Tank: BACPAC compression range and export throughput measured and documented
2. Kid: Blog diagrams must be verified inline in rendered post (decision merged from inbox)

## Evidence

- Six show-output files with raw measurements
- Calibrated parameters with measured data (RestoreMeasured: false for unmeasured restore path)
- Mermaid diagrams rendered and validated
- VM operational with private networking confirmed

