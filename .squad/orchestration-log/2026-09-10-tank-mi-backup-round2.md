# MI BACKUP TO URL Round 2 — tank / general-purpose / background  

**Date:** 2026-09-10T12:23:44Z  
**Agent:** tank (general-purpose)  
**Mode:** background  
**Task:** Managed Identity backup to URL, round 2 after TDE remediation (two-step process).

**Outcome:** SUCCESS, end-to-end proven

**Evidence:** Commit 7f950f6

**Key finding:** Service-managed TDE requires TWO steps to disable:  
1. `ALTER DATABASE ... SET ENCRYPTION OFF`  
2. `DROP DATABASE ENCRYPTION KEY`  

The first step alone (reaching encryption_state=1) is insufficient. Backup still fails with Msg 41938 until DEK is dropped.

**Proof:** End-to-end native .bak backup to Azure Storage with:
- User-assigned managed identity (Storage Blob Data Contributor)
- Storage account with allowSharedKeyAccess=false and publicNetworkAccess=Disabled
- Private endpoint connectivity only
- RESTORE VERIFYONLY succeeded
- Blob confirmed from inside VNet: mitest.bak, 11927552 bytes

**Closes:** Last load-bearing unverified assumption in the lab.
