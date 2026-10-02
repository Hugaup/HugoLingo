from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://localhost/language_learning"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "mistral"
    # Set true when served over HTTPS so the session cookie is never sent in clear
    cookie_secure: bool = False

    class Config:
        env_file = ".env"


settings = Settings()
