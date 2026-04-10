from utils.datetime_utils import now_iso, timestamp_slug
from services.persistence_service import PersistenceService

persistence = PersistenceService()


class IterativeOptimizer:
    """
    Orchestrates iterative freqtrade hyperopt runs with checkpoint saving.
    Each accepted result is persisted as a checkpoint.
    """

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.is_running = False

    def start(self, payload: dict) -> dict:
        """
        Initialize an optimizer run.
        TODO: Launch freqtrade hyperopt subprocess with payload params,
              stream stdout to a log file, parse epoch results line by line,
              and save accepted checkpoints via persistence_service.
        """
        self.is_running = True
        run_meta = {
            "run_id": self.run_id,
            "status": "started",
            "started_at": now_iso(),
            "payload": payload,
        }
        persistence.save_optimizer_run(self.run_id, run_meta)
        # TODO: spawn async subprocess and begin log streaming
        return run_meta

    def stop(self) -> dict:
        """Signal the subprocess to stop."""
        self.is_running = False
        # TODO: send SIGTERM to running subprocess
        return {"run_id": self.run_id, "status": "stopped"}

    def save_checkpoint(self, epoch: int, params: dict, profit_pct: float) -> dict:
        """Persist a good epoch result as a checkpoint."""
        checkpoint_id = f"epoch_{epoch:04d}_{timestamp_slug()}"
        data = {
            "checkpoint_id": checkpoint_id,
            "epoch": epoch,
            "profit_pct": profit_pct,
            "params": params,
            "saved_at": now_iso(),
        }
        persistence.save_checkpoint(self.run_id, checkpoint_id, data)
        return data

    def list_checkpoints(self) -> list[str]:
        return persistence.list_checkpoints(self.run_id)
