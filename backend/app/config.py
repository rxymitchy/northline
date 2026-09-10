from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    search_provider: str = "duckduckgo"
    tavily_api_key: str = ""
    serper_api_key: str = ""
    brave_api_key: str = ""

    max_discover: int = 36
    max_deep_research: int = 22
    max_outreach: int = 18
    cheap_filter_min_score: int = 30

    fetch_timeout_seconds: int = 20
    fetch_delay_seconds: float = 1.2
    user_agent: str = "Mozilla/5.0 (compatible; FindClientsAgent/1.0; +https://localhost; research)"

    database_url: str = "sqlite:///./data/prospects.db"
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    cors_origins: str = "http://localhost:3000"
    email_sending_enabled: bool = False
    outbound_send_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "Northline"
    smtp_use_tls: bool = True
    outbound_send_delay_seconds: float = 4.0

    admin_pin: str = "northline"
    openai_input_cost_per_1m: float = 0.15
    openai_output_cost_per_1m: float = 0.60


settings = Settings()
