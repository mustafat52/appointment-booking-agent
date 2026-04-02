# db/database.py

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os
from dotenv import load_dotenv

# Load .env so this module works whether imported directly or via main.py
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "\n\n❌ DATABASE_URL is not set.\n"
        "Create a .env file in your project root with:\n"
        "  DATABASE_URL=postgresql://user:password@host:port/dbname\n"
    )

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)

Base = declarative_base()