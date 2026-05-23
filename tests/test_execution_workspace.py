import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from kortny.execution import task_workspace


def test_task_workspace_creates_isolated_directory(tmp_path: Path) -> None:
    task_id = uuid.uuid4()

    with task_workspace(task_id, base_dir=tmp_path) as workspace:
        assert workspace.task_id == task_id
        assert workspace.path.exists()
        assert workspace.path.is_dir()
        assert workspace.path.parent == tmp_path
        assert workspace.path.name.startswith(f"kortny-task-{task_id.hex}-")


def test_task_workspace_cleans_up_directory_on_exit(tmp_path: Path) -> None:
    task_id = uuid.uuid4()

    with task_workspace(task_id, base_dir=tmp_path) as workspace:
        created_path = workspace.path
        (created_path / "artifact.txt").write_text("done", encoding="utf-8")
        assert created_path.exists()

    assert not created_path.exists()


def test_task_workspace_creates_base_dir_if_missing(tmp_path: Path) -> None:
    base_dir = tmp_path / "kortny" / "workspaces"

    with task_workspace(uuid.uuid4(), base_dir=base_dir) as workspace:
        assert base_dir.exists()
        assert workspace.path.parent == base_dir


def test_concurrent_task_workspaces_do_not_collide(tmp_path: Path) -> None:
    task_ids = [uuid.uuid4() for _ in range(12)]

    with ThreadPoolExecutor(max_workers=6) as executor:
        paths = list(
            executor.map(
                lambda task_id: create_workspace_path(task_id, tmp_path),
                task_ids,
            )
        )

    assert len(paths) == len(set(paths))
    assert all(not path.exists() for path in paths)


def create_workspace_path(task_id: uuid.UUID, base_dir: Path) -> Path:
    with task_workspace(task_id, base_dir=base_dir) as workspace:
        (workspace.path / "marker.txt").write_text(task_id.hex, encoding="utf-8")
        return workspace.path
