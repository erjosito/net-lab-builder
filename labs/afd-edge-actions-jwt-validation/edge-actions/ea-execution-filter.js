// ea-execution-filter.js — Controlled failure test version (A4, S9)
// Execution filter: triggered when request carries X-Test-Fail: 1 header
// Purpose: Test fail-open behaviour. This version throws a deliberate exception,
//          causing the platform to terminate execution and pass the request through.
//          S9 uses this to prove that /edge-only fails open (no origin auth)
//          and /protected does NOT fail open (origin re-validates independently).
//
// ⚠️ TEACHING NOTE: This demonstrates that Edge Action fail-open is a real risk.
//    Origin re-validation is mandatory for all protected routes.
//
// Design reference: design.md §8 Failure and Resiliency Table

function handler(event) {
  console.log('EA_EXECUTION_FILTER triggered x-test-fail=1 path=' + (event.request.uri || ''));

  // Strip x-test-fail before any forwarding — never forward to origin
  delete event.request.headers['x-test-fail'];

  // Deliberate exception: forces platform fail-open
  // (platform terminates EA execution; request proceeds as if no EA ran)
  throw new Error('EA_DELIBERATE_EXCEPTION: execution filter test — expect fail-open');
}
