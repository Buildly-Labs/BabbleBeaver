import os
import uuid
from datetime import datetime
import logging
import re

from sqlalchemy import create_engine, Column, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

Base = declarative_base()


def get_database_url():
    """
    Get and normalize the database URL.
    
    Handles the postgres:// vs postgresql:// issue with DigitalOcean/Heroku
    and SQLAlchemy 1.4+.
    """
    database_url = os.getenv("DATABASE_URL")
    
    # Log what we received (safely, without exposing credentials)
    if database_url:
        # Check if it looks like an unresolved placeholder
        if database_url.startswith("${") or not re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://', database_url):
            logger.error(f"DATABASE_URL appears to be invalid or unresolved: {database_url[:50]}...")
            database_url = None
        else:
            safe_url = database_url.split('@')[-1] if '@' in database_url else database_url[:30]
            logger.info(f"DATABASE_URL configured: ...@{safe_url}")
    
    if not database_url:
        # Fallback to SQLite for local development
        logger.warning("DATABASE_URL not set or invalid for response_logger, using SQLite fallback")
        os.makedirs("db", exist_ok=True)
        return "sqlite:///db/response_logger.db"
    
    # DigitalOcean/Heroku use postgres:// but SQLAlchemy 1.4+ requires postgresql://
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
        logger.info("Converted postgres:// to postgresql:// for SQLAlchemy compatibility")
    
    return database_url


DATABASE_URL = get_database_url()

# Configure engine with appropriate settings based on database type
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(
        DATABASE_URL,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Define the ChatHistory model
class ChatHistory(Base):
    __tablename__ = "user_chats"
    session_id = Column(String, primary_key=True, index=True)
    sender = Column(String)
    message = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

# ChatLogger class for inserting and selecting chat history
class ChatLogger:

    @staticmethod
    def get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def __init__(self, table_name='user_chats'):
        self.table_name = table_name

        # Create table(s) - use checkfirst=True to avoid errors if table exists
        try:
            Base.metadata.create_all(bind=engine, checkfirst=True)
        except Exception as e:
            logger.warning(f"Table creation warning (may already exist): {e}")

    def select_all_messages(self, session_id):
        print("session_id:", session_id)
        db = SessionLocal()
        try:
            records = db.query(ChatHistory).filter(ChatHistory.session_id == session_id).all()
            print("records:", records)
            return records
        finally:
            db.close()

    def insert_message(self, session_id, sender, message):
        db = SessionLocal()
        try:
            record = ChatHistory(
                session_id=session_id,
                sender=sender,
                message=message,
                timestamp=datetime.utcnow()
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            print(f"✅ Stored chat data for {session_id} - {sender}")
        finally:
            db.close()
