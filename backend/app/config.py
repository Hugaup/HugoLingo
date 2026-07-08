from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://localhost/language_learning"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "mistral"

    class Config:
        env_file = ".env"


settings = Settings()
