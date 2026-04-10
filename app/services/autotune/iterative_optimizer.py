from utils.datetime_utils import now_iso, timestamp_slug
from services.persistence_service import PersistenceService
from app.models.optimizer_models import ChangeType, MutationRequest
from app.services.mutation_service import mutation_service

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

    def save_checkpoint(self, epoch: int, params: dict, profit_pct: float, strategy_name: str = "unknown") -> dict:
        """Persist a good epoch result as a checkpoint with version control."""
        checkpoint_id = f"epoch_{epoch:04d}_{timestamp_slug()}"
        data = {
            "checkpoint_id": checkpoint_id,
            "epoch": epoch,
            "profit_pct": profit_pct,
            "params": params,
            "saved_at": now_iso(),
        }
        persistence.save_checkpoint(self.run_id, checkpoint_id, data)
        
        mutation_result = mutation_service.create_mutation(
            MutationRequest(
                strategy_name=strategy_name,
                change_type=ChangeType.EVOLUTION,
                summary=f"Optimizer checkpoint epoch {epoch} with profit {profit_pct:.2f}%",
                created_by="optimizer",
                parameters={"hyperopt_params": params, "profit_pct": profit_pct},
                source_ref=checkpoint_id,
            )
        )
        data["version_id"] = mutation_result.version_id
        
        return data

    def list_checkpoints(self) -> list[str]:
        return persistence.list_checkpoints(self.run_id)
