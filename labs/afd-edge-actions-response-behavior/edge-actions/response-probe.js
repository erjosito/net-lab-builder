function handler(event) {
  var path = event.request.uri || '';
  var response = event.response;

  console.log('RESPONSE_PROBE path=' + path);

  if (path === '/ea/tracking-reference') {
    var candidates = [
      'TrackingReference',
      'trackingReference',
      'tracking_reference',
      'x-azure-ref',
      'x_azure_ref'
    ];
    var trackingReference = '';

    Object.keys(event.context || {}).forEach(function (key) {
      console.log('CONTEXT_KEY ' + key);
    });

    for (var i = 0; i < candidates.length; i++) {
      if (event.context && event.context[candidates[i]]) {
        trackingReference = event.context[candidates[i]];
        break;
      }
    }

    response.response_code = 401;
    response.headers['content-type'] = 'application/json';
    response.headers['x-ea-test'] = 'tracking-reference';
    response.headers['x-ea-context-tracking-reference'] =
      trackingReference || 'unavailable-at-edge-action';
    response.body = JSON.stringify({
      source: 'edge',
      contextTrackingReference: trackingReference || null
    });
    return event;
  }

  if (path === '/ea/body-401') {
    response.response_code = 401;
    response.body = 'EA_BODY_401';
    response.headers['content-type'] = 'text/plain';
    response.headers['x-ea-test'] = 'body-401';
  } else if (path === '/ea/body-403') {
    response.response_code = 403;
    response.body = '{"source":"edge","test":"body-403"}';
    response.headers['content-type'] = 'application/json';
    response.headers['x-ea-test'] = 'body-403';
  } else if (path === '/ea/body-200') {
    response.response_code = 200;
    response.body = 'EA_BODY_200';
    response.headers['content-type'] = 'text/plain';
    response.headers['x-ea-test'] = 'body-200';
  } else if (path === '/ea/header-401') {
    response.response_code = 401;
    response.headers['x-ea-test'] = 'header-401';
    response.headers['content-type'] = 'application/problem+json';
  } else if (path === '/ea/header-200') {
    response.response_code = 200;
    response.headers['x-ea-test'] = 'header-200';
    event.request.headers['x-ea-request-test'] = 'request-header-reached-origin';
  } else if (path === '/ea/cookie-401') {
    response.response_code = 401;
    response.body = 'EA_COOKIE_401';
    response.set_cookie_headers = [
      'ea_cookie=one; Path=/; Secure; HttpOnly',
      'ea_cookie_two=two; Path=/; SameSite=Lax'
    ];
  } else if (path === '/ea/location-403') {
    response.response_code = 403;
    response.headers['location'] = 'https://example.invalid/blocked';
  } else if (path === '/ea/unsupported-302') {
    response.response_code = 302;
    response.headers['location'] = 'https://example.invalid/redirect';
    response.body = 'EA_UNSUPPORTED_302';
  } else if (path === '/ea/unsupported-404') {
    response.response_code = 404;
    response.body = 'EA_UNSUPPORTED_404';
  } else if (path === '/ea/unsupported-418') {
    response.response_code = 418;
    response.body = 'EA_UNSUPPORTED_418';
  } else if (path === '/ea/unsupported-500') {
    response.response_code = 500;
    response.body = 'EA_UNSUPPORTED_500';
  } else if (path === '/ea/alias-status') {
    response.status = 418;
    response.body = 'EA_ALIAS_STATUS';
  } else if (path === '/ea/alias-status-code') {
    response.statusCode = 419;
    response.body = 'EA_ALIAS_STATUS_CODE';
  } else if (path === '/ea/alias-content') {
    response.response_code = 401;
    response.content = 'EA_ALIAS_CONTENT';
  } else if (path === '/ea/alias-data') {
    response.response_code = 401;
    response.data = 'EA_ALIAS_DATA';
  } else if (path === '/ea/alias-payload') {
    response.response_code = 401;
    response.payload = 'EA_ALIAS_PAYLOAD';
  } else if (path === '/ea/alias-header') {
    response.response_code = 401;
    response.header = { 'x-ea-singular-header': 'true' };
  } else if (path === '/ea/metadata') {
    response.response_code = 401;
    response.body = 'EA_METADATA';
    response.reason_phrase = 'Edge Action Custom Reason';
    response.body_encoding = 'utf8';
    response.bodyEncoding = 'utf8';
    response.isBase64Encoded = false;
    response.content_type = 'text/plain';
  } else if (path === '/ea/body-object') {
    response.response_code = 401;
    response.body = { source: 'edge', test: 'object' };
  } else if (path === '/ea/body-null') {
    response.response_code = 401;
    response.body = null;
  } else if (path === '/ea/body-empty') {
    response.response_code = 401;
    response.body = '';
  }

  return event;
}
