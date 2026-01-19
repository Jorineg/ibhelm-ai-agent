"""Configuration settings for AI Email Agent."""

from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str
    
    # Anthropic
    anthropic_api_key: str
    claude_model: str = "claude-sonnet-4-5-20250514"
    
    # MCP Server
    mcp_server_url: str = "https://api.ibhelm.de/mcp"
    mcp_bearer_token: str
    
    # Missive
    missive_api_token: str
    missive_organization_id: Optional[str] = None
    
    # Polling
    poll_interval_seconds: float = 1.0
    
    # Logging
    log_level: str = "INFO"
    betterstack_source_token: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()

