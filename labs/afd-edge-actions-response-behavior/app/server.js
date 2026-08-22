'use strict';

const http = require('http');

const port = process.env.PORT || 8080;

http.createServer((request, response) => {
  response.setHeader('content-type', 'application/json');
  response.setHeader('x-origin-reached', 'true');

  if (request.url === '/health') {
    response.end(JSON.stringify({ status: 'healthy' }));
    return;
  }

  response.end(JSON.stringify({
    source: 'origin',
    method: request.method,
    path: request.url,
    edgeRequestHeader: request.headers['x-ea-request-test'] || null,
  }));
}).listen(port, () => {
  console.log(`Edge response test origin listening on ${port}`);
});
