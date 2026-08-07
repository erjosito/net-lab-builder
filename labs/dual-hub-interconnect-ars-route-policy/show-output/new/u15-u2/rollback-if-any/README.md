# Rollback — not exercised

Neither U1.5 nor U2 triggered a rollback condition during this execution
session.

- **U1.5** (Poland-state removal on vm-nva1, then vm-nva2): route delta was
  exactly `10.30.0.0/27` on both NVAs as required, gateway/on-prem route
  captures were byte-identical, and no BGP session flap occurred. The
  `birdc configure undo` / backup-restore path defined in the approved plan
  was never invoked.
- **U2** (`rm-hub1-tmp-assoc` creation + association on `peer-nva1`): the PUT
  succeeded to `provisioningState: Succeeded`, all `vnetRoutes` /
  `staticRoutesConfig` / `peerAsn` / `peerIp` fields were preserved
  byte-for-byte, routes stayed byte-identical B1→B2, and BGP sessions showed
  no reset. The documented recovery path (restore exact pre-U2 body with
  `If-Match` + delete the temp route map) was never invoked.

This folder is intentionally empty of transcripts. Its presence documents that
the rollback path was considered and prepared (see
`scripts/rollback.ps1` and `scripts/bodies/bgpconn-restore-hub1.json`) but not
needed.
