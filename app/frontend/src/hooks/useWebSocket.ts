import { useEffect, useRef } from 'react'
import type { WsMessage } from '@/types/watcher'

const MAX_RECONNECT_DELAY = 30_000

/**
 * Connects to a WebSocket URL and calls `onMessage` for each parsed JSON frame.
 * Reconnects with exponential backoff on disconnect. Cleans up on unmount.
 *
 * `onMessage` is kept in a ref so it can be updated without restarting the connection.
 */
export function useWebSocket(
  url: string,
  onMessage: (msg: WsMessage) => void,
  callbacks?: {
    onOpen?: () => void
    onClose?: () => void
  },
) {
  const onMessageRef = useRef(onMessage)
  const onOpenRef = useRef(callbacks?.onOpen)
  const onCloseRef = useRef(callbacks?.onClose)

  useEffect(() => {
    onMessageRef.current = onMessage
  })
  useEffect(() => {
    onOpenRef.current = callbacks?.onOpen
    onCloseRef.current = callbacks?.onClose
  })

  useEffect(() => {
    let ws: WebSocket
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let attempts = 0
    let cancelled = false

    function connect() {
      ws = new WebSocket(url)

      ws.onopen = () => {
        attempts = 0
        onOpenRef.current?.()
      }

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data) as WsMessage
          onMessageRef.current(msg)
        } catch {
          // malformed frame — ignore
        }
      }

      ws.onclose = () => {
        if (cancelled) return
        onCloseRef.current?.()
        attempts++
        const delay = Math.min(1000 * Math.pow(2, attempts - 1), MAX_RECONNECT_DELAY)
        reconnectTimer = setTimeout(() => {
          if (!cancelled) connect()
        }, delay)
      }

      ws.onerror = () => {
        // error always followed by close; handled above
      }
    }

    connect()

    return () => {
      cancelled = true
      if (reconnectTimer) clearTimeout(reconnectTimer)
      ws?.close()
    }
  }, [url])
}
