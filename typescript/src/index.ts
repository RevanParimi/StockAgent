import express from "express";
import cors from "cors";
import http from "http";

import analyseRouter from "./routes/analyse";
import historyRouter from "./routes/history";
import scheduleRouter from "./routes/schedule";
import { attachWsHub } from "./wsHub";

const REST_PORT = parseInt(process.env.REST_PORT ?? "3000", 10);
const WS_PORT   = parseInt(process.env.WS_PORT   ?? "3001", 10);

// ---------------------------------------------------------------------------
// REST server — port 3000
// ---------------------------------------------------------------------------

const app = express();

app.use(cors({
  origin: [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:8000",
    "http://localhost:5000",
  ],
}));
app.use(express.json());

app.get("/health", (_req, res) => res.json({ status: "ok" }));

app.use("/api/analyse",  analyseRouter);
app.use("/api/history",  historyRouter);
app.use("/api/schedule", scheduleRouter);

app.listen(REST_PORT, () => {
  console.log(`[REST]  listening on http://localhost:${REST_PORT}`);
});

// ---------------------------------------------------------------------------
// WebSocket hub — port 3001
// ---------------------------------------------------------------------------

const wsServer = http.createServer();
attachWsHub(wsServer);

wsServer.listen(WS_PORT, () => {
  console.log(`[WS]    listening on ws://localhost:${WS_PORT}`);
});
