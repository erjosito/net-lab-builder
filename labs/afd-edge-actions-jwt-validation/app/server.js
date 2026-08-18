// Origin API — AFD Edge Actions JWT Validation Lab
// Routes: /health, /public, /edge-only, /protected, /admin, /debug/request
//
// JWT validation at /protected and /admin uses the 'jose' library for:
//   - JWKS key rollover support (auto-fetches from Entra JWKS endpoint)
//   - RS256 / ES256 signature verification
//   - Issuer, audience, expiry claims validation
//   - Lab.Admin app-role check on /admin
//
// Origin hardening: App Service Access Restrictions (ARM-native) enforce
//   AzureFrontDoor.Backend + X-Azure-FDID header on all traffic.
//   This code is defence-in-depth only — not the authoritative enforcement point.
//
// Never log raw Authorization headers or token signatures.

'use strict';

const express = require('express');
const { createRemoteJWKSet, jwtVerify } = require('jose');

const app = express();
const PORT = process.env.PORT || 8080;

// ─── Configuration (from App Settings — no secrets here) ──────────────────────
const TENANT_ID     = process.env.ENTRA_TENANT_ID   || '';
const API_APP_ID    = process.env.ENTRA_API_APP_ID   || '';
// Entra v2 client_credentials tokens carry the bare appId as `aud` (not the api:// URI).
// Delegated tokens may carry either format. Accept both; jose `audience` checks exact match,
// so we try the bare appId first (matches client_credentials) then fall back to api:// URI.
// The `EXPECTED_AUD_OVERRIDE` env var allows explicit override for future format changes.
const EXPECTED_AUD  = process.env.EXPECTED_AUD_OVERRIDE ||
                      (API_APP_ID ? API_APP_ID : '');
const EXPECTED_ISS  = TENANT_ID  ? `https://login.microsoftonline.com/${TENANT_ID}/v2.0` : '';
const JWKS_URL      = TENANT_ID  ? `https://login.microsoftonline.com/${TENANT_ID}/discovery/v2.0/keys` : '';
const ADMIN_ROLE    = 'Lab.Admin';
const AFD_ID        = process.env.AFD_FRONT_DOOR_ID  || '';  // non-secret FDID for defence-in-depth logging

// JWKS remote key set — auto-refreshes on key rollover (jose handles caching)
let JWKS = null;
if (JWKS_URL) {
  JWKS = createRemoteJWKSet(new URL(JWKS_URL));
}

// ─── Utility: sanitise error for response (never expose internals) ─────────────
function safeErrorBody(code, message) {
  return { error: { code, message } };
}

// ─── Middleware: validate JWT (for /protected and /admin) ─────────────────────
async function requireJwt(req, res, next) {
  if (!JWKS || !EXPECTED_AUD || !EXPECTED_ISS) {
    // Configuration not yet available (pre-A1 state)
    return res.status(503).json(safeErrorBody('NOT_CONFIGURED',
      'JWT validation not configured — Entra app IDs missing'));
  }

  const authHeader = req.headers['authorization'] || '';
  if (!authHeader.startsWith('Bearer ')) {
    return res.status(401).json(safeErrorBody('MISSING_TOKEN', 'Authorization Bearer token required'));
  }
  const token = authHeader.slice(7);

  try {
    const { payload } = await jwtVerify(token, JWKS, {
      issuer:   EXPECTED_ISS,
      audience: EXPECTED_AUD,
      algorithms: ['RS256', 'ES256'],
    });
    // Attach decoded payload to request for downstream handlers
    req.jwtPayload = payload;
    next();
  } catch (err) {
    // Log failure reason without logging the token itself
    const reason = err.code || err.message || 'JWT_VERIFY_FAILED';
    console.log('[AUTH] JWT validation failed reason=' + reason +
      ' path=' + req.path + ' ip=' + (req.headers['x-forwarded-for'] || req.ip));
    return res.status(401).json(safeErrorBody('INVALID_TOKEN', reason));
  }
}

// ─── Middleware: require Lab.Admin role ───────────────────────────────────────
function requireAdminRole(req, res, next) {
  const roles = (req.jwtPayload && req.jwtPayload.roles) || [];
  if (!roles.includes(ADMIN_ROLE)) {
    console.log('[AUTH] Insufficient role path=/admin sub=' +
      (req.jwtPayload && req.jwtPayload.sub ? req.jwtPayload.sub.slice(0, 8) + '...' : 'unknown'));
    return res.status(403).json(safeErrorBody('INSUFFICIENT_ROLE',
      `Role '${ADMIN_ROLE}' required`));
  }
  next();
}

// ─── Defence-in-depth: log if request did not come through AFD ────────────────
function logAfdOrigin(req) {
  const fdid = req.headers['x-azure-fdid'] || '';
  const via = req.headers['x-forwarded-for'] || req.ip;
  if (AFD_ID && fdid !== AFD_ID) {
    // Log warning for S8 bypass detection — not a block (ARM rules enforce that)
    console.log('[WARN] Request missing expected X-Azure-FDID path=' + req.path +
      ' fdid_present=' + (fdid ? 'yes' : 'no') + ' ip=' + via);
  }
}

// ─── Routes ───────────────────────────────────────────────────────────────────

// GET /health — AFD health probe target; no auth; always 200
app.get('/health', (req, res) => {
  res.json({ status: 'healthy', app: 'afd-edge-jwt-lab', ts: new Date().toISOString() });
});

// GET /public — No auth; baseline scenario
app.get('/public', (req, res) => {
  logAfdOrigin(req);
  res.json({ route: 'public', message: 'No authentication required', ts: new Date().toISOString() });
});

// GET /edge-only — Teaching-only route
// ⚠️ TEACHING NOTE: This route intentionally has NO origin-side JWT validation.
//   The Edge Action is the ONLY enforcement. When the Edge Action fails open (S9),
//   this endpoint is unprotected. This demonstrates why origin re-validation is mandatory.
//   NEVER use this pattern in production.
app.get('/edge-only', (req, res) => {
  logAfdOrigin(req);
  const edgeStatus = req.headers['x-edge-jwt-status'] || 'NOT_SET';
  const claimsHeader = req.headers['x-validated-claims'] || null;
  // Log only edge-injected metadata, never raw tokens
  console.log('[EDGE-ONLY] x-edge-jwt-status=' + edgeStatus + ' path=/edge-only');
  res.json({
    route: 'edge-only',
    // ⚠️ TEACHING: This trusts only the Edge Action header — no independent validation
    teaching_warning: 'EDGE-ONLY: Origin trusts forwarded Edge Action header. No independent JWT validation.',
    edge_jwt_status: edgeStatus,
    validated_claims: claimsHeader ? JSON.parse(claimsHeader) : null,
    ts: new Date().toISOString(),
  });
});

// GET /protected — Defence-in-depth: Edge Action + origin both validate independently
app.get('/protected', requireJwt, (req, res) => {
  logAfdOrigin(req);
  const edgeStatus = req.headers['x-edge-jwt-status'] || 'NOT_SET';
  const sub = req.jwtPayload.sub ? req.jwtPayload.sub.slice(0, 8) + '...' : 'unknown';
  console.log('[PROTECTED] sub=' + sub + ' edge_status=' + edgeStatus);
  res.json({
    route: 'protected',
    sub: req.jwtPayload.sub,
    roles: req.jwtPayload.roles || [],
    edge_jwt_status: edgeStatus,
    ts: new Date().toISOString(),
  });
});

// GET /admin — Defence-in-depth + Lab.Admin role required
app.get('/admin', requireJwt, requireAdminRole, (req, res) => {
  logAfdOrigin(req);
  const edgeStatus = req.headers['x-edge-jwt-status'] || 'NOT_SET';
  console.log('[ADMIN] sub=' + (req.jwtPayload.sub || 'unknown').slice(0, 8) +
    '... edge_status=' + edgeStatus);
  res.json({
    route: 'admin',
    sub: req.jwtPayload.sub,
    roles: req.jwtPayload.roles || [],
    edge_jwt_status: edgeStatus,
    ts: new Date().toISOString(),
  });
});

// GET /debug/request — Echo all request headers (S1 probe target)
// Intended for AFD-only access (enforced by ARM access restriction + FDID)
// Never called by unauthenticated public; no JWT required here — EA probe uses this
app.get('/debug/request', (req, res) => {
  logAfdOrigin(req);
  // Echo all headers except Authorization (never log credentials)
  const safeHeaders = {};
  for (const [k, v] of Object.entries(req.headers)) {
    if (k === 'authorization') {
      safeHeaders[k] = '<redacted length=' + v.length + '>';
    } else {
      safeHeaders[k] = v;
    }
  }
  res.json({
    route: 'debug_request',
    method: req.method,
    path: req.path,
    headers: safeHeaders,
    ts: new Date().toISOString(),
  });
});

// ─── 404 fallback ─────────────────────────────────────────────────────────────
app.use((req, res) => {
  res.status(404).json(safeErrorBody('NOT_FOUND', `No route for ${req.method} ${req.path}`));
});

// ─── Start server ─────────────────────────────────────────────────────────────
app.listen(PORT, () => {
  console.log('[START] afd-edge-jwt-lab origin listening port=' + PORT);
  console.log('[CONFIG] TENANT_ID=' + (TENANT_ID ? '***' + TENANT_ID.slice(-4) : 'NOT_SET'));
  console.log('[CONFIG] API_APP_ID=' + (API_APP_ID ? '***' + API_APP_ID.slice(-4) : 'NOT_SET'));
  console.log('[CONFIG] JWKS_URL=' + (JWKS_URL || 'NOT_SET'));
});
