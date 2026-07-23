// Scheduled cleanup for Blob storage. Nothing in this project ever deletes
// what /generate or api/blob-upload.ts write — every result (tiff/png/mockup
// /preview/meta) and every direct-to-Blob photo upload persists forever
// otherwise, which is both an unbounded cost and an abuse vector (anyone can
// fill the store by hitting the upload endpoint repeatedly). Invoked by
// Vercel Cron (see the `crons` entry in vercel.json) — deletes anything
// under `uploads/` or `results/` older than TTL_MS. See issue #14.
//
// Guarded by CRON_SECRET (Vercel's own convention: it sets `Authorization:
// Bearer $CRON_SECRET` on cron-triggered requests when that env var exists)
// so this can't be triggered on demand by anyone who guesses the path.

import type { IncomingMessage, ServerResponse } from 'http';
import { list, del } from '@vercel/blob';

const TTL_MS = 24 * 60 * 60 * 1000; // 24 hours
const PREFIXES = ['uploads/', 'results/'];

export default async function handler(req: IncomingMessage, res: ServerResponse) {
  res.setHeader('content-type', 'application/json');

  const expected = process.env.CRON_SECRET;
  if (expected && req.headers.authorization !== `Bearer ${expected}`) {
    res.statusCode = 401;
    res.end(JSON.stringify({ error: 'Unauthorized' }));
    return;
  }

  const cutoff = Date.now() - TTL_MS;
  const deleted: string[] = [];

  try {
    for (const prefix of PREFIXES) {
      let cursor: string | undefined;
      do {
        const page = await list({ prefix, cursor, limit: 1000 });
        const stale = page.blobs.filter((b) => new Date(b.uploadedAt).getTime() < cutoff);
        if (stale.length) {
          await del(stale.map((b) => b.url));
          deleted.push(...stale.map((b) => b.pathname));
        }
        cursor = page.cursor;
      } while (cursor);
    }

    res.statusCode = 200;
    res.end(JSON.stringify({ deletedCount: deleted.length }));
  } catch (error) {
    res.statusCode = 500;
    res.end(JSON.stringify({
      error: error instanceof Error ? error.message : String(error),
    }));
  }
}
