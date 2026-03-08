from pathlib import Path
from config.config import Config
from utils.errors import ConfigError
from platformdirs import user_config_dir
from typing import Any
from tomllib import TOMLDecodeError, load
import logging

logger = logging.getLogger(__name__)

# ~/.config/ai-agent/config.toml (global)
# /home/pawxnsingh/coding/Projects/volmorelabs/ai-coding-cl (local per project and that will override the globall config toml files)

CONFIG_FILE_NAME = "config.toml"
AGENT_MD_FILE_NAME = "AGENT.md"


def get_config_path() -> Path:
    return Path(user_config_dir("ai-agent"))


def get_system_config_path() -> Path:
    return get_config_path() / CONFIG_FILE_NAME


def _parse_toml(config_path: Path) -> dict[str, Any]:
    try:
        with open(config_path, "rb") as f:
            return load(f)

    except TOMLDecodeError as e:
        raise ConfigError(
            f"Invalid Toml in {config_path}: {e}",
            config_file=str(config_path),
        ) from e

    except (OSError, IOError) as e:
        raise ConfigError(
            f"Failed to read the config file in {config_path}: {str(e)}",
            config_file=str(config_path),
        ) from e


def _get_project_config(cwd: Path) -> Path | None:
    current = cwd.resolve()
    agent_dir = current / ".ai-agent"

    if agent_dir.is_dir():
        config_file = agent_dir / CONFIG_FILE_NAME
        if config_file.is_file():
            return config_file

    return None


def _get_agent_md_files(cwd: Path) -> Path | None:
    current = cwd.resolve()

    if current.is_dir():
        agent_md_path = current / AGENT_MD_FILE_NAME
        if agent_md_path.is_file():
            content = agent_md_path.read_text("utf-8")
            return content

    return None


def _merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge_dicts(result[key], value)
        else:
            result[key] = value

    return result


def load_config(cwd: Path | None) -> Config:
    # this is the current working dir
    cwd = cwd or Path.cwd()
    # now we need to load the system configurations
    system_path = get_system_config_path()

    config_dict: dict[str, Any] = {}
    if system_path.is_file():
        try:
            config_dict = _parse_toml(config_path=system_path)
        except ConfigError:
            logger.warning(
                f"skipping invalid system config: {system_path}",
            )

    project_path = _get_project_config(cwd)
    if project_path:
        try:
            project_config_dict = _parse_toml(project_path)
            config_dict = _merge_dicts(config_dict, project_config_dict)
        except ConfigError:
            logger.warning(
                f"skipping invalid system config: {system_path}",
            )

    if "cwd" not in config_dict:
        config_dict["cwd"] = cwd

    if "developer_instructions" not in config_dict:
        agent_md_content = _get_agent_md_files(cwd=cwd)
        config_dict["developer_instructions"] = agent_md_content

    try:
        config = Config(**config_dict)
    except Exception as e:
        raise ConfigError(f"Invalid Configuration: {str(e)}") from e

    return config
