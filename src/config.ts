function optional(name: string, defaultValue: string): string {
  return process.env[name] ?? defaultValue;
}

export const config = {
  port: parseInt(optional('PORT', '3000'), 10),

  redis: {
    host: optional('REDIS_HOST', 'localhost'),
    port: parseInt(optional('REDIS_PORT', '6379'), 10),
  },

  postgres: {
    host:     optional('POSTGRES_HOST', 'localhost'),
    port:     parseInt(optional('POSTGRES_PORT', '5432'), 10),
    user:     optional('POSTGRES_USER', 'postgres'),
    password: optional('POSTGRES_PASSWORD', 'postgres'),
    database: optional('POSTGRES_DB', 'hf_platform'),
  },

  upstreamConfigPath: optional('UPSTREAM_CONFIG_PATH', './config/routes.yaml'),
};
