import logging

import docker
from docker.errors import DockerException, NotFound

logger = logging.getLogger(__name__)


def restart_container(container_name: str) -> dict:
    try:
        client = docker.from_env()
        container = client.containers.get(container_name)
        container.restart(timeout=30)
        logger.info(f"Restarted container: {container_name}")
        return {"success": True, "output": f"Container {container_name} restarted successfully."}
    except NotFound:
        return {"success": False, "output": f"Container {container_name} not found."}
    except DockerException as e:
        logger.error(f"Failed to restart {container_name}: {e}")
        return {"success": False, "output": str(e)}


def exec_in_container(container_name: str, command: str) -> dict:
    try:
        client = docker.from_env()
        container = client.containers.get(container_name)
        result = container.exec_run(command, demux=False)
        output = result.output.decode("utf-8", errors="replace") if result.output else ""
        success = result.exit_code == 0
        logger.info(f"Exec in {container_name}: {command!r} → exit {result.exit_code}")
        return {"success": success, "output": output, "exit_code": result.exit_code}
    except NotFound:
        return {"success": False, "output": f"Container {container_name} not found."}
    except DockerException as e:
        logger.error(f"Exec failed in {container_name}: {e}")
        return {"success": False, "output": str(e)}
