from db import Base
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    Text,
    DateTime,
    Date,
    ForeignKey,
    UniqueConstraint,
)
from datetime import datetime

class User(Base):
  __tablename__ = "users"

  id = Column(Integer, primary_key=True)
  name = Column(String, nullable=True)
  email = Column(String, unique=True)
  password_hash = Column(String)
  email_verified = Column(Boolean, default=False)
  verify_token = Column(String, nullable=True)
  reset_token = Column(String, nullable=True)

class Page(Base):
    __tablename__ = "pages"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String, default="")
    result_json = Column(Text)
    source = Column(String, nullable=False, default="user")
    metadata_json = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime)
    notebook_id = Column(Integer, ForeignKey("notebooks.id"), nullable=True)
    language = Column(String, nullable=False)

class Notebook(Base):
    __tablename__ = "notebooks"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String)
    created_at = Column(DateTime)

class UserLemma(Base):
    __tablename__ = "user_lemmas"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    lemma_key = Column(String, index=True)
    __table_args__ = (
        UniqueConstraint("user_id", "lemma_key"),
    )

class Annotation(Base):
    __tablename__ = "annotations"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    page_id = Column(Integer, ForeignKey("pages.id"), index=True)

    type = Column(String)  # "link" | "memo"
    content = Column(Text)

    start_index = Column(Integer)
    end_index = Column(Integer)

    created_at = Column(DateTime)

class Mutual(Base):
    __tablename__ = "mutuals"

    id = Column(Integer, primary_key=True)
    user1_id = Column(Integer, ForeignKey("users.id"), index=True)
    user2_id = Column(Integer, ForeignKey("users.id"), index=True)

    requester_id = Column(Integer, ForeignKey("users.id"))

    status = Column(String, default="pending")
    created_at = Column(DateTime)

    __table_args__ = (
        UniqueConstraint("user1_id", "user2_id"),
    )

class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True)

    annotation_id = Column(Integer, ForeignKey("annotations.id"), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)

    parent_id = Column(Integer, ForeignKey("comments.id"), nullable=True, index=True)

    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    deleted_at = Column(DateTime, nullable=True)


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)

    user_id = Column(Integer, index=True)   # 받는 사람
    actor_id = Column(Integer)              # 행동한 사람

    type = Column(String)  # "comment" | "reply"

    comment_id = Column(Integer, ForeignKey("comments.id"))
    annotation_id = Column(Integer, ForeignKey("annotations.id"))

    is_read = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)


class ReadingPreference(Base):
    __tablename__ = "reading_preferences"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, index=True)
    enabled = Column(Boolean, default=True)
    languages_json = Column(Text, default="[]")
    categories_json = Column(Text, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class DailyReadingRecommendation(Base):
    __tablename__ = "daily_reading_recommendations"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    recommendation_date = Column(Date, index=True)
    language = Column(String, nullable=False)
    category_key = Column(String, nullable=True)
    gutenberg_id = Column(Integer, nullable=False)
    title = Column(String, nullable=False)
    author = Column(String, nullable=False)
    summary = Column(Text, nullable=False)
    excerpt = Column(Text, nullable=False)
    source_url = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "recommendation_date"),
    )
