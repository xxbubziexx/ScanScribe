import { useCallback, useState } from 'react'

function readFlag(key: string, fallback: boolean): boolean {
  try {
    const raw = window.localStorage.getItem(key)
    return raw === null ? fallback : raw === '1'
  } catch {
    // localStorage can be unavailable (private mode, blocked storage); use the default.
    return fallback
  }
}

/** Boolean preference persisted in localStorage. */
export function usePersistedFlag(key: string, fallback: boolean): [boolean, (value: boolean) => void] {
  const [value, setValue] = useState<boolean>(() => readFlag(key, fallback))

  const update = useCallback(
    (next: boolean) => {
      setValue(next)
      try {
        window.localStorage.setItem(key, next ? '1' : '0')
      } catch {
        // Persisting is best effort; the in-memory value still applies for this session.
      }
    },
    [key],
  )

  return [value, update]
}

export const SHOW_TOOLS_KEY = 'scanscribe_intel_show_tools'
export const SHOW_THINKING_KEY = 'scanscribe_intel_show_thinking'
