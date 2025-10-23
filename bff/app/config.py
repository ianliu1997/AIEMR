from functools import cached_property
from typing import List
from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
  """BFF configuration (inherits env from underlying services)."""

  app_name: str = "AIEMR Gateway"
  environment: str = Field(default="development", description="Deployment environment label")
  allowed_origins: List[str] = Field(default_factory=lambda: ["http://localhost:3000"])
  request_timeout_seconds: int = 60

  class Config:
    env_prefix = "GATEWAY_"
    env_file = ".env"
    case_sensitive = False

  @cached_property
  def cors_origins(self) -> List[AnyHttpUrl]:
    origins: List[AnyHttpUrl] = []
    for entry in self.allowed_origins:
      try:
        origins.append(AnyHttpUrl(entry))
      except Exception:
        # Skip invalid entries and fall back to wildcard in app setup
        continue
    return origins


settings = Settings()
