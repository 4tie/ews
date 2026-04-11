import os

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


class PersistenceService:
    def save_optimizer_run(self, run_id: str, data: dict) -> None:
        path = resolve_safe(optimizer_runs_dir(), run_id, "run_meta.json")
        write_json(path, data)

    def load_optimizer_run(self, run_id: str) -> dict:
        path = resolve_safe(optimizer_runs_dir(), run_id, "run_meta.json")
        return read_json(path, fallback={})

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

    def rollback(self, run_id: str, checkpoint_id: str) -> dict:
        """Load and return checkpoint data as the new active state."""
        checkpoint = self.load_checkpoint(run_id, checkpoint_id)
        # TODO: apply rollback logic - re-activate this checkpoint's params
        return {"run_id": run_id, "checkpoint_id": checkpoint_id, "data": checkpoint}

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
