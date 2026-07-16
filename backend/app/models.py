"""ORM model — mirrors the BTM entities the spec requires."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Station(Base):
    __tablename__ = "stations"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    instrument_model: Mapped[str] = mapped_column(String(64), default="")
    site: Mapped[str] = mapped_column(String(64), default="NTE")
    instrument_height_m: Mapped[float] = mapped_column(Float, default=0.0)
    e: Mapped[float | None] = mapped_column(Float, nullable=True)
    n: Mapped[float | None] = mapped_column(Float, nullable=True)
    h: Mapped[float | None] = mapped_column(Float, nullable=True)

    sensors: Mapped[list["Sensor"]] = relationship(back_populates="station", cascade="all, delete-orphan")


class Sensor(Base):
    """A BTM variable triplet (Hz/Vz/Sd) bound to one physical prism or target."""

    __tablename__ = "sensors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    station_code: Mapped[str] = mapped_column(ForeignKey("stations.code"), index=True)
    raw_name: Mapped[str] = mapped_column(String(64), index=True)
    measurement_type: Mapped[str] = mapped_column(String(24), default="prism")  # prism | reflective-sheet | reflectorless
    prism_constant_required_m: Mapped[float] = mapped_column(Float, default=0.0)
    prism_constant_applied_m: Mapped[float] = mapped_column(Float, default=0.0)
    target_height_m: Mapped[float] = mapped_column(Float, default=0.0)
    edm_mode: Mapped[str] = mapped_column(String(24), default="standard")

    station: Mapped[Station] = relationship(back_populates="sensors")


class PhysicalPoint(Base):
    __tablename__ = "physical_points"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    label: Mapped[str] = mapped_column(String(128), default="")
    known_e: Mapped[float | None] = mapped_column(Float, nullable=True)
    known_n: Mapped[float | None] = mapped_column(Float, nullable=True)
    known_h: Mapped[float | None] = mapped_column(Float, nullable=True)
    sigma_e_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    sigma_n_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    sigma_h_m: Mapped[float | None] = mapped_column(Float, nullable=True)


class RawObservation(Base):
    __tablename__ = "raw_observations"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    station_code: Mapped[str] = mapped_column(String(32), index=True)
    sensor_id: Mapped[int] = mapped_column(ForeignKey("sensors.id"), index=True)
    epoch: Mapped[str] = mapped_column(String(40), index=True)
    record_number: Mapped[int] = mapped_column(Integer, default=0)
    hz_rad: Mapped[float] = mapped_column(Float)
    vz_rad: Mapped[float] = mapped_column(Float)
    sd_m: Mapped[float] = mapped_column(Float)


class EnvironmentReading(Base):
    __tablename__ = "environment_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    station_code: Mapped[str] = mapped_column(String(32), index=True)
    epoch: Mapped[str] = mapped_column(String(40), index=True)
    temperature_c: Mapped[float] = mapped_column(Float)
    pressure_hpa: Mapped[float] = mapped_column(Float)


class Processing(Base):
    __tablename__ = "processings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(24), default="network")  # single-station | network
    template: Mapped[str] = mapped_column(String(24), default="uk")  # uk | fr | custom
    state: Mapped[str] = mapped_column(String(16), default="active")  # active | inactive
    created_at: Mapped[str] = mapped_column(String(40), default=lambda: utcnow().isoformat())

    versions: Mapped[list["ConfigVersion"]] = relationship(back_populates="processing", cascade="all, delete-orphan")
    runs: Mapped[list["Run"]] = relationship(back_populates="processing", cascade="all, delete-orphan")


class ConfigVersion(Base):
    __tablename__ = "config_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    processing_id: Mapped[int] = mapped_column(ForeignKey("processings.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft | active | inactive | archived
    valid_from: Mapped[str] = mapped_column(String(40))
    valid_to: Mapped[str | None] = mapped_column(String(40), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)
    origin: Mapped[str] = mapped_column(String(32), default="manual")  # manual | analysis-lab | seed
    created_at: Mapped[str] = mapped_column(String(40), default=lambda: utcnow().isoformat())

    processing: Mapped[Processing] = relationship(back_populates="versions")


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    processing_id: Mapped[int] = mapped_column(ForeignKey("processings.id"), index=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("config_versions.id"))
    slot: Mapped[str] = mapped_column(String(40), index=True)
    trigger: Mapped[str] = mapped_column(String(24), default="manual")  # event-driven | scheduled | manual | reprocess | catch-up | analysis
    status: Mapped[str] = mapped_column(String(16), default="success")  # success | provisional | failed
    chi_square_status: Mapped[str] = mapped_column(String(16), default="not-applicable")
    engine: Mapped[str] = mapped_column(String(32), default="python-lsq-v1")
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    diagnostics: Mapped[dict] = mapped_column(JSON, default=dict)
    starnet: Mapped[dict] = mapped_column(JSON, default=dict)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String(40), default=lambda: utcnow().isoformat())

    processing: Mapped[Processing] = relationship(back_populates="runs")


class OutputValue(Base):
    """Published results — one row per variable × slot, replaced on recompute."""

    __tablename__ = "output_values"
    __table_args__ = (UniqueConstraint("processing_id", "point_id", "component", "slot", name="uq_output_variable_slot"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    processing_id: Mapped[int] = mapped_column(ForeignKey("processings.id"), index=True)
    point_id: Mapped[str] = mapped_column(String(64))
    component: Mapped[str] = mapped_column(String(16))  # X Y Z DX DY DZ SX SY SZ
    slot: Mapped[str] = mapped_column(String(40), index=True)
    value: Mapped[float] = mapped_column(Float)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"))


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String(40), default=lambda: utcnow().isoformat(), index=True)
    processing_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class DemoState(Base):
    __tablename__ = "demo_state"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
