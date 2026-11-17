import uuid
import time
import threading
from concurrent.futures import ThreadPoolExecutor


class BackgroundTaskManager:
    """
    In-memory asynchronous background task manager for long-running operations
    (bulk certificate generation, bulk email dispatch, exports).
    Thread-safe, non-blocking, with real-time progress callbacks and status polling.
    """
    def __init__(self, max_workers=2):
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="SDA-Worker")
        self.tasks = {}
        self.lock = threading.Lock()

    def create_task(self, name="Task"):
        task_id = str(uuid.uuid4())
        task_info = {
            "id": task_id,
            "name": name,
            "status": "pending",
            "progress": 0,
            "current": 0,
            "total": 0,
            "message": "Queued in background...",
            "result": None,
            "error": None,
            "created_at": time.time(),
            "updated_at": time.time()
        }
        with self.lock:
            self.tasks[task_id] = task_info
        return task_id

    def update_task(self, task_id, status=None, progress=None, current=None, total=None, message=None, result=None, error=None):
        with self.lock:
            task = self.tasks.get(task_id)
            if not task:
                return
            if status is not None:
                task["status"] = status
            if current is not None:
                task["current"] = current
            if total is not None:
                task["total"] = total
            if current is not None and total and total > 0:
                task["progress"] = min(100, int((current / total) * 100))
            elif progress is not None:
                task["progress"] = progress
            if message is not None:
                task["message"] = message
            if result is not None:
                task["result"] = result
            if error is not None:
                task["error"] = str(error)
            task["updated_at"] = time.time()

    def get_task(self, task_id):
        with self.lock:
            task = self.tasks.get(task_id)
            return dict(task) if task else None

    def run_async(self, fn, *args, name="Task", **kwargs):
        task_id = self.create_task(name=name)

        def _worker():
            self.update_task(task_id, status="running", message="Task started...")
            try:
                def progress_cb(current, total, msg=None):
                    self.update_task(task_id, current=current, total=total, message=msg)

                res = fn(progress_callback=progress_cb, *args, **kwargs)
                self.update_task(task_id, status="completed", progress=100, message="Completed successfully.", result=res)
            except Exception as e:
                import traceback
                print(f"[BackgroundTask Error] {e}\n{traceback.format_exc()}")
                self.update_task(task_id, status="failed", message=f"Failed: {str(e)}", error=str(e))

        self.executor.submit(_worker)
        return task_id


# Global singleton task manager
task_manager = BackgroundTaskManager(max_workers=2)
