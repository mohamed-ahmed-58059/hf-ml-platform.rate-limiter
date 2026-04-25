function required(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`Missing required environment variable: ${name}`);
  return value;
}

function optional(name: string, defaultValue: string): string {
  return process.env[name] ?? defaultValue;
}

export const config = {
  port:              parseInt(optional('PORT', '3000'), 10),
  trustedProxyHops: parseInt(optional('TRUSTED_PROXY_HOPS', '1'), 10),

  redis: {
    host: optional('REDIS_HOST', 'localhost'),
    port: parseInt(optional('REDIS_PORT', '6379'), 10),
  },

  postgres: {
    host:     optional('POSTGRES_HOST',   'localhost'),
    port:     parseInt(optional('POSTGRES_PORT', '5432'), 10),
    user:     required('POSTGRES_USER'),
    password: required('POSTGRES_PASSWORD'),
    database: optional('POSTGRES_DB',     'hf_platform'),
    ssl:      optional('POSTGRES_SSL', 'true') === 'true',
  },

  aws: {
    region:      optional('AWS_REGION',       'us-east-1'),
    endpointUrl: optional('AWS_ENDPOINT_URL', ''),
    topicArn:    required('SNS_TOPIC_ARN'),
    queueUrl:    required('SQS_QUEUE_URL'),
  },
};
