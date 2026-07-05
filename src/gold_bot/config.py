"""Configuración central del proyecto.

Usa pydantic-settings: los valores se pueden sobreescribir con variables
de entorno o con un fichero .env en la raíz del repo. Así, cuando lleguen
las API keys (OANDA, etc.), vivirán en .env y nunca en el código.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Raíz del repo: config.py está en src/gold_bot/, subimos dos niveles.
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Rutas de datos
    data_dir: Path = PROJECT_ROOT / "data"

    # Reproducibilidad: toda aleatoriedad del proyecto usa esta seed
    random_seed: int = 42

    # Nivel de logging (DEBUG, INFO, WARNING...)
    log_level: str = "INFO"

    # Broker OANDA (Fase 7) — credenciales SOLO en .env, nunca en código
    oanda_api_key: str = ""
    oanda_account_id: str = ""
    oanda_practice: bool = True  # False = dinero real (Fase 8, ni se te ocurra aún)

    # Telegram (informe diario del runner + alertas de error)
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Paper broker interno (sin broker externo ni KYC): capital virtual
    paper_capital_eur: float = 50_000.0

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"


settings = Settings()
