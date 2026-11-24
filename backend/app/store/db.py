from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    create_engine,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.domain.models import Bar


class Base(DeclarativeBase):
    pass


class CandleRow(Base):
    __tablename__ = "candles"
    __table_args__ = (UniqueConstraint("venue", "symbol", "interval", "open_time"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    venue: Mapped[str] = mapped_column(String(32))
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    interval: Mapped[str] = mapped_column(String(8))
    open_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    open: Mapped[Decimal] = mapped_column(Numeric(28, 10))
    high: Mapped[Decimal] = mapped_column(Numeric(28, 10))
    low: Mapped[Decimal] = mapped_column(Numeric(28, 10))
    close: Mapped[Decimal] = mapped_column(Numeric(28, 10))
    volume: Mapped[Decimal] = mapped_column(Numeric(28, 10))
    is_closed: Mapped[bool] = mapped_column(Boolean)
    source: Mapped[str] = mapped_column(String(32))
    quality: Mapped[str] = mapped_column(String(32))


class AuditEventRow(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[str] = mapped_column(String(4000))


class TradingStore:
    def __init__(self, url: str = "sqlite+pysqlite:///:memory:") -> None:
        self.engine = create_engine(url, future=True)
        Base.metadata.create_all(self.engine)
        self._sessions = sessionmaker(self.engine, expire_on_commit=False)

    def save_bars(self, bars: list[Bar], venue: str = "binance") -> int:
        inserted = 0
        with self._sessions() as session:
            for bar in bars:
                existing = session.scalar(
                    select(CandleRow).where(
                        CandleRow.venue == venue,
                        CandleRow.symbol == bar.symbol,
                        CandleRow.interval == bar.interval,
                        CandleRow.open_time == bar.open_time,
                    )
                )
                if existing is not None:
                    continue
                session.add(
                    CandleRow(
                        venue=venue,
                        symbol=bar.symbol,
                        interval=bar.interval,
                        open_time=bar.open_time,
                        open=bar.open,
                        high=bar.high,
                        low=bar.low,
                        close=bar.close,
                        volume=bar.volume,
                        is_closed=bar.is_closed,
                        source=bar.source,
                        quality=bar.quality,
                    )
                )
                inserted += 1
            session.commit()
        return inserted

    def append_event(self, sequence: int, event_type: str, payload: str) -> None:
        with self._sessions() as session:
            session.add(AuditEventRow(sequence=sequence, event_type=event_type, payload=payload))
            session.commit()

    def events(self) -> list[AuditEventRow]:
        with self._sessions() as session:
            return list(session.scalars(select(AuditEventRow).order_by(AuditEventRow.sequence)))
