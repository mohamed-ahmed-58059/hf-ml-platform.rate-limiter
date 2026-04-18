import { SQSClient, ReceiveMessageCommand, DeleteMessageCommand } from '@aws-sdk/client-sqs';
import { Redis } from 'ioredis';
import { clearMemoryCache } from './policy_cache';

export interface CacheInvalidatorOptions {
  queueUrl:        string;
  region:          string;
  endpointUrl?:    string;
  pollWaitSeconds?: number; // default 20; lower in tests to speed up shutdown
}

export function startCacheInvalidator(redis: Redis, options: CacheInvalidatorOptions): () => void {
  const sqs = new SQSClient({
    region:   options.region,
    ...(options.endpointUrl ? { endpoint: options.endpointUrl } : {}),
  });

  let running = true;

  console.log(`[cache-invalidator] polling ${options.queueUrl}`);
  pollForever(redis, sqs, options, () => running);

  return () => { running = false; };
}

// ── poll loop ─────────────────────────────────────────────────────────────────

async function pollForever(
  redis: Redis,
  sqs: SQSClient,
  options: CacheInvalidatorOptions,
  isRunning: () => boolean
): Promise<void> {
  const waitSeconds = options.pollWaitSeconds ?? 20;

  while (isRunning()) {
    try {
      const res = await sqs.send(
        new ReceiveMessageCommand({
          QueueUrl:            options.queueUrl,
          MaxNumberOfMessages: 10,
          WaitTimeSeconds:     waitSeconds,
        })
      );

      if (!isRunning()) break;

      for (const msg of res.Messages ?? []) {
        await handleMessage(redis, sqs, options.queueUrl, msg.Body ?? '', msg.ReceiptHandle ?? '');
      }
    } catch (err) {
      if (isRunning()) console.error('[cache-invalidator] poll error:', err);
    }
  }
}

// ── message handling ──────────────────────────────────────────────────────────

interface InvalidationMessage {
  clientType: string;
  clientId:   string;
  newVersion: number;
}

async function handleMessage(
  redis: Redis,
  sqs: SQSClient,
  queueUrl: string,
  rawBody: string,
  receiptHandle: string
): Promise<void> {
  let msg: InvalidationMessage;

  try {
    // SNS wraps the message in an envelope when delivering to SQS
    const envelope = JSON.parse(rawBody) as { Message?: string };
    const inner    = envelope.Message ?? rawBody;
    msg            = JSON.parse(inner) as InvalidationMessage;
  } catch {
    console.error('[cache-invalidator] failed to parse message, discarding:', rawBody);
    await deleteMessage(sqs, queueUrl, receiptHandle);
    return;
  }

  const { clientType, clientId, newVersion } = msg;
  await invalidateIfStale(redis, clientType, clientId, newVersion);
  await deleteMessage(sqs, queueUrl, receiptHandle);
}

// ── invalidation ──────────────────────────────────────────────────────────────

async function invalidateIfStale(
  redis: Redis,
  clientType: string,
  clientId: string,
  newVersion: number
): Promise<void> {
  const pattern = `policy:${clientType}:${clientId}:*`;
  const keys    = await scanKeys(redis, pattern);

  if (keys.length === 0) {
    console.log(`[cache-invalidator] no cached keys for ${clientType}:${clientId}`);
    return;
  }

  const cachedVersion = await redis.hget(keys[0], 'version');
  const cached        = cachedVersion !== null ? parseInt(cachedVersion, 10) : -1;

  if (cached >= newVersion) {
    console.log(
      `[cache-invalidator] ${clientType}:${clientId} already at v${cached} (event v${newVersion}), skipping`
    );
    return;
  }

  await redis.del(...keys);
  clearMemoryCache();
  console.log(
    `[cache-invalidator] evicted ${keys.length} key(s) for ${clientType}:${clientId} ` +
    `(v${cached} → v${newVersion})`
  );
}

async function scanKeys(redis: Redis, pattern: string): Promise<string[]> {
  const keys: string[] = [];
  let cursor = '0';

  do {
    const [nextCursor, batch] = await redis.scan(cursor, 'MATCH', pattern, 'COUNT', 100);
    keys.push(...batch);
    cursor = nextCursor;
  } while (cursor !== '0');

  return keys;
}

async function deleteMessage(sqs: SQSClient, queueUrl: string, receiptHandle: string): Promise<void> {
  try {
    await sqs.send(new DeleteMessageCommand({ QueueUrl: queueUrl, ReceiptHandle: receiptHandle }));
  } catch (err) {
    console.error('[cache-invalidator] failed to delete SQS message:', err);
  }
}
