from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Jurisdiction(Base):
    __tablename__ = "jurisdictions"

    copo: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    jurisdiction_type: Mapped[str] = mapped_column(
        String(10),
        CheckConstraint("jurisdiction_type IN ('city', 'county')"),
        nullable=False,
    )
    county_name: Mapped[str | None] = mapped_column(String(255))
    population: Mapped[int | None] = mapped_column(Integer)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    ledger_records: Mapped[list[LedgerRecord]] = relationship(back_populates="jurisdiction")
    naics_records: Mapped[list[NaicsRecord]] = relationship(back_populates="jurisdiction")


class DataImport(Base):
    __tablename__ = "data_imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str | None] = mapped_column(String(255))
    report_type: Mapped[str] = mapped_column(
        String(10),
        CheckConstraint("report_type IN ('ledger', 'naics')"),
        nullable=False,
    )
    copo: Mapped[str | None] = mapped_column(String(10))
    tax_type: Mapped[str | None] = mapped_column(String(10))
    year: Mapped[int | None] = mapped_column(Integer)
    month: Mapped[int | None] = mapped_column(Integer)
    records_imported: Mapped[int | None] = mapped_column(Integer)
    imported_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class LedgerRecord(Base):
    __tablename__ = "ledger_records"
    __table_args__ = (
        UniqueConstraint("copo", "tax_type", "voucher_date", name="uq_ledger_copo_type_date"),
        Index("ix_ledger_copo_type_date", "copo", "tax_type", "voucher_date"),
        Index("ix_ledger_voucher_date", "voucher_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    copo: Mapped[str] = mapped_column(String(10), ForeignKey("jurisdictions.copo"), nullable=False)
    tax_type: Mapped[str] = mapped_column(
        String(10),
        CheckConstraint("tax_type IN ('lodging', 'sales', 'use')"),
        nullable=False,
    )
    voucher_date: Mapped[date] = mapped_column(Date, nullable=False)
    tax_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    current_month_collection: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    refunded: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    suspended_monies: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    apportioned: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    revolving_fund: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    interest_returned: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    returned: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    import_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("data_imports.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    jurisdiction: Mapped[Jurisdiction] = relationship(back_populates="ledger_records")


class NaicsCode(Base):
    __tablename__ = "naics_codes"

    code: Mapped[str] = mapped_column(String(10), primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    sector: Mapped[str] = mapped_column(String(2), nullable=False)
    sector_description: Mapped[str | None] = mapped_column(Text)


class NaicsRecord(Base):
    __tablename__ = "naics_records"
    __table_args__ = (
        UniqueConstraint("copo", "tax_type", "year", "month", "activity_code", name="uq_naics_copo_type_period_code"),
        Index("ix_naics_copo_type_period", "copo", "tax_type", "year", "month"),
        Index("ix_naics_activity_code", "activity_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    copo: Mapped[str] = mapped_column(String(10), ForeignKey("jurisdictions.copo"), nullable=False)
    tax_type: Mapped[str] = mapped_column(
        String(10),
        CheckConstraint("tax_type IN ('sales', 'use')"),
        nullable=False,
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    activity_code: Mapped[str] = mapped_column(String(10), nullable=False)
    activity_code_description: Mapped[str | None] = mapped_column(Text)
    sector: Mapped[str] = mapped_column(String(15), nullable=False)
    tax_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    sector_total: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    year_to_date: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    import_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("data_imports.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    jurisdiction: Mapped[Jurisdiction] = relationship(back_populates="naics_records")


class Anomaly(Base):
    __tablename__ = "anomalies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    copo: Mapped[str] = mapped_column(String(10), ForeignKey("jurisdictions.copo"), nullable=False)
    tax_type: Mapped[str] = mapped_column(String(10), nullable=False)
    anomaly_type: Mapped[str] = mapped_column(String(50), nullable=False)
    period: Mapped[date] = mapped_column(Date, nullable=False)
    expected_value: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    actual_value: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    deviation_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    severity: Mapped[str] = mapped_column(
        String(10),
        CheckConstraint("severity IN ('low', 'medium', 'high', 'critical')"),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(Text)
    naics_code: Mapped[str | None] = mapped_column(String(10))
    investigated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Forecast(Base):
    __tablename__ = "forecasts"
    __table_args__ = (
        UniqueConstraint("copo", "tax_type", "forecast_date", "model_type", name="uq_forecast_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    copo: Mapped[str] = mapped_column(String(10), ForeignKey("jurisdictions.copo"), nullable=False)
    tax_type: Mapped[str] = mapped_column(String(10), nullable=False)
    forecast_date: Mapped[date] = mapped_column(Date, nullable=False)
    projected_returned: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    lower_bound: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    upper_bound: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    model_type: Mapped[str] = mapped_column(String(50), default="seasonal_trend")
    generated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
