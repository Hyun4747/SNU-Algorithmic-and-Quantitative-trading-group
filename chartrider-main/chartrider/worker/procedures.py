import pickle
import time
from pathlib import Path

import docker
from docker.models.containers import Container

from chartrider.settings import ROOT_PATH, settings
from chartrider.telegram.context import TelegramUserContext


async def create_isolated_container(user_context: TelegramUserContext) -> str:
    client = docker.from_env()
    user_context_bytes = pickle.dumps(user_context).hex()
    entrypoint_path = str(Path(__file__).parent.relative_to(ROOT_PATH) / "entrypoint.py")
    command = [
        entrypoint_path,
        user_context_bytes,
    ]
    container = client.containers.run(
        f"{settings.ecr_repository}/chartrider:latest",
        command=command,
        detach=True,
        auto_remove=False,
        network_mode="host",
        name=f"trader-{user_context.username}-{user_context.environment}-{int(time.time())}",
    )
    assert isinstance(container, Container)
    return str(container.id)


async def kill_container(container_id: str) -> bool:
    client = docker.from_env()
    try:
        container = client.containers.get(container_id)
        assert isinstance(container, Container)
        if container.status == "running":
            container.stop()
        container.remove()
        return True
    except BaseException:
        return False


async def container_exists(container_id: str) -> bool:
    client = docker.from_env()
    try:
        container = client.containers.get(container_id)
        assert isinstance(container, Container)
        if container.status == "running":
            return True
        return False
    except BaseException:
        return False
    return True
