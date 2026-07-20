"""Environment-only application configuration."""
from pathlib import Path
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    environment: str = "development"
    service_name: str = "devpilot-api"
    cors_origins: str = "http://localhost:3000"
    database_url: str = "postgresql+psycopg://devpilot:devpilot@postgres:5432/devpilot"
    default_tenant_id: str = "ai_platform"
    jwt_secret_key: SecretStr = SecretStr("")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = Field(30, ge=1, le=1440)
    refresh_token_days: int = Field(30, ge=1, le=90)
    github_webhook_secret: SecretStr = SecretStr("")
    github_api_url: str = "https://api.github.com"
    github_checks_token: SecretStr = SecretStr("")
    github_checks_enabled: bool = False
    github_app_id: str = ""
    github_app_slug: str = ""
    github_app_private_key: SecretStr = SecretStr("")
    github_app_private_key_path: str = ""
    outbox_poll_seconds: float = Field(2, ge=.2, le=60)
    monthly_budget_usd: float = Field(0, ge=0)
    allow_self_registration: bool = True
    allow_local_auth: bool = True
    oidc_enabled: bool = False
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: SecretStr = SecretStr("")
    oidc_redirect_uri: str = "http://localhost:3000/api/auth/oidc/callback"
    oidc_default_workspace: str = "ai_platform"
    oidc_workspace_claim: str = "tenant_id"
    oidc_role_claim: str = "role"
    scim_enabled: bool = False
    scim_bearer_token: SecretStr = SecretStr("")
    scim_default_workspace: str = "ai_platform"
    otel_exporter_otlp_endpoint: str = ""
    otel_service_name: str = "devpilot-api"
    otel_sample_ratio: float = Field(0.1, ge=0, le=1)
    log_level: str = "INFO"
    log_json: bool = False
    worker_metrics_port: int = Field(9100, ge=1024, le=65535)
    knowledge_llm_enabled: bool = False
    knowledge_llm_base_url: str = "https://api.openai.com/v1"
    knowledge_llm_api_key: SecretStr = SecretStr("")
    knowledge_llm_model: str = "gpt-4.1-mini"
    knowledge_llm_timeout_seconds: float = Field(20, ge=1, le=120)
    knowledge_input_cost_per_million: float = Field(0, ge=0)
    knowledge_output_cost_per_million: float = Field(0, ge=0)
    knowledge_max_upload_bytes: int = Field(5_242_880, ge=1024, le=20_971_520)

    @property
    def jwt_key(self) -> str:
        return self.jwt_secret_key.get_secret_value()

    @property
    def github_app_configured(self) -> bool:
        return bool(self.github_app_id and self.github_app_private_key_value)

    @property
    def github_app_private_key_value(self) -> str:
        inline_key = self.github_app_private_key.get_secret_value()
        if inline_key:
            return inline_key
        if not self.github_app_private_key_path:
            return ""
        key_path = Path(self.github_app_private_key_path)
        if not key_path.exists():
            return ""
        return key_path.read_text(encoding="utf-8")

    def production_readiness_issues(self) -> list[str]:
        issues: list[str] = []
        if len(self.jwt_key) < 32:
            issues.append("JWT_SECRET_KEY must contain at least 32 characters")
        if self.environment == "production":
            if self.allow_local_auth or self.allow_self_registration:
                issues.append("local authentication and self-registration must be disabled")
            if not self.oidc_enabled:
                issues.append("OIDC must be enabled before production startup")
            if "localhost" in self.cors_origins or "*" in self.cors_origins:
                issues.append("CORS_ORIGINS must use explicit production origins")
        if self.knowledge_llm_enabled and not self.knowledge_llm_api_key.get_secret_value():
            issues.append("KNOWLEDGE_LLM_API_KEY is required when knowledge LLM is enabled")
        return issues
