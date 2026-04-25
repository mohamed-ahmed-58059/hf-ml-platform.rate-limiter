export interface Route {
  path: string;
  upstream: string;
}

let table: Route[] = [];

export function updateRoutes(routes: Route[]): void {
  table = [...routes];
}

function isMatch(requestPath: string, routePath: string): boolean {
  if (!requestPath.startsWith(routePath)) return false;
  const next = requestPath[routePath.length];
  return next === undefined || next === '/';
}

function bestMatch(requestPath: string): Route | undefined {
  return table
    .filter(r => isMatch(requestPath, r.path))
    .sort((a, b) => b.path.length - a.path.length)[0];
}

export function findUpstream(requestPath: string): string | undefined {
  return bestMatch(requestPath)?.upstream;
}

export function matchEndpoint(requestPath: string): string {
  return bestMatch(requestPath)?.path ?? 'unknown';
}
