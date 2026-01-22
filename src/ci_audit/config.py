"""Configuration management for CI audit tool."""

import os
import re
from pathlib import Path
from typing import Any, Dict

import yaml
from dotenv import load_dotenv


class Config:
    """Configuration manager that loads from YAML and environment variables."""

    def __init__(self, config_path: str = "config/config.yaml"):
        """Initialize configuration.

        Args:
            config_path: Path to YAML configuration file
        """
        # Load environment variables from .env file
        load_dotenv()

        self.config_path = Path(config_path)
        self._config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file.

        Returns:
            Configuration dictionary
        """
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {self.config_path}\n"
                f"Copy config/config.yaml.example to config/config.yaml and update it."
            )

        with open(self.config_path, 'r') as f:
            config = yaml.safe_load(f)

        # Substitute environment variables
        config = self._substitute_env_vars(config)

        return config

    def _substitute_env_vars(self, obj: Any) -> Any:
        """Recursively substitute environment variables in config.

        Replaces ${VAR_NAME} with the value of environment variable VAR_NAME.

        Args:
            obj: Configuration object (dict, list, or primitive)

        Returns:
            Object with environment variables substituted
        """
        if isinstance(obj, dict):
            return {k: self._substitute_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._substitute_env_vars(item) for item in obj]
        elif isinstance(obj, str):
            # Replace ${VAR_NAME} with environment variable value
            pattern = r'\$\{([^}]+)\}'

            def replace_env_var(match):
                var_name = match.group(1)
                return os.environ.get(var_name, match.group(0))

            return re.sub(pattern, replace_env_var, obj)
        else:
            return obj

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key.

        Supports dot notation for nested keys (e.g., 'github.token').

        Args:
            key: Configuration key (dot-separated for nested)
            default: Default value if key not found

        Returns:
            Configuration value
        """
        keys = key.split('.')
        value = self._config

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default

        return value

    @property
    def github_token(self) -> str:
        """Get GitHub API token."""
        token = self.get('github.token')
        if not token or token.startswith('${'):
            raise ValueError(
                "GitHub token not configured. Set GITHUB_TOKEN environment variable "
                "or update config/config.yaml"
            )
        return token

    @property
    def github_repo_owner(self) -> str:
        """Get GitHub repository owner."""
        return self.get('github.repo_owner', 'opendatahub-io')

    @property
    def github_repo_name(self) -> str:
        """Get GitHub repository name."""
        return self.get('github.repo_name', 'opendatahub-operator')

    @property
    def gcs_bucket(self) -> str:
        """Get GCS bucket name."""
        return self.get('gcs.bucket', 'test-platform-results')

    @property
    def gcs_base_path(self) -> str:
        """Get GCS base path for test results."""
        return self.get('gcs.base_path', 'pr-logs/pull/opendatahub-io_opendatahub-operator')

    @property
    def gcs_job_name(self) -> str:
        """Get Prow job name."""
        return self.get('gcs.job_name', 'pull-ci-opendatahub-io-opendatahub-operator-main-opendatahub-operator-e2e')

    @property
    def database_url(self) -> str:
        """Get PostgreSQL database connection URL.

        Returns PostgreSQL URL built from configuration components.
        """
        # Build PostgreSQL URL from components
        user = self.get('database.user', 'ci_audit')
        password = self.get('database.password', '')
        host = self.get('database.host', 'localhost')
        port = self.get('database.port', 5432)
        dbname = self.get('database.name', 'ci_audit')
        return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"

    @property
    def worker_mode_enabled(self) -> bool:
        """Check if parallel worker mode is enabled."""
        return self.get('workers.enabled', False)

    @property
    def worker_id(self) -> str:
        """Get unique worker ID (hostname or env var)."""
        import socket
        import os
        return os.environ.get('WORKER_ID', socket.gethostname())

    @property
    def max_workers(self) -> int:
        """Get maximum number of parallel workers."""
        return self.get('collection.max_workers', 5)

    @property
    def cache_directory(self) -> Path:
        """Get cache directory path."""
        cache_dir = Path(self.get('collection.cache_directory', './data/cache'))
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    def __repr__(self):
        """String representation (hide sensitive data)."""
        return f"<Config(config_path='{self.config_path}')>"
