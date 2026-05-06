import os


def _get_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


class Config:
    @staticmethod
    def secret_key() -> str:
        return os.getenv("SECRET_KEY", "inventory_ai_secret_2024")

    @staticmethod
    def database_url() -> str:
        return os.getenv("DATABASE_URL", "sqlite:///inventory.db")

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    @staticmethod
    def host() -> str:
        return os.getenv("HOST", "127.0.0.1")

    @staticmethod
    def port() -> int:
        return int(os.getenv("PORT", "5000"))

    @staticmethod
    def enable_forecasting() -> bool:
        return _get_bool("ENABLE_FORECASTING", True)

    @staticmethod
    def enable_copilot() -> bool:
        return _get_bool("ENABLE_COPILOT", True)

