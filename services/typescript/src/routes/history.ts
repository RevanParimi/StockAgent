import { Router, Request, Response } from "express";
import { getHistory, getLatestHistory } from "../clients/pythonClient";

const router = Router();

// GET /api/history/:ticker         →  GET :8000/history/:ticker
router.get("/:ticker", async (req: Request, res: Response): Promise<void> => {
  try {
    const data = await getHistory(String(req.params.ticker).toUpperCase());
    res.json(data);
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    res.status(502).json({ detail: `Python API error: ${msg}` });
  }
});

// GET /api/history/:ticker/latest  →  GET :8000/history/:ticker/latest
router.get("/:ticker/latest", async (req: Request, res: Response): Promise<void> => {
  try {
    const data = await getLatestHistory(String(req.params.ticker).toUpperCase());
    res.json(data);
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    res.status(502).json({ detail: `Python API error: ${msg}` });
  }
});

export default router;
