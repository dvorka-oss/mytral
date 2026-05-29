# MyTraL: my trailing log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Tests for asynchronous task system."""

import datetime
import pathlib
import time
import uuid

import pytest

from mytral import tasks
from mytral.tasks import executors


class MockDataset:
    """Mock dataset for testing task storage."""

    def __init__(self, base_dir: pathlib.Path):
        self.base_dir = base_dir
        self.tasks_dir = base_dir / "tasks"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

    def user_task_json_path(self, user_id: str, task_id: str) -> pathlib.Path:
        return self.tasks_dir / f"task-{task_id}.json"

    def user_task_log_path(self, user_id: str, task_id: str) -> pathlib.Path:
        return self.tasks_dir / f"task-{task_id}.log"

    def save_task(self, user_id: str, task_dict: dict) -> None:
        import json

        task_id = task_dict["key"]
        json_path = self.user_task_json_path(user_id, task_id)
        with open(json_path, "w") as f:
            json.dump(task_dict, f, indent=2)

    def append_task_logs(
        self, user_id: str, task_id: str, log_entries: list[str]
    ) -> None:
        log_path = self.user_task_log_path(user_id, task_id)
        with open(log_path, "a") as f:
            for entry in log_entries:
                f.write(entry + "\n")

    def load_task(self, user_id: str, task_id: str) -> dict:
        import json

        json_path = self.user_task_json_path(user_id, task_id)
        with open(json_path, "r") as f:
            return json.load(f)

    def load_task_logs(self, user_id: str, task_id: str, tail: int = 100) -> list[str]:
        log_path = self.user_task_log_path(user_id, task_id)
        if not log_path.exists():
            return []
        with open(log_path, "r") as f:
            lines = f.readlines()
        return [line.strip() for line in lines[-tail:]]

    def list_task_files(self, user_id: str) -> list[pathlib.Path]:
        if not self.tasks_dir.exists():
            return []
        return list(self.tasks_dir.glob("task-*.json"))

    def delete_task_files(self, user_id: str, task_id: str) -> None:
        json_path = self.user_task_json_path(user_id, task_id)
        log_path = self.user_task_log_path(user_id, task_id)
        if json_path.exists():
            json_path.unlink()
        if log_path.exists():
            log_path.unlink()

    def list_profiles(self) -> list[str]:
        return ["test_user"]


@pytest.mark.mytral
class TestTaskEntities:
    """Test task entities and status."""

    def test_task_status_enum(self):
        # GIVEN
        # WHEN
        # THEN
        assert tasks.TaskStatus.QUEUED.value == "queued"
        assert tasks.TaskStatus.RUNNING.value == "running"
        assert tasks.TaskStatus.COMPLETED.value == "completed"
        assert tasks.TaskStatus.FAILED.value == "failed"

    def test_task_entity_creation(self):
        # GIVEN
        task_id = str(uuid.uuid4())
        created_at = datetime.datetime.now()

        # WHEN
        task = tasks.TaskEntity(
            key=task_id,
            user_id="test_user",
            task_type="hello_world",
            status=tasks.TaskStatus.QUEUED,
            created_at=created_at,
            started_at=None,
            completed_at=None,
            error_message=None,
            error_type=None,
            error_traceback=None,
            progress=0,
            parameters={},
            is_cancelled=False,
        )

        # THEN
        assert task.key == task_id
        assert task.user_id == "test_user"
        assert task.status == tasks.TaskStatus.QUEUED
        assert task.progress == 0
        assert task.is_cancelled is False
        print(f"✓ Task entity created: {task.key}")

    def test_task_entity_serialization(self):
        # GIVEN
        task = tasks.TaskEntity(
            key=str(uuid.uuid4()),
            user_id="test_user",
            task_type="hello_world",
            status=tasks.TaskStatus.RUNNING,
            created_at=datetime.datetime.now(),
            started_at=datetime.datetime.now(),
            completed_at=None,
            error_message=None,
            error_type=None,
            error_traceback=None,
            progress=50,
            parameters={"test": "value"},
            is_cancelled=False,
        )

        # WHEN
        task_dict = task.to_dict()
        restored_task = tasks.TaskEntity.from_dict(task_dict)

        # THEN
        assert restored_task.key == task.key
        assert restored_task.status == task.status
        assert restored_task.progress == task.progress
        assert restored_task.parameters == task.parameters
        print(f"✓ Task serialization works: {task.key}")


@pytest.mark.mytral
class TestUserTaskLock:
    """Test per-user task mutex."""

    def test_acquire_and_release(self):
        # GIVEN
        lock = tasks.UserTaskLock()

        # WHEN
        acquired = lock.acquire("user_123")

        # THEN
        assert acquired is True
        assert lock.is_locked("user_123") is True
        print("DONE Lock acquired for user_123")

        # WHEN
        lock.release("user_123")

        # THEN
        assert lock.is_locked("user_123") is False
        print("DONE Lock released for user_123")

    def test_concurrent_tasks_blocked(self):
        # GIVEN
        lock = tasks.UserTaskLock()

        # WHEN - first task acquires lock
        acquired1 = lock.acquire("user_123")
        # second task for same user is rejected
        acquired2 = lock.acquire("user_123")

        # THEN
        assert acquired1 is True
        assert acquired2 is False  # at-most-one-task enforced
        print("DONE Second task correctly blocked for same user")

        # WHEN - release and retry
        lock.release("user_123")
        acquired2_retry = lock.acquire("user_123")

        # THEN
        assert acquired2_retry is True
        print("DONE Lock acquired after release")
        lock.release("user_123")

    def test_different_users_independent(self):
        # GIVEN
        lock = tasks.UserTaskLock()

        # WHEN - two different users acquire locks simultaneously
        acquired_123 = lock.acquire("user_123")
        acquired_456 = lock.acquire("user_456")

        # THEN - both succeed (users are independent)
        assert acquired_123 is True
        assert acquired_456 is True
        assert lock.is_locked("user_123") is True
        assert lock.is_locked("user_456") is True
        print("DONE Different users can run tasks concurrently")

        lock.release("user_123")
        lock.release("user_456")


@pytest.mark.mytral
class TestTaskStorage:
    """Test task storage."""

    def _make_storage(self, tmp_path: pathlib.Path):
        dataset = MockDataset(tmp_path)
        return dataset, tasks.TaskStorage(dataset=dataset)

    def test_save_and_load_task(self, tmp_path: pathlib.Path):
        # GIVEN
        mock_dataset, storage = self._make_storage(tmp_path)
        task = tasks.TaskEntity(
            key=str(uuid.uuid4()),
            user_id="test_user",
            task_type="hello_world",
            status=tasks.TaskStatus.COMPLETED,
            created_at=datetime.datetime.now(),
            started_at=datetime.datetime.now(),
            completed_at=datetime.datetime.now(),
            error_message=None,
            error_type=None,
            error_traceback=None,
            progress=100,
            parameters={},
            is_cancelled=False,
        )

        # WHEN
        storage.save(task)
        loaded_task = storage.load(task.key, task.user_id)

        # THEN
        assert loaded_task.key == task.key
        assert loaded_task.status == task.status
        assert loaded_task.progress == task.progress
        print(f"✓ Task saved and loaded: {task.key}")

    def test_append_and_load_logs(self, tmp_path: pathlib.Path):
        # GIVEN
        mock_dataset, storage = self._make_storage(tmp_path)
        task_id = str(uuid.uuid4())
        user_id = "test_user"
        logs = [
            "2024-12-27T10:00:00 - Task started",
            "2024-12-27T10:00:05 - Progress: 50%",
            "2024-12-27T10:00:10 - Task completed",
        ]

        # WHEN
        storage.append_logs(user_id, task_id, logs)
        loaded_logs = storage.load_logs(task_id, user_id, tail=100)

        # THEN
        assert len(loaded_logs) == 3
        assert loaded_logs[0] == logs[0]
        assert loaded_logs[2] == logs[2]
        print(f"✓ Logs appended and loaded: {len(loaded_logs)} entries")

    def test_log_tail_limit(self, tmp_path: pathlib.Path):
        # GIVEN
        mock_dataset, storage = self._make_storage(tmp_path)
        task_id = str(uuid.uuid4())
        user_id = "test_user"
        logs = [f"2024-12-27T10:00:{i:02d} - Log entry {i}" for i in range(20)]

        # WHEN
        storage.append_logs(user_id, task_id, logs)
        loaded_logs = storage.load_logs(task_id, user_id, tail=5)

        # THEN
        assert len(loaded_logs) == 5
        assert "Log entry 15" in loaded_logs[0]
        assert "Log entry 19" in loaded_logs[4]
        print(f"✓ Log tail limit works: requested 5, got {len(loaded_logs)}")

    def test_list_tasks(self, tmp_path: pathlib.Path):
        # GIVEN
        mock_dataset, storage = self._make_storage(tmp_path)
        task1 = tasks.TaskEntity(
            key=str(uuid.uuid4()),
            user_id="test_user",
            task_type="hello_world",
            status=tasks.TaskStatus.COMPLETED,
            created_at=datetime.datetime.now(),
            started_at=None,
            completed_at=None,
            error_message=None,
            error_type=None,
            error_traceback=None,
            progress=100,
            parameters={},
            is_cancelled=False,
        )
        task2 = tasks.TaskEntity(
            key=str(uuid.uuid4()),
            user_id="test_user",
            task_type="hello_world",
            status=tasks.TaskStatus.RUNNING,
            created_at=datetime.datetime.now(),
            started_at=None,
            completed_at=None,
            error_message=None,
            error_type=None,
            error_traceback=None,
            progress=50,
            parameters={},
            is_cancelled=False,
        )

        # WHEN
        storage.save(task1)
        storage.save(task2)
        all_tasks = storage.list_tasks("test_user")
        running_tasks = storage.list_tasks("test_user", tasks.TaskStatus.RUNNING)

        # THEN
        assert len(all_tasks) == 2
        assert len(running_tasks) == 1
        assert running_tasks[0].key == task2.key
        print(f"✓ Listed tasks: {len(all_tasks)} total, {len(running_tasks)} running")

    def test_delete_task(self, tmp_path: pathlib.Path):
        # GIVEN
        mock_dataset, storage = self._make_storage(tmp_path)
        task = tasks.TaskEntity(
            key=str(uuid.uuid4()),
            user_id="test_user",
            task_type="hello_world",
            status=tasks.TaskStatus.COMPLETED,
            created_at=datetime.datetime.now(),
            started_at=datetime.datetime.now(),
            completed_at=datetime.datetime.now(),
            error_message=None,
            error_type=None,
            error_traceback=None,
            progress=100,
            parameters={},
            is_cancelled=False,
        )
        storage.save(task)
        storage.append_logs(task.user_id, task.key, ["Log entry"])

        # verify they exist
        assert mock_dataset.user_task_json_path(task.user_id, task.key).exists()
        assert mock_dataset.user_task_log_path(task.user_id, task.key).exists()

        # WHEN
        storage.delete_task(task.user_id, task.key)

        # THEN
        assert not mock_dataset.user_task_json_path(task.user_id, task.key).exists()
        assert not mock_dataset.user_task_log_path(task.user_id, task.key).exists()
        print(f"✓ Task deleted: {task.key}")


@pytest.mark.mytral
class TestHelloWorldTask:
    """Test HelloWorld task implementation."""

    def test_hello_world_execution(self):
        # GIVEN
        from mytral import loggers

        task_entity = tasks.TaskEntity(
            key=str(uuid.uuid4()),
            user_id="test_user",
            task_type="hello_world",
            status=tasks.TaskStatus.QUEUED,
            created_at=datetime.datetime.now(),
            started_at=None,
            completed_at=None,
            error_message=None,
            error_type=None,
            error_traceback=None,
            progress=0,
            parameters={},
            is_cancelled=False,
            result_route="home",
            result_route_kwargs={},
        )
        logger = loggers.MytralPrintLogger()

        # WHEN
        from mytral.tasks.do.hello_world import HelloWorldTask

        task = HelloWorldTask(
            task_entity=task_entity,
            logger=logger,
            log_callback=lambda user_id, task_id, message: print(message),
        )
        task.execute()

        # THEN
        assert task.task_entity.progress == 100
        logs = task.get_buffered_logs()
        assert len(logs) > 0
        print("DONE HelloWorld task executed successfully")
        print(f"DONE Generated {len(logs)} log entries")

    def test_hello_world_cancellation(self):
        # GIVEN
        from mytral import loggers

        task_entity = tasks.TaskEntity(
            key=str(uuid.uuid4()),
            user_id="test_user",
            task_type="hello_world",
            status=tasks.TaskStatus.RUNNING,
            created_at=datetime.datetime.now(),
            started_at=datetime.datetime.now(),
            completed_at=None,
            error_message=None,
            error_type=None,
            error_traceback=None,
            progress=0,
            parameters={},
            is_cancelled=True,  # set cancellation flag
        )
        logger = loggers.MytralPrintLogger()

        # WHEN
        from mytral.tasks.do.hello_world import HelloWorldTask

        task = HelloWorldTask(
            task_entity=task_entity,
            logger=logger,
            log_callback=lambda user_id, task_id, message: print(message),
        )

        # THEN
        with pytest.raises(tasks.TaskCancelledException):
            task.execute()
        print("DONE HelloWorld task cancellation works")


@pytest.mark.mytral
class TestThreadTaskExecutor:
    """Test thread-based task executor."""

    def test_submit_and_execute_task(self, tmp_path: pathlib.Path):
        # GIVEN
        print("\n[TEST] Creating executor...")
        mock_dataset = MockDataset(tmp_path)
        executor = executors.ThreadTaskExecutor(max_workers=2, dataset=mock_dataset)
        task = tasks.TaskEntity(
            key=str(uuid.uuid4()),
            user_id="test_user",
            task_type="hello_world",
            status=tasks.TaskStatus.QUEUED,
            created_at=datetime.datetime.now(),
            started_at=None,
            completed_at=None,
            error_message=None,
            error_type=None,
            error_traceback=None,
            progress=0,
            parameters={},
            is_cancelled=False,
        )

        # WHEN
        print(f"[TEST] Submitting task {task.key}...")
        task_id = executor.submit(task)
        print(f"[TEST] Task submitted: {task_id}")

        # wait for task to complete (HelloWorld takes ~20 seconds)
        max_wait = 30
        waited = 0
        print(f"[TEST] Waiting up to {max_wait} seconds for task completion...")
        while waited < max_wait:
            time.sleep(1)
            waited += 1
            status = executor.get_status(task_id, "test_user")
            print(
                f"[TEST] After {waited}s: status={status.status.value}, "
                f"progress={status.progress}%, completed_at={status.completed_at}"
            )
            if status.status in [
                tasks.TaskStatus.COMPLETED,
                tasks.TaskStatus.FAILED,
            ]:
                print(f"[TEST] Task reached terminal status: {status.status.value}")
                break

        # THEN
        print(f"[TEST] Getting final status after waiting {waited} seconds...")
        final_status = executor.get_status(task_id, "test_user")
        print(f"[TEST] Final status: {final_status.status.value}")
        print(f"[TEST] Final progress: {final_status.progress}%")
        print(f"[TEST] Final completed_at: {final_status.completed_at}")
        print(f"[TEST] Final error: {final_status.error_message}")

        assert final_status.status == tasks.TaskStatus.COMPLETED
        assert final_status.progress == 100
        print(f"✓ Task executed successfully: {task_id}")

        # check logs
        logs = executor.get_logs(task_id, "test_user")
        assert len(logs) > 0
        print(f"✓ Task logs retrieved: {len(logs)} entries")
