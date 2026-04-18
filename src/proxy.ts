import { Application, Request, Response, NextFunction } from 'express';
import { createProxyMiddleware } from 'http-proxy-middleware';
import { findUpstream } from './route_table';

export function registerProxy(app: Application): void {
  app.use((req: Request, res: Response, next: NextFunction) => {
    if (!findUpstream(req.path)) {
      res.status(404).json({ error: `no route configured for ${req.path}` });
      return;
    }
    next();
  });

  app.use(
    createProxyMiddleware({
      target: 'http://placeholder',
      router: (req: Request) => findUpstream(req.path)!,
      changeOrigin: true,
    })
  );
}
