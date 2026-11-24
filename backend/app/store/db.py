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
from sqlalchemy.pool import StaticPool

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


class StrategyStateRow(Base):
    __tablename__ = "strategy_states"
    __table_args__ = (UniqueConstraint("username", "strategy_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), index=True)
    strategy_id: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(40))
    symbol: Mapped[str] = mapped_column(String(20))
    fast: Mapped[int] = mapped_column(Integer)
    slow: Mapped[int] = mapped_column(Integer)
    quote_amount: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    position_qty: Mapped[str] = mapped_column(String(40))
    cash: Mapped[str] = mapped_column(String(40))
    entry_price: Mapped[str] = mapped_column(String(40), default="")
    last_decision: Mapped[str] = mapped_column(String(80), default="")
    signal_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String(40))


class LiveOrderRow(Base):
    __tablename__ = "live_orders"
    __table_args__ = (UniqueConstraint("username", "client_order_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), index=True)
    strategy_id: Mapped[str] = mapped_column(String(16), default="")
    symbol: Mapped[str] = mapped_column(String(20))
    side: Mapped[str] = mapped_column(String(8), default="")
    client_order_id: Mapped[str] = mapped_column(String(64))
    order_id: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32))
    quantity: Mapped[str] = mapped_column(String(40), default="0")
    executed_quantity: Mapped[str] = mapped_column(String(40), default="0")
    average_price: Mapped[str] = mapped_column(String(40), default="0")
    reason: Mapped[str] = mapped_column(String(80), default="")


class FillLedgerRow(Base):
    __tablename__ = "fill_ledger"
    __table_args__ = (UniqueConstraint("username", "client_order_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), index=True)
    strategy_id: Mapped[str] = mapped_column(String(16), default="")
    symbol: Mapped[str] = mapped_column(String(20))
    side: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[str] = mapped_column(String(40))
    price: Mapped[str] = mapped_column(String(40))
    client_order_id: Mapped[str] = mapped_column(String(64))


class TradingStore:
    def __init__(self, url: str = "sqlite+pysqlite:///:memory:") -> None:
        sync_url = url.replace("sqlite+aiosqlite://", "sqlite+pysqlite://")
        if ":memory:" in sync_url:
            self.engine = create_engine(sync_url, future=True, poolclass=StaticPool, connect_args={"check_same_thread": False})
        else:
            self.engine = create_engine(sync_url, future=True)
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

    def save_strategy(self, username: str, payload: dict) -> None:
        with self._sessions() as session:
            row = session.scalar(
                select(StrategyStateRow).where(StrategyStateRow.username == username, StrategyStateRow.strategy_id == payload["id"])
            )
            if row is None:
                row = StrategyStateRow(username=username, strategy_id=payload["id"], created_at=payload["created_at"])
                session.add(row)
            row.name = payload["name"]
            row.symbol = payload["symbol"]
            row.fast = int(payload["fast"])
            row.slow = int(payload["slow"])
            row.quote_amount = payload["quote_amount"]
            row.status = payload["status"]
            row.position_qty = payload["position_qty"]
            row.cash = payload["cash"]
            row.entry_price = payload["entry_price"]
            row.last_decision = payload["last_decision"]
            row.signal_count = int(payload["signal_count"])
            session.commit()

    def strategies(self, username: str) -> list[StrategyStateRow]:
        with self._sessions() as session:
            return list(session.scalars(select(StrategyStateRow).where(StrategyStateRow.username == username).order_by(StrategyStateRow.id)))

    def save_order(self, username: str, payload: dict) -> None:
        with self._sessions() as session:
            row = session.scalar(
                select(LiveOrderRow).where(LiveOrderRow.username == username, LiveOrderRow.client_order_id == payload["client_order_id"])
            )
            if row is None:
                row = LiveOrderRow(username=username, client_order_id=payload["client_order_id"], symbol=payload["symbol"], status=payload["status"])
                session.add(row)
            row.strategy_id = payload.get("strategy_id", "")
            row.symbol = payload["symbol"]
            row.side = payload.get("side", "")
            row.order_id = payload.get("order_id", "")
            row.status = payload["status"]
            row.quantity = payload.get("quantity", "0")
            row.executed_quantity = payload.get("executed_quantity", "0")
            row.average_price = payload.get("average_price", "0")
            row.reason = payload.get("reason", "")
            session.commit()

    def orders(self, username: str) -> list[dict]:
        with self._sessions() as session:
            rows = session.scalars(select(LiveOrderRow).where(LiveOrderRow.username == username).order_by(LiveOrderRow.id)).all()
            return [
                {
                    "symbol": row.symbol,
                    "side": row.side,
                    "order_id": row.order_id,
                    "client_order_id": row.client_order_id,
                    "status": row.status,
                    "quantity": row.quantity,
                    "executed_quantity": row.executed_quantity,
                    "average_price": row.average_price,
                    "reason": row.reason,
                    "strategy_id": row.strategy_id,
                }
                for row in rows
            ]

    def save_fill(self, username: str, payload: dict) -> None:
        with self._sessions() as session:
            existing = session.scalar(
                select(FillLedgerRow).where(FillLedgerRow.username == username, FillLedgerRow.client_order_id == payload["client_order_id"])
            )
            if existing is not None:
                return
            session.add(
                FillLedgerRow(
                    username=username,
                    strategy_id=payload.get("strategy_id", ""),
                    symbol=payload["symbol"],
                    side=payload["side"],
                    quantity=payload["quantity"],
                    price=payload["price"],
                    client_order_id=payload["client_order_id"],
                )
            )
            session.commit()

    def fills(self, username: str) -> list[dict]:
        with self._sessions() as session:
            rows = session.scalars(select(FillLedgerRow).where(FillLedgerRow.username == username).order_by(FillLedgerRow.id)).all()
            return [
                {
                    "client_order_id": row.client_order_id,
                    "symbol": row.symbol,
                    "side": row.side,
                    "price": row.price,
                    "quantity": row.quantity,
                    "strategy_id": row.strategy_id,
                }
                for row in rows
            ]
