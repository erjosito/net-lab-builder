**Archived entries:** see `history-archive.md`

# Project Context

- **Owner:** Jose Moreno
- **Project:** net-lab-builder
- **Role:** IaC executor and evidence capture

## Historical summaries

- **2026-08 labs and route-map work:** executed scoped Azure changes, captured before-and-after evidence, and documented platform-driven deviations instead of hiding them.
- **2026-09 SQL LTR work:** closed the attempted measurement chain once the backups were proven empty or unavailable for the intended timing experiment.
- **Earlier SAP RISE deploy work:** deployed the lab, documented four live deviations, and handed the scenario into validation and repair rounds.

## Learnings

### 2026-09-29 - The reliable way to apply multiline VM changes from Windows is `--scripts @file`

- The first Defect E retries reported outer Azure success but did not produce trustworthy inner stdout or heredoc execution.
- Writing the guest script to `deploy\scripts\hub-bird-kernel-export-fix.sh` and invoking `az vm run-command invoke --scripts @file` produced the proof the team actually needed: `birdc configure` output plus the expected Linux FIB route.
- Keep using this pattern for future multiline guest changes in this lab.

### 2026-09-29 - A/B/C and D1/D2/E are applied and verified, but they did not close the final CE-to-spoke hop

- A, B, and C all landed with the expected Azure-side proof.
- D1, D2, and E landed after the `@file` transport correction, and the ordered verification advanced from the hub route check through a successful CE-to-hub ping.
- The authoritative stage then still failed at `vm-ce-onprem -> 10.60.0.4`, so no extra self-directed fix was attempted.

### 2026-09-29 - F1 and F2 landed, fallback diagnostics captured, issue remains with Trinity

- Spoke NSG rule `Allow-OnpremSim-Forwarded-In` and route table `rt-spoke-nva-return` were both applied and verified.
- The CE-to-spoke-NVA probe still returned `100% packet loss`, so the fallback diagnostics were run exactly as requested.
- Current handoff artifact: `labs/sap-rise-scoped-peering-fwaas/show-output/s1-spoke-reachability-fix-20260929T173839Z/`. Do not improvise beyond that evidence without a new Trinity spec.
