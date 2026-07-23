// The one Node.js Function in an otherwise pure-Python project. Its only
// job is minting a presigned Blob PUT URL so the browser can upload a photo
// directly to storage, bypassing this project's Python Function entirely —
// Vercel Functions cap request bodies at 4.5MB, which phone photos routinely
// exceed. See storage.py and issue #7 for the full architecture discussion.
//
// `issueSignedToken`/`presignUrl` are the documented, stable half of Vercel
// Blob's "Signed URLs" feature (POST /signed-token on the Blob control API,
// then a local HMAC computation) — unlike the older `handleUpload()`
// client-token protocol, which isn't published as a versioned contract.
// Both calls happen here, server-side, using the real @vercel/blob package;
// the browser never needs any Blob-specific JS at all, just a plain PUT.
//
// Uses the classic Node.js Function signature `(req, res)` — this runtime
// silently drops a returned `Response` object from the Fetch-API signature
// (confirmed via `vercel logs` after that version hung every request).

import type { IncomingMessage, ServerResponse } from 'http';
import { issueSignedToken, presignUrl } from '@vercel/blob';

const ALLOWED_CONTENT_TYPES = ['image/jpeg', 'image/png', 'image/webp'];
const MAX_UPLOAD_BYTES = 20 * 1024 * 1024; // matches umoja-voices' upload cap
const TOKEN_VALID_MS = 15 * 60 * 1000; // 15 minutes — long enough to pick and upload a photo

function extensionFor(contentType: string): string {
  switch (contentType) {
    case 'image/jpeg': return '.jpg';
    case 'image/png': return '.png';
    case 'image/webp': return '.webp';
    default: return '';
  }
}

function readJsonBody(req: IncomingMessage): Promise<any> {
  return new Promise((resolve, reject) => {
    let raw = '';
    req.on('data', (chunk) => { raw += chunk; });
    req.on('end', () => {
      try {
        resolve(raw ? JSON.parse(raw) : {});
      } catch (err) {
        reject(err);
      }
    });
    req.on('error', reject);
  });
}

export default async function handler(req: IncomingMessage, res: ServerResponse) {
  res.setHeader('content-type', 'application/json');

  if (req.method !== 'POST') {
    res.statusCode = 405;
    res.end(JSON.stringify({ error: 'Method not allowed' }));
    return;
  }

  let body: { contentType?: string };
  try {
    body = await readJsonBody(req);
  } catch {
    res.statusCode = 400;
    res.end(JSON.stringify({ error: 'Invalid JSON body' }));
    return;
  }

  const contentType = body.contentType;
  if (!contentType || !ALLOWED_CONTENT_TYPES.includes(contentType)) {
    res.statusCode = 400;
    res.end(JSON.stringify({
      error: `Unsupported content type. Allowed: ${ALLOWED_CONTENT_TYPES.join(', ')}`,
    }));
    return;
  }

  const pathname = `uploads/${crypto.randomUUID()}${extensionFor(contentType)}`;
  const validUntil = Date.now() + TOKEN_VALID_MS;

  try {
    const signedToken = await issueSignedToken({
      pathname,
      operations: ['put'],
      allowedContentTypes: ALLOWED_CONTENT_TYPES,
      maximumSizeInBytes: MAX_UPLOAD_BYTES,
      validUntil,
    });

    const { presignedUrl } = await presignUrl(signedToken, {
      operation: 'put',
      pathname,
      access: 'public',
      allowedContentTypes: ALLOWED_CONTENT_TYPES,
      maximumSizeInBytes: MAX_UPLOAD_BYTES,
      addRandomSuffix: false,
    });

    res.statusCode = 200;
    res.end(JSON.stringify({ presignedUrl, pathname }));
  } catch (error) {
    res.statusCode = 500;
    res.end(JSON.stringify({
      error: error instanceof Error ? error.message : String(error),
    }));
  }
}
