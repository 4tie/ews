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


class PersistenceService:
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

    def save_checkpoint(self, optimizer_run_id: str, checkpoint_id: str, data: dict) -> None:
        """Save a checkpoint for an optimizer run."""
        path = resolve_safe(optimizer_runs_dir(), optimizer_run_id, "checkpoints", f"{checkpoint_id}.json")
        write_json(path, data)

    def load_checkpoint(self, optimizer_run_id: str, checkpoint_id: str) -> dict:
        """Load a checkpoint by ID."""
        path = resolve_safe(optimizer_runs_dir(), optimizer_run_id, "checkpoints", f"{checkpoint_id}.json")
        return read_json(path, fallback={})

    def list_checkpoints(self, optimizer_run_id: str) -> list[dict]:
        """List all checkpoints for an optimizer run, sorted by recency."""
        checkpoint_dir = resolve_safe(optimizer_runs_dir(), optimizer_run_id, "checkpoints")
        if not os.path.isdir(checkpoint_dir):
            return []
        
        checkpoints = []
        for filename in os.listdir(checkpoint_dir):
            if not filename.endswith(".json"):
                continue
            path = resolve_safe(checkpoint_dir, filename)
            data = read_json(path, fallback=None)
            if isinstance(data, dict) and data.get("checkpoint_id"):
                checkpoints.append(data)
        
        # Sort by timestamp descending (most recent first)
        def _sort_key(item: dict) -> str:
            return str(item.get("saved_at") or item.get("checkpoint_id") or "")
        
        return sorted(checkpoints, key=_sort_key, reverse=True)

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
