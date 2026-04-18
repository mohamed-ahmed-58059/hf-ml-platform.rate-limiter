export interface Route {
  path: string;
  upstream: string;
}

let table: Route[] = [];

export function updateRoutes(routes: Route[]): void {
  table = [...routes];
}

export function findUpstream(requestPath: string): string | undefined {
  const match = table
    .filter(r => requestPath.startsWith(r.path))
    .sort((a, b) => b.path.length - a.path.length)[0];
  return match?.upstream;
}

export function matchEndpoint(requestPath: string): string {
  const match = table
    .filter(r => requestPath.startsWith(r.path))
    .sort((a, b) => b.path.length - a.path.length)[0];
  return match?.path ?? 'unknown';
}
