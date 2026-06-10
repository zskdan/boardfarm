import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { getServerUrl } from '../api/client';

export function useStatusSocket() {
  const qc = useQueryClient();
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    function connect() {
      const serverUrl = getServerUrl();
      const wsUrl = serverUrl.replace(/^http/, 'ws') + '/ws/status';

      try {
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.type === 'booking_changed' || data.type === 'booking_expired') {
              // Invalidate device queries so UI refreshes immediately
              qc.invalidateQueries({ queryKey: ['devices'] });
              if (data.board_id) {
                qc.invalidateQueries({ queryKey: ['device', data.board_id] });
              }
            }
          } catch { /* ignore parse errors */ }
        };

        ws.onerror = () => {
          ws.close();
        };

        // Keepalive ping every 30s
        const pingInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send('ping');
          }
        }, 30_000);

        ws.onclose = () => {
          clearInterval(pingInterval);
          reconnectTimer.current = setTimeout(connect, 5000);
        };
      } catch {
        reconnectTimer.current = setTimeout(connect, 5000);
      }
    }

    connect();

    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [qc]);
}
