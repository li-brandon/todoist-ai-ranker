"""Configuration management for Todoist AI Ranker."""

import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

# Load .env file
load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Todoist Configuration
    todoist_api_token: str
    
    # OpenAI Configuration
    openai_api_key: str
    ai_model: str = "gpt-3.5-turbo"
    ai_temperature: float = 0.7
    
    # Rate Limiting
    todoist_rate_limit: int = 1000  # requests per 15 minutes
    todoist_rate_period: int = 900  # 15 minutes in seconds
    
    # API Timeouts
    api_timeout: int = 30  # seconds
    
    # Retry Configuration
    max_retries: int = 3
    retry_min_wait: int = 2  # seconds
    retry_max_wait: int = 10  # seconds
    
    # Today View Organization
    today_view_limit: int = 15  # Maximum number of tasks in organized Today view
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    def validate_settings(self) -> None:
        """Validate that required settings are present."""
        if not self.todoist_api_token or self.todoist_api_token == "your_todoist_token_here":
            raise ValueError(
                "TODOIST_API_TOKEN is not set. "
                "Get your token from https://todoist.com/app/settings/integrations"
            )
        
        if not self.openai_api_key or self.openai_api_key == "your_openai_key_here":
            raise ValueError(
                "OPENAI_API_KEY is not set. "
                "Get your key from https://platform.openai.com/api-keys"
            )
    
    @property
    def log_level(self) -> str:
        """Get log level from environment or default to INFO."""
        return os.getenv("LOG_LEVEL", "INFO").upper()


def get_settings() -> Settings:
    """Get validated application settings."""
    settings = Settings()
    settings.validate_settings()
    return settings
