"""
Loads a portfolio's definition (portfolios/<name>/portfolio.json) and
status (portfolios/<name>/status.json), and resolves the correct
environment variable names for that portfolio's Bitget credentials.

Grok keeps its ORIGINAL, unprefixed secret names (BITGET_API_KEY,
BITGET_SECRET_KEY, BITGET_PASSPHRASE) since those are already set up and
working -- its portfolio.json has "env_prefix": "". Every other portfolio
gets its own prefixed set (e.g. BITGET_API_KEY_CLAUDE) so each portfolio's
Bitget sub-account credentials stay completely separate.

XAI_API_KEY and the Telegram credentials are shared across all portfolios
(same xAI account, one Telegram chat receiving alerts from all of them,
each message labelled with the portfolio's display name).
"""

import os
import json
from pathlib import Path

PORTFOLIOS_ROOT = Path(__file__).parent.parent / "portfolios"


class PortfolioConfig:
    def __init__(self, name: str):
        self.name = name
        self.dir = PORTFOLIOS_ROOT / name
        if not self.dir.exists():
            raise ValueError(
                f"No such portfolio '{name}'. Expected a directory at {self.dir}"
            )

        definition = json.loads((self.dir / "portfolio.json").read_text())
        self.display_name = definition["display_name"]
        self.x_handle = definition.get("x_handle")  # None => manual-only portfolio
        self.env_prefix = definition.get("env_prefix", "")

        status = json.loads((self.dir / "status.json").read_text())
        self.dry_run = bool(status.get("dry_run", True))
        self.paper_trading = bool(status.get("paper_trading", False))

    def _env_name(self, base: str) -> str:
        return f"{base}_{self.env_prefix}" if self.env_prefix else base

    def get_required_env(self, base: str) -> str:
        name = self._env_name(base)
        value = os.environ.get(name)
        if not value:
            raise RuntimeError(
                f"Missing required secret '{name}' for portfolio '{self.name}'. "
                f"Add it in GitHub repo Settings -> Secrets and variables -> Actions."
            )
        return value

    def has_bitget_credentials(self) -> bool:
        """
        True if all three Bitget credentials are present for this portfolio.
        Lets main.py fall back to tracking-only mode (fetch + merge, no
        trading) for portfolios that don't have a funded sub-account yet,
        e.g. DeepSeek/GPT before you've set them up.
        """
        return all(
            os.environ.get(self._env_name(base))
            for base in ("BITGET_API_KEY", "BITGET_SECRET_KEY", "BITGET_PASSPHRASE")
        )

    @property
    def ticker_map_path(self) -> Path:
        return PORTFOLIOS_ROOT.parent / "config" / "ticker_map.json"
        
    @property
    def manual_override_path(self) -> Path:
        return self.dir / "config" / "manual_override.json"

    @property
    def merged_state_path(self) -> Path:
        return self.dir / "data" / "merged_state.json"

    @property
    def snapshots_dir(self) -> Path:
        return self.dir / "data" / "snapshots"
