/**
 * WebSocket hub on port 3001.
 * Accepts client connections, then opens one upstream WS per ticker
 * to :8000/ws/stream?ticker=TICKER and rebroadcasts every message to
 * all subscribers for that ticker.
 */

import { IncomingMessage, Server } from "http";
import { WebSocket, WebSocketServer } from "ws";
import { PYTHON_WS_URL } from "./clients/pythonClient";

interface TickerHub {
  upstream: WebSocket;
  clients: Set<WebSocket>;
}

const hubs = new Map<string, TickerHub>();

function getOrCreateHub(ticker: string): TickerHub {
  const existing = hubs.get(ticker);
  if (existing && existing.upstream.readyState === WebSocket.OPEN) {
    return existing;
  }

  const upstreamUrl = `${PYTHON_WS_URL}?ticker=${encodeURIComponent(ticker)}`;
  const upstream = new WebSocket(upstreamUrl);
  const hub: TickerHub = { upstream, clients: new Set() };
  hubs.set(ticker, hub);

  upstream.on("message", (data) => {
    const payload = data.toString();
    for (const client of hub.clients) {
      if (client.readyState === WebSocket.OPEN) {
        client.send(payload);
      }
    }
  });

  upstream.on("close", () => {
    // Notify subscribers then clean up
    const errMsg = JSON.stringify({ event: "error", detail: "upstream disconnected" });
    for (const client of hub.clients) {
      if (client.readyState === WebSocket.OPEN) client.send(errMsg);
    }
    hubs.delete(ticker);
  });

  upstream.on("error", (err) => {
    const errMsg = JSON.stringify({ event: "error", detail: err.message });
    for (const client of hub.clients) {
      if (client.readyState === WebSocket.OPEN) client.send(errMsg);
    }
  });

  return hub;
}

export function attachWsHub(server: Server): WebSocketServer {
  const wss = new WebSocketServer({ server });

  wss.on("connection", (client: WebSocket, req: IncomingMessage) => {
    const url = new URL(req.url ?? "/", "ws://localhost");
    const ticker = (url.searchParams.get("ticker") ?? "").toUpperCase();

    if (!ticker) {
      client.send(JSON.stringify({ event: "error", detail: "ticker query param required" }));
      client.close();
      return;
    }

    const hub = getOrCreateHub(ticker);
    hub.clients.add(client);

    client.on("close", () => {
      hub.clients.delete(client);
    });

    client.on("error", () => {
      hub.clients.delete(client);
    });
  });

  return wss;
}
