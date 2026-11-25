import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

function titleForPath(pathname: string): string {
  const map: Record<string, string> = {
    '/': 'Dashboard',
    '/insights': 'Insights',
    '/intel': 'Intelligence',
    '/logs': 'Database',
    '/data': 'Database',
    '/data/logs': 'Transmissions',
    '/data/spans': 'Span Store',
    '/data/entities': 'NER Entities',
    '/data/events': 'Events Table',
    '/data/dataset': 'Fine-Tuning Dataset',

    '/events': 'Events',
    '/events/monitors': 'Monitor config',
    '/events/debug': 'Pipeline debug',
    '/events/span-store': 'Span store',
    '/users': 'Users',
    '/settings': 'Settings',
    '/login': 'Sign in',
    '/register': 'Register',
  }
  return map[pathname] ?? 'ScanScribe'
}

/**
 * Syncs `document.title` with the current client route (basename is already stripped by React Router).
 */
export function DocumentTitle() {
  const { pathname } = useLocation()
  const segment = titleForPath(pathname)

  useEffect(() => {
    document.title = segment === 'ScanScribe' ? 'ScanScribe' : `${segment} · ScanScribe`
  }, [segment])

  return null
}
