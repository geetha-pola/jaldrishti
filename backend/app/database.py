from sqlalchemy import text
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from .config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency
def get_db():
    try:
        db = SessionLocal()
        # Just to trigger connection exception if it's dead
        db.execute(text("SELECT 1"))
    except Exception as e:
        yield None
        return
    try:
        yield db
    finally:
        db.close()
