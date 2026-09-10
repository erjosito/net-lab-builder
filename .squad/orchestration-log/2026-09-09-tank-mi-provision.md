# MI Provisioning — tank / general-purpose / sync

**Date:** 2026-09-09  
**Agent:** tank (general-purpose)  
**Mode:** sync  
**Task:** MI provision. Created snet-mi delegated to Microsoft.Sql/managedInstances with route table rt-snet-mi and NSG nsg-snet-mi, then provisioned Managed Instance ltrlab552754-mi (GP_Gen5, 4 vCore, 32 GB, AHB BasePrice, Local redundancy, Entra-only, UAMI primary).

**Outcome:** SUCCESS

**Evidence:** Commit a851507  
**Duration:** Provisioned faster than budgeted 4-6 hours.

**Key finding:** Network intent policy (Microsoft.Sql-managedInstances_UseOnly routes + NSG rules) must be left in place after MI provisioning. Do not attempt to converge route tables or NSGs back to empty/default state post-provisioning. Use read-only verification instead.
