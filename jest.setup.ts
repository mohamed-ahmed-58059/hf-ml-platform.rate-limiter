// Set required env vars before any module loads `config.ts`.
process.env.POSTGRES_USER     ??= 'test';
process.env.POSTGRES_PASSWORD ??= 'test';
process.env.SNS_TOPIC_ARN     ??= 'arn:aws:sns:us-east-1:000000000000:test';
process.env.SQS_QUEUE_URL     ??= 'http://localhost:4566/000000000000/test';
