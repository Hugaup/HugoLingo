from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://localhost/language_learning"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "mistral"
    # How long Ollama keeps the model loaded after a request (reloading costs seconds)
    ollama_keep_alive: str = "30m"
    # Default cap on reply length; callers with short answers pass a lower one
    ollama_max_tokens: int = 600
    # Load the model when the backend starts, so the first request isn't slow
    llm_warmup: bool = True
    # Keep this many ready-made practice sentences per language (services/sentence_pool.py)
    sentence_pool_enabled: bool = True
    sentence_pool_size: int = 20
    # Set true when served over HTTPS so the session cookie is never sent in clear
    cookie_secure: bool = False

    class Config:
        env_file = ".env"


settings = Settings()
