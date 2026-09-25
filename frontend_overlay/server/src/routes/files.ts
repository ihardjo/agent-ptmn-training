import { Router, type Request, type Response } from 'express';

/**
 * `POST /api/files/upload` — the route the stock template's paperclip calls and does not have.
 *
 * It forwards the multipart body, untouched, to the agent backend's `/files/upload`, which
 * validates it and writes it to the artifact Volume. Nothing is parsed here on purpose: this
 * process has no opinion about what a valid upload is, and adding a multipart parser to hold
 * that opinion in a second place is how the two drift apart.
 *
 * The backend's origin comes from API_PROXY, which already points at it.
 */
export const filesRouter: Router = Router();

const AGENT_UPLOAD_URL = (() => {
  const proxy = process.env.API_PROXY;
  if (!proxy) return null;
  try {
    return new URL('/files/upload', proxy).toString();
  } catch {
    return null;
  }
})();

filesRouter.post('/upload', async (req: Request, res: Response) => {
  if (!AGENT_UPLOAD_URL) {
    res.status(503).json({
      error: 'Uploads are unavailable: this chat is not connected to an agent backend.',
    });
    return;
  }

  const chunks: Buffer[] = [];
  let total = 0;
  // 25 MB, matching the backend's per-request limit. Enforced here too so an oversized body is
  // refused before it crosses a second hop, not after.
  const LIMIT = 25 * 1024 * 1024;

  try {
    for await (const chunk of req) {
      total += (chunk as Buffer).length;
      if (total > LIMIT) {
        res.status(413).json({
          error:
            'That upload is over 25 MB. Put it in the Unity Catalog volume instead — that route has no ceiling worth worrying about.',
        });
        return;
      }
      chunks.push(chunk as Buffer);
    }

    const upstream = await fetch(AGENT_UPLOAD_URL, {
      method: 'POST',
      headers: {
        'content-type': req.headers['content-type'] ?? 'application/octet-stream',
      },
      body: Buffer.concat(chunks),
    });

    const text = await upstream.text();
    let payload: unknown;
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { error: text || 'The agent backend returned an unreadable response.' };
    }

    // FastAPI wraps a raised HTTPException's detail under `detail`. The template's client reads
    // `error` off the top level and shows it in a toast, so unwrap it rather than showing the
    // user the word "detail".
    if (
      !upstream.ok &&
      payload &&
      typeof payload === 'object' &&
      'detail' in (payload as Record<string, unknown>)
    ) {
      const detail = (payload as Record<string, unknown>).detail;
      payload =
        detail && typeof detail === 'object' && 'error' in (detail as Record<string, unknown>)
          ? detail
          : { error: String(detail) };
    }

    res.status(upstream.status).json(payload);
  } catch (error) {
    res.status(502).json({
      error: `Could not reach the agent backend to store the file: ${String(error)}`,
    });
  }
});
