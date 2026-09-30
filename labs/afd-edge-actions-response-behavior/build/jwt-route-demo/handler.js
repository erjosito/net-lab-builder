// Structural reproduction of the original JWT lab routing.
// This checks only for a bearer token; it does not authenticate the token.

function handler(event) {
  var path = event.request.uri || '';
  var authorization = event.request.headers['authorization'] || '';

  if (authorization.indexOf('Bearer ') !== 0) {
    console.log('JWT_ROUTE_DEMO reject path=' + path + ' reason=MISSING_TOKEN');
    event.response.response_code = 401;
    event.response.headers['x-ea-test'] = 'jwt-protected';
    return event;
  }

  event.request.headers['x-edge-jwt-route-demo'] = 'bearer-present';
  console.log('JWT_ROUTE_DEMO accept path=' + path);
  return event;
}
