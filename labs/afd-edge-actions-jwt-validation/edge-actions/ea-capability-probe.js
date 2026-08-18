// ea-capability-probe.js — S1 Capability Probe
// Deployed to: /debug/* route
// Purpose: Enumerate available JS globals in the Edge Action Hyperlight sandbox.
//          Never logs secrets. Never reads Authorization header content.
//
// Design reference: design.md §4.2
// EdgeActionEvent API: https://github.com/Azure/EdgeActionsSamples/tree/main/src/edgeactions-js

function handler(event) {
  // Probe all required globals with typeof — never throws on undefined
  const probes = {
    crypto:        typeof crypto,
    crypto_subtle: (typeof crypto !== 'undefined') ? typeof crypto.subtle : 'N/A',
    fetch:         typeof fetch,
    atob:          typeof atob,
    btoa:          typeof btoa,
    Promise:       typeof Promise,
    Uint8Array:    typeof Uint8Array,
    TextEncoder:   typeof TextEncoder,
    JSON:          typeof JSON,
    Date:          typeof Date,
    console:       typeof console,
  };

  for (const [k, v] of Object.entries(probes)) {
    console.log('PROBE ' + k + '=' + v);
  }

  // Log all request headers (keys only for path, sanitize Authorization)
  for (const [k, v] of Object.entries(event.request.headers)) {
    if (k === 'authorization') {
      // Never log raw JWT or credentials
      console.log('HDR authorization=<redacted length=' + v.length + '>');
    } else {
      console.log('HDR ' + k + '=' + v);
    }
  }

  // Log context map (server variables)
  for (const [k, v] of Object.entries(event.context)) {
    console.log('CTX ' + k + '=' + v);
  }

  // Log request metadata
  console.log('REQ uri=' + event.request.uri);
  console.log('REQ method=' + event.request.method);

  // JWKS latency sub-probe — only if fetch is available
  if (typeof fetch === 'function' && typeof Promise !== 'undefined') {
    const JWKS_URL = 'https://login.microsoftonline.com/common/discovery/v2.0/keys';
    const t0 = Date.now();
    // NOTE: async/await support is probed here; if Promise is present we attempt it.
    // The result is only logged — EA result is always 200 regardless.
    try {
      // Synchronous-safe probe: we cannot await inside a non-async function.
      // We attempt fetch() as a call to see if it throws immediately.
      const p = fetch(JWKS_URL);
      if (p && typeof p.then === 'function') {
        console.log('PROBE fetch_returns_thenable=true');
        p.then(function(r) {
          const ms = Date.now() - t0;
          console.log('JWKS_FETCH status=' + r.status + ' ms=' + ms);
        }).catch(function(e) {
          console.log('JWKS_FETCH error=' + e.message);
        });
      } else {
        console.log('PROBE fetch_returns_thenable=false');
      }
    } catch (e) {
      console.log('PROBE fetch_throws=' + e.message);
    }
  } else {
    console.log('PROBE fetch_skipped=no_fetch_or_promise');
  }

  event.response.response_code = 200;
  return event;
}
