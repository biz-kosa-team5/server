from __future__ import annotations

from sqlalchemy import BigInteger, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
  pass


class Region(Base):
  __tablename__ = "regions"

  id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
  code: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
  name: Mapped[str] = mapped_column(String, nullable=False)
  type: Mapped[str] = mapped_column(String, nullable=False)
  parent_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("regions.id"), nullable=True, index=True)
  center_lat: Mapped[float] = mapped_column(Float, nullable=False)
  center_lng: Mapped[float] = mapped_column(Float, nullable=False)
  unit_cnt_sum: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

  children: Mapped[list[Region]] = relationship("Region")
  complexes: Mapped[list[Complex]] = relationship(back_populates="region")


class Complex(Base):
  __tablename__ = "complexes"
  __table_args__ = (
    Index("idx_complexes_coordinate", "latitude", "longitude"),
  )

  id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
  region_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("regions.id"), nullable=False, index=True)
  parcel_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
  pnu: Mapped[str | None] = mapped_column(String, nullable=True)
  name: Mapped[str] = mapped_column(String, nullable=False, index=True)
  trade_name: Mapped[str | None] = mapped_column(String, nullable=True)
  address: Mapped[str | None] = mapped_column(String, nullable=True)
  latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
  longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
  dong_cnt: Mapped[int | None] = mapped_column(Integer, nullable=True)
  unit_cnt: Mapped[int | None] = mapped_column(Integer, nullable=True)
  use_date: Mapped[str | None] = mapped_column(String, nullable=True)

  region: Mapped[Region] = relationship(back_populates="complexes")
  trades: Mapped[list[Trade]] = relationship(back_populates="complex")


class Trade(Base):
  __tablename__ = "trades"
  __table_args__ = (
    Index("idx_trades_complex_date", "complex_id", "deal_date"),
  )

  id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
  complex_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("complexes.id"), nullable=False)
  deal_date: Mapped[str] = mapped_column(String, nullable=False)
  deal_amount: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
  excl_area: Mapped[float] = mapped_column(Float, nullable=False, index=True)
  floor: Mapped[int | None] = mapped_column(Integer, nullable=True)
  apt_dong: Mapped[str | None] = mapped_column(String, nullable=True)

  complex: Mapped[Complex] = relationship(back_populates="trades")
