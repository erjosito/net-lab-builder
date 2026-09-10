# Roadmap Scan — oracle / research / background

**Date:** 2026-09-10  
**Agent:** oracle (research)  
**Mode:** background  
**Task:** MI BACKUP TO URL public roadmap scan.

**Outcome:** SUCCESS

**Evidence:** Commit e0dfc58 (file)  

**Findings (6 total):**

1. MI BACKUP TO URL with managed identity is confirmed GA for Azure SQL Managed Instance (not preview).
2. SQL Database import/export over Private Link is available (addresses public endpoint blocker).
3. SQL Database import/export with managed identity is in preview (addresses shared-key blocker).
4. Combined path (import/export + managed identity + Private Link) is not documented as tested.
5. All three capabilities are on different release timelines. Combined GA path not yet declared.
6. MI database copy/move across subscriptions is GA but does not move PITR or LTR backups.

**Recommendation:** For compliance-critical drain deadlines, use client-side sqlpackage from in-VNet compute unless both features reach GA and combined path is documented.
