import os
import time
import uuid
from sqlalchemy import Boolean, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


def ident():
    return str(uuid.uuid4())


engine = create_engine(os.getenv('DATABASE_URL', 'sqlite:///attendance.db'), pool_pre_ping=True)
Session = sessionmaker(engine, expire_on_commit=False)


class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=ident)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class LoginSession(Base):
    __tablename__ = 'admin_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    expires_at: Mapped[float] = mapped_column(Float)


class Employee(Base):
    __tablename__ = 'employees'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=ident)
    code: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    embeddings: Mapped[list] = mapped_column(JSON, default=list)


class Kiosk(Base):
    __tablename__ = 'kiosks'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=ident)
    name: Mapped[str] = mapped_column(String(160))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Attendance(Base):
    __tablename__ = 'attendance_logs'
    __table_args__ = (UniqueConstraint('kiosk_id', 'event_id'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=ident)
    event_id: Mapped[str] = mapped_column(String(36))
    kiosk_id: Mapped[str] = mapped_column(ForeignKey('kiosks.id'))
    employee_id: Mapped[str] = mapped_column(ForeignKey('employees.id'))
    captured_at: Mapped[float] = mapped_column(Float)
    received_at: Mapped[float] = mapped_column(Float, default=time.time)
    confidence: Mapped[float] = mapped_column(Float)


class Subscription(Base):
    __tablename__ = 'webhook_subscriptions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=ident)
    name: Mapped[str] = mapped_column(String(160))
    url: Mapped[str] = mapped_column(Text)
    secret: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Delivery(Base):
    __tablename__ = 'webhook_deliveries'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=ident)
    subscription_id: Mapped[str] = mapped_column(ForeignKey('webhook_subscriptions.id'))
    payload: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(20), default='pending')
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[float] = mapped_column(Float, default=time.time, index=True)
    last_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
