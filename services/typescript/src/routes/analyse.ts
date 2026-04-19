import { Router, Request, Response } from "express";
import { postAnalyse } from "../clients/pythonClient";

const router = Router();

// POST /api/analyse  →  POST :8000/analyse
router.post("/", async (req: Request, res: Response): Promise<void> => {
  const { ticker } = req.body as { ticker?: string };
  if (!ticker || typeof ticker !== "string") {
    res.status(400).json({ detail: "ticker is required" });
    return;
  }
  try {
    const report = await postAnalyse(ticker.toUpperCase());
    res.json(report);
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    res.status(502).json({ detail: `Python API error: ${msg}` });
  }
});

export default router;
