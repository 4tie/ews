import os
from app.utils.paths import optimizer_runs_dir, resolve_safe
from app.utils.json_io import read_json, write_json
from app.utils.datetime_utils import timestamp_slug


class PersistenceService:
    def save_optimizer_run(self, run_id: str, data: dict) -> None:
        path = resolve_safe(optimizer_runs_dir(), run_id, "run_meta.json")
        write_json(path, data)

    def load_optimizer_run(self, run_id: str) -> dict:
        path = resolve_safe(optimizer_runs_dir(), run_id, "run_meta.json")
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

    def rollback(self, run_id: str, checkpoint_id: str) -> dict:
        """Load and return checkpoint data as the new active state."""
        checkpoint = self.load_checkpoint(run_id, checkpoint_id)
        # TODO: apply rollback logic — re-activate this checkpoint's params
        return {"run_id": run_id, "checkpoint_id": checkpoint_id, "data": checkpoint}
