# Squad Team

> net-lab-builder

## Coordinator

| Name | Role | Notes |
|------|------|-------|
| Squad | Coordinator | Routes work, enforces handoffs and reviewer gates. |

## Members

| Name | Role | Charter | Status |
|------|------|---------|--------|
| 🏗️ Morpheus | Lead / Architect | [charter](agents/morpheus/charter.md) | active |
| 🌐 Trinity | Azure Network SME | [charter](agents/trinity/charter.md) | active |
| 🔧 Tank | IaC Engineer | [charter](agents/tank/charter.md) | active |
| 🧪 Niobe | Lab Validator & Diagnostics | [charter](agents/niobe/charter.md) | active |
| 🔮 Oracle | Documentation & Diagrams | [charter](agents/oracle/charter.md) | active |
| 📋 Scribe | Memory / Session Logger | [charter](agents/scribe/charter.md) | active (silent) |
| 🔄 Ralph | Persistent Watcher / Circuit Breaker | [charter](agents/ralph/charter.md) | active (monitor) |

## Member Notes

> **🌐 Trinity vault link:** Reads and writes `C:\Users\jomore\OneDrive - Microsoft\ObsidianVaults\AzureNetworking\` — Jose's curated Azure Networking Obsidian vault. Trinity is the **only** squad member with write access; vault touches by other members must route through Trinity. See Trinity's charter, **"Vault Stewardship"** section, for the full read/write protocol and sanitization rules. The vault has its own `AGENTS.md` schema that Trinity reloads on every dispatch.

## Project Context

- **Owner:** Jose Moreno
- **Project:** net-lab-builder — build, document, and tear down ephemeral Azure Networking labs
- **Workflow:** requirements → architecture → region & SKU selection → IaC deploy → validate → diagnose (effective routes, traceroutes, logs, metrics) → portal screenshots → write `labs/<name>/` artifact → cleanup
- **Layout:** `labs/<lab-name>/` per-lab artifact (summary, lessons learned, show command output, screenshots); `src/` shared IaC and scripts (Azure CLI, PowerShell, Bicep, Terraform)
- **Universe:** The Matrix
- **Created:** 2026-05-28
