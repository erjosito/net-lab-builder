// Claims prefilter only. This code does not verify the JWT signature.
// The origin must perform cryptographic JWT validation.

const CONFIG = {
  audience: '%%API_APP_ID%%',
  issuer: 'https://login.microsoftonline.com/%%TENANT_ID%%/v2.0',
  adminRole: 'Lab.Admin',
};

function decodeBase64Url(value) {
  var chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  var input = value.replace(/-/g, '+').replace(/_/g, '/');
  var out = '', buf = 0, bits = 0;
  for (var i = 0; i < input.length; i++) {
    var c = chars.indexOf(input[i]);
    if (c < 0) continue;
    buf = (buf << 6) | c;
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      out += String.fromCharCode((buf >> bits) & 255);
    }
  }
  return out;
}

function parseJson(value) {
  try {
    return JSON.parse(decodeBase64Url(value));
  } catch (e) {
    return null;
  }
}

function deny(event, status, reason) {
  console.log('EA_REJECT reason=' + reason);
  event.response.response_code = status;
  return event;
}

function handler(event) {
  var headers = event.request.headers;
  delete event.request.headers['x-validated-claims'];
  delete event.request.headers['x-edge-jwt-status'];
  delete event.request.headers['x-test-fail'];

  var authorization = headers['authorization'] || '';
  if (authorization.indexOf('Bearer ') !== 0)
    return deny(event, 401, 'MISSING_TOKEN');

  var parts = authorization.slice(7).split('.');
  if (parts.length !== 3 || !parseJson(parts[0]))
    return deny(event, 401, 'MALFORMED_HEADER');

  var claims = parseJson(parts[1]);
  if (!claims) return deny(event, 401, 'MALFORMED_PAYLOAD');

  var now = Math.floor(Date.now() / 1000);
  if (!claims.exp || claims.exp < now)
    return deny(event, 401, 'EXPIRED');
  if (claims.nbf && claims.nbf > now + 60)
    return deny(event, 401, 'NOT_YET_VALID');
  if (claims.aud !== CONFIG.audience)
    return deny(event, 401, 'AUD_FAIL');
  if (claims.iss !== CONFIG.issuer)
    return deny(event, 401, 'ISS_FAIL');

  var roles = claims.roles || [];
  if ((event.request.uri || '').indexOf('/admin') === 0 &&
      roles.indexOf(CONFIG.adminRole) < 0)
    return deny(event, 403, 'ROLE_FAIL');

  headers['x-validated-claims'] = JSON.stringify({
    roles: roles,
    exp: claims.exp,
    mode: 'claims_only',
  });
  headers['x-edge-jwt-status'] = 'VALIDATED';
  console.log('EA_ACCEPT');
  return event;
}
