// ea-jwt-validate.js — JWT validation Edge Action (A3, CONDITIONAL path)
//
// ─── S1 CAPABILITY VERDICT (confirmed 2026-08-17, eaprobe2/v1) ─────────────────
// STOP   on RS256/JWKS signature verification
// STOP   on fetch / JWKS endpoint calls
// CONDITIONAL on claim-only enforcement (iss/aud/exp/nbf/roles)
//
// Sandbox capabilities:
//   crypto      = undefined  → signature verification IMPOSSIBLE
//   crypto.subtle = N/A      → RS256/JWKS verify IMPOSSIBLE
//   fetch       = undefined  → JWKS endpoint calls IMPOSSIBLE
//   atob/btoa   = undefined  → use pure-JS base64 only (see below)
//   TextEncoder = undefined
//   Promise     = function   ✅
//   JSON        = object     ✅
//   Date        = function   ✅
//   Uint8Array  = function   ✅
//
// SECURITY ENFORCEMENT MODEL:
//   EA performs: header strip, token structure check, iss/aud/exp/nbf/roles claim check,
//                x-validated-claims + x-edge-jwt-status header injection.
//   ⚠️ EA does NOT verify the JWT signature. Any structurally valid JWT with correct
//   claims passes this filter. The ORIGIN performs full RS256/JWKS cryptographic
//   verification using the `jose` library. Origin is the only security boundary.
//
// API reference: https://github.com/Azure/EdgeActionsSamples/tree/main/src/edgeactions-js
// Design reference: design.md §5

const CONFIG = {
  // Entra v2 client_credentials tokens carry the bare appId as aud (not api:// URI).
  // See: Entra accessTokenAcceptedVersion=2 + client_credentials behavior.
  EXPECTED_AUD: '%%API_APP_ID%%',
  EXPECTED_ISS_TENANT: '%%TENANT_ID%%',
  ADMIN_ROLE: 'Lab.Admin',
};

// Pure-JS base64url decode — atob is unavailable in the EA sandbox
function base64urlDecode(s) {
  var CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  var b64 = s.replace(/-/g, '+').replace(/_/g, '/') +
    '=='.slice(0, (4 - (s.length % 4)) % 4);
  var out = '', buf = 0, bits = 0;
  for (var i = 0; i < b64.length; i++) {
    var c = CHARS.indexOf(b64[i]);
    if (c < 0) continue;
    buf = (buf << 6) | c;
    bits += 6;
    if (bits >= 8) { bits -= 8; out += String.fromCharCode((buf >> bits) & 0xFF); }
  }
  return out;
}

function parseJwtPart(token, idx) {
  var parts = token.split('.');
  if (parts.length !== 3) return null;
  try { return JSON.parse(base64urlDecode(parts[idx])); } catch (e) { return null; }
}

function reject(event, code, reason) {
  console.log('EA_REJECT code=' + code + ' reason=' + reason);
  event.response.response_code = code;
  return event;
}

function handler(event) {
  var path = event.request.uri || '';

  // Strip spoofed inbound headers (prevent client injection)
  delete event.request.headers['x-validated-claims'];
  delete event.request.headers['x-edge-jwt-status'];
  delete event.request.headers['x-test-fail'];

  var authHeader = event.request.headers['authorization'] || '';
  if (authHeader.indexOf('Bearer ') !== 0) {
    event.request.headers['x-edge-jwt-status'] = 'MISSING';
    return reject(event, 401, 'MISSING_TOKEN');
  }
  var token = authHeader.slice(7);

  var hdr = parseJwtPart(token, 0);
  if (!hdr) return reject(event, 401, 'MALFORMED_HEADER');

  var payload = parseJwtPart(token, 1);
  if (!payload) return reject(event, 401, 'MALFORMED_PAYLOAD');

  var now = Math.floor(Date.now() / 1000);
  if (!payload.exp || payload.exp < now) {
    return reject(event, 401, 'EXPIRED exp=' + (payload.exp || 'missing'));
  }
  if (payload.nbf && payload.nbf > now + 60) {
    return reject(event, 401, 'NOT_YET_VALID nbf=' + payload.nbf);
  }

  var aud = typeof payload.aud === 'string' ? payload.aud : ((payload.aud || [])[0] || '');
  if (aud !== CONFIG.EXPECTED_AUD) {
    return reject(event, 401, 'AUD_FAIL got=' + (aud || 'missing'));
  }

  if (!payload.iss || payload.iss.indexOf(CONFIG.EXPECTED_ISS_TENANT) < 0) {
    return reject(event, 401, 'ISS_FAIL got=' + (payload.iss || 'missing'));
  }

  // ⚠️ CLAIMS-ONLY MODE — signature NOT verified (sandbox limits; see header)
  // Origin performs full RS256/JWKS cryptographic verification (jose library).
  console.log('EA_MODE=CLAIMS_ONLY alg=' + (hdr.alg || '?'));

  var roles = payload.roles || [];
  if (path.indexOf('/admin') === 0) {
    if (roles.indexOf(CONFIG.ADMIN_ROLE) < 0) {
      return reject(event, 403, 'ROLE_FAIL required=' + CONFIG.ADMIN_ROLE);
    }
  }

  event.request.headers['x-validated-claims'] = JSON.stringify({
    sub: (payload.sub || 'unknown').slice(0, 8),
    roles: roles,
    exp: payload.exp,
    mode: 'claims_only',
  });
  event.request.headers['x-edge-jwt-status'] = 'VALIDATED';

  console.log('EA_ACCEPT path=' + path + ' roles=' + JSON.stringify(roles));
  return event;
}
