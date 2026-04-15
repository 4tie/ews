import os
import json

from app.utils.json_io import list_json_files, read_json, write_json
from app.utils.paths import (
    ai_chat_job_file,
    ai_chat_jobs_dir,
    ai_chat_thread_file,
    ai_chat_threads_dir,
    backtest_runs_dir,
    download_runs_dir,
    optimizer_runs_dir,
    resolve_safe,
)
from app.models.optimizer_models import ChangeType, MutationRequest


class PersistenceService:
    def __init__(self):
        # Lazy import to avoid circular dependency
        self._mutation_service = None

    @property
    def mutation_service(self):
        """Lazy-load mutation_service to avoid circular imports."""
        if self._mutation_service is None:
            from app.services.mutation_service import StrategyMutationService
            self._mutation_service = StrategyMutationService()
        return self._mutation_service

    def save_optimizer_run(self, run_id: str, data: dict) -> None:
        path = resolve_safe(optimizer_runs_dir(), run_id, "run_meta.json")
        write_json(path, data)

    def load_optimizer_run(self, run_id: str) -> dict:
        path = resolve_safe(optimizer_runs_dir(), run_id, "run_meta.json")
        return read_json(path, fallback={})


    def save_optimizer_nodes(self, run_id: str, data: dict) -> None:
        path = resolve_safe(optimizer_runs_dir(), run_id, "nodes.json")
        write_json(path, data)

    def load_optimizer_nodes(self, run_id: str) -> dict:
        path = resolve_safe(optimizer_runs_dir(), run_id, "nodes.json")
        return read_json(path, fallback={})

    def optimizer_events_path(self, run_id: str) -> str:
        return resolve_safe(optimizer_runs_dir(), run_id, "events.log")

    def append_optimizer_event(self, run_id: str, event: dict) -> None:
        path = self.optimizer_events_path(run_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=True) + "\n")

    def save_backtest_run(self, run_id: str, data: dict) -> None:
        path = resolve_safe(backtest_runs_dir(), run_id, "run_meta.json")
        write_json(path, data)

    def load_backtest_run(self, run_id: str) -> dict:
        path = resolve_safe(backtest_runs_dir(), run_id, "run_meta.json")
        return read_json(path, fallback={})

    def list_backtest_runs(self) -> list[dict]:
        base = backtest_runs_dir()
        if not os.path.isdir(base):
            return []

        runs = []
        for entry in os.listdir(base):
            path = resolve_safe(base, entry, "run_meta.json")
            data = read_json(path, fallback=None)
            if isinstance(data, dict) and data.get("run_id"):
                runs.append(data)

        def _sort_key(item: dict) -> str:
            return str(item.get("created_at") or item.get("updated_at") or item.get("run_id") or "")

        return sorted(runs, key=_sort_key, reverse=True)

    def save_download_run(self, download_id: str, data: dict) -> None:
        path = resolve_safe(download_runs_dir(), download_id, "run_meta.json")
        write_json(path, data)

    def load_download_run(self, download_id: str) -> dict:
        path = resolve_safe(download_runs_dir(), download_id, "run_meta.json")
        return read_json(path, fallback={})

    def save_checkpoint(self, run_id: str, checkpoint_id: str, data: dict) -> None:
        path = resolve_safe(optimizer_runs_dir(), run_id, "checkpoints", f"{checkpoint_id}.json")
        write_json(path, data)

    def list_checkpoints(self, run_id: str) -> list[str]:
        checkpoint_dir = resolve_safe(optimizer_runs_dir(), run_id, "checkpoints")
        if not os.path.isdir(checkpoint_dir):
            return []
        return sorted(
            [f[:-5] for f in os.listdir(checkpoint_dir) if f.endswith(".json")],
            reverse=True,
        )

    def load_checkpoint(self, run_id: str, checkpoint_id: str) -> dict:
        path = resolve_safe(optimizer_runs_dir(), run_id, "checkpoints", f"{checkpoint_id}.json")
        return read_json(path, fallback={})

    def rollback(self, run_id: str, checkpoint_id: str, strategy_name: str) -> dict:
        """
        Rollback to a checkpoint: load it, create ROLLBACK version, accept it, and return promoted version.
        
        Steps:
        1. Load checkpoint from disk
        2. Extract parameters and metadata
        3. Create ROLLBACK version via mutation_service (with checkpoint_id as source_ref)
        4. Accept ROLLBACK version (promote to ACTIVE)
        5. Return promoted version for UI display
        """
        # Step 1: Load checkpoint
        checkpoint = self.load_checkpoint(run_id, checkpoint_id)
        if not checkpoint:
            return {
                "status": "error",
                "message": f"Checkpoint {checkpoint_id} not found in run {run_id}",
            }

        # Step 2: Extract parameters following EVOLUTION checkpoint pattern
        # Checkpoints store: {"params": {...}, "profit_pct": float, "epoch": int, ...}
        # Versions expect: {"hyperopt_params": {...}, "profit_pct": float}
        params = checkpoint.get("params", {})
        profit_pct = checkpoint.get("profit_pct", 0.0)
        
        wrapped_parameters = {
            "hyperopt_params": params,
            "profit_pct": profit_pct,
        }

        # Step 3: Create ROLLBACK version
        mutation_request = MutationRequest(
            strategy_name=strategy_name,
            change_type=ChangeType.ROLLBACK,
            summary=f"Rollback to checkpoint {checkpoint_id} (epoch {checkpoint.get('epoch', '?')}, profit {profit_pct:.2f}%)",
            created_by="optimizer",
            parameters=wrapped_parameters,
            source_ref=checkpoint_id,
            source_kind="checkpoint",
            source_context={
                "run_id": run_id,
                "epoch": checkpoint.get("epoch"),
                "profit_pct": profit_pct,
            },
        )
        
        mutation_result = self.mutation_service.create_mutation(mutation_request)
        if mutation_result.status != "created":
            return {
                "status": "error",
                "message": f"Failed to create ROLLBACK version: {mutation_result.message}",
            }

        # Step 4: Accept the ROLLBACK version (promote to ACTIVE)
        version_id = mutation_result.version_id
        accept_result = self.mutation_service.accept_version(
            version_id,
            notes=f"Rolled back to checkpoint {checkpoint_id}"
        )
        if accept_result.status != "accepted":
            return {
                "status": "error",
                "message": f"Failed to accept ROLLBACK version: {accept_result.message}",
            }

        # Step 5: Load and return the promoted version for UI
        promoted_version = self.mutation_service.get_version_by_id(version_id)
        if not promoted_version:
            return {
                "status": "error",
                "message": f"Promoted version {version_id} not found after acceptance",
            }

        return {
            "status": "rolled_back",
            "run_id": run_id,
            "checkpoint_id": checkpoint_id,
            "version_id": version_id,
            "strategy_name": strategy_name,
            "promoted_version": promoted_version.model_dump(),
            "message": f"Successfully rolled back to checkpoint {checkpoint_id}",
        }

    def save_ai_chat_thread(self, strategy_name: str, data: dict) -> None:
        write_json(ai_chat_thread_file(strategy_name), data)

    def load_ai_chat_thread(self, strategy_name: str) -> dict:
        return read_json(ai_chat_thread_file(strategy_name), fallback={})

    def list_ai_chat_threads(self) -> list[dict]:
        base = ai_chat_threads_dir()
        if not os.path.isdir(base):
            return []

        threads = []
        for strategy_name in os.listdir(base):
            path = ai_chat_thread_file(strategy_name)
            data = read_json(path, fallback=None)
            if isinstance(data, dict) and data.get("strategy_name"):
                threads.append(data)

        def _sort_key(item: dict) -> str:
            return str(item.get("updated_at") or item.get("created_at") or item.get("strategy_name") or "")

        return sorted(threads, key=_sort_key, reverse=True)

    def save_ai_chat_job(self, job_id: str, data: dict) -> None:
        write_json(ai_chat_job_file(job_id), data)

    def load_ai_chat_job(self, job_id: str) -> dict:
        return read_json(ai_chat_job_file(job_id), fallback={})

    def list_ai_chat_jobs(self, strategy_name: str | None = None) -> list[dict]:
        base = ai_chat_jobs_dir()
        if not os.path.isdir(base):
            return []

        jobs = []
        for name in list_json_files(base):
            data = read_json(resolve_safe(base, name), fallback=None)
            if not isinstance(data, dict) or not data.get("job_id"):
                continue
            if strategy_name and data.get("strategy_name") != strategy_name:
                continue
            jobs.append(data)

        def _sort_key(item: dict) -> str:
            return str(item.get("updated_at") or item.get("created_at") or item.get("job_id") or "")

        return sorted(jobs, key=_sort_key, reverse=True)
