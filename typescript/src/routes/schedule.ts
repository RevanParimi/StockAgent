import { Router, Request, Response } from "express";
import { getSchedulerStatus } from "../clients/pythonClient";

const router = Router();

// GET /api/schedule  →  GET :5000/scheduler/status
router.get("/", async (_req: Request, res: Response): Promise<void> => {
  try {
    const status = await getSchedulerStatus();
    res.json(status);
  } catch (err: unknown) {
    // C# scheduler may not be running — surface cleanly
    const msg = err instanceof Error ? err.message : String(err);
    res.status(503).json({ detail: `Scheduler unavailable: ${msg}` });
  }
});

export default router;
