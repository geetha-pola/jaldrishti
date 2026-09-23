from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    host: str = "0.0.0.0"
    port: int = 8000
    delft3d_bin_dir: str = ""

    class Config:
        env_file = ".env"

settings = Settings()
