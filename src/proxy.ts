import { Application, Request, Response, NextFunction } from 'express';
import { createProxyMiddleware } from 'http-proxy-middleware';
import { findUpstream } from './route_table';

export function registerProxy(app: Application): void {
  app.use((req: Request, res: Response, next: NextFunction) => {
    if (!findUpstream(req.path)) {
      res.status(404).json({ error: 'not found' });
      return;
    }
    next();
  });

  app.use(
    createProxyMiddleware({
      target: 'http://placeholder',
      router: (req: Request) => findUpstream(req.path)!,
      changeOrigin: true,
      pathRewrite: (path) => path.replace(/^\/internal/, ''),
      proxyTimeout: 30_000,
      timeout: 30_000,
    })
  );
}
