import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const option = process.argv.indexOf('--port');
const port = option === -1 ? 65003 : Number(process.argv[option + 1]);
if (!Number.isInteger(port) || port < 1024 || port > 65535) {
  throw new Error('Use --port with an integer between 1024 and 65535.');
}
const document = fileURLToPath(new URL('../src/Freehand.App/Prototypes/Compact/index.html', import.meta.url));
const server = createServer(async (request, response) => {
  const path = new URL(request.url, 'http://localhost').pathname;
  if (!['GET', 'HEAD'].includes(request.method) || !['/', '/index.html', '/health'].includes(path)) {
    response.writeHead(404).end();
    return;
  }
  try {
    const body = path === '/health' ? 'Freehand Compact prototype' : await readFile(document);
    response.writeHead(200, {
      'Content-Type': path === '/health' ? 'text/plain; charset=utf-8' : 'text/html; charset=utf-8',
      'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff',
      'Content-Security-Policy': "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
    });
    response.end(request.method === 'HEAD' ? undefined : body);
  } catch {
    response.writeHead(500).end('Could not read the prototype. Run from the Freehand checkout.');
  }
});
server.on('error', error => { console.error(error.message); process.exitCode = 1; });
server.listen(port, '127.0.0.1', () => console.log(`Freehand Compact prototype: http://127.0.0.1:${port}/`));
