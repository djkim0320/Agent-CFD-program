from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import Form
from pydantic import BaseModel

from aero_agent_contracts import (
    AnalysisRequest,
    ConnectionMode,
    FlowCondition,
    FrameSpec,
    GeometryKind,
    ReferenceValues,
    SolverKind,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


class CreateConnectionRequest(BaseModel):
    mode: ConnectionMode
    label: str | None = None
    data_policy: str = "summary_first"
    credentials_hint: dict[str, str] | None = None


class CreateJobFromPreflightRequest(BaseModel):
    preflight_id: str


class ArtifactPayload(BaseModel):
    job_id: str
    kind: str
    path: str
    size_bytes: int


class PreflightMultipartForm(BaseModel):
    connection_id: str | None = None
    connection_mode: ConnectionMode
    unit: Literal["m", "mm", "cm", "in", "ft"]
    geometry_kind: Literal["general_3d", "aircraft_vsp"]
    solver_preference: Literal["auto", "vspaero", "su2", "openfoam"] = "auto"
    fidelity: Literal["fast", "balanced", "high"] = "balanced"
    forward_axis: Literal["x", "y", "z"] = "x"
    up_axis: Literal["x", "y", "z"] = "z"
    symmetry_plane: Literal["xy", "yz", "xz"] | None = None
    moment_center: str | None = None
    area: float
    length: float | None = None
    span: float | None = None
    velocity: float | None = None
    mach: float | None = None
    aoa: float = 0.0
    sideslip: float = 0.0
    altitude: float | None = None
    density: float | None = None
    viscosity: float | None = None
    notes: str | None = None

    @classmethod
    def as_form(
        cls,
        connection_id: str | None = Form(None),
        connection_mode: ConnectionMode = Form(...),
        unit: Literal["m", "mm", "cm", "in", "ft"] = Form(...),
        geometry_kind: Literal["general_3d", "aircraft_vsp"] = Form(...),
        solver_preference: Literal["auto", "vspaero", "su2", "openfoam"] = Form("auto"),
        fidelity: Literal["fast", "balanced", "high"] = Form("balanced"),
        frame_forward_axis: Literal["x", "y", "z"] = Form("x"),
        frame_up_axis: Literal["x", "y", "z"] = Form("z"),
        frame_symmetry_plane: Literal["xy", "yz", "xz"] | None = Form(None),
        frame_moment_center: str | None = Form(None),
        reference_area: float = Form(...),
        reference_length: float | None = Form(None),
        reference_span: float | None = Form(None),
        flow_velocity: float | None = Form(None),
        flow_mach: float | None = Form(None),
        flow_aoa: float = Form(0.0),
        flow_sideslip: float = Form(0.0),
        flow_altitude: float | None = Form(None),
        flow_density: float | None = Form(None),
        flow_viscosity: float | None = Form(None),
        notes: str | None = Form(None),
    ) -> "PreflightMultipartForm":
        return cls(
            connection_id=connection_id,
            connection_mode=connection_mode,
            unit=unit,
            geometry_kind=geometry_kind,
            solver_preference=solver_preference,
            fidelity=fidelity,
            forward_axis=frame_forward_axis,
            up_axis=frame_up_axis,
            symmetry_plane=frame_symmetry_plane,
            moment_center=frame_moment_center,
            area=reference_area,
            length=reference_length,
            span=reference_span,
            velocity=flow_velocity,
            mach=flow_mach,
            aoa=flow_aoa,
            sideslip=flow_sideslip,
            altitude=flow_altitude,
            density=flow_density,
            viscosity=flow_viscosity,
            notes=notes,
        )

    def to_analysis_request(self, geometry_file: str) -> AnalysisRequest:
        moment_center = None
        if self.moment_center:
            values = [part.strip() for part in self.moment_center.split(",")]
            if len(values) == 3:
                try:
                    moment_center = (float(values[0]), float(values[1]), float(values[2]))
                except ValueError:
                    moment_center = None
        return AnalysisRequest(
            geometry_file=geometry_file,
            unit=self.unit,
            geometry_kind_hint=GeometryKind(self.geometry_kind),
            solver_preference=SolverKind(self.solver_preference),
            fidelity=self.fidelity,
            frame=FrameSpec(
                forward_axis=self.forward_axis,
                up_axis=self.up_axis,
                symmetry_plane=self.symmetry_plane,
                moment_center=moment_center,
            ),
            reference_values=ReferenceValues(area=self.area, length=self.length, span=self.span),
            flow=FlowCondition(
                velocity=self.velocity,
                mach=self.mach,
                aoa=self.aoa,
                sideslip=self.sideslip,
                altitude=self.altitude,
                density=self.density,
                viscosity=self.viscosity,
            ),
            notes=self.notes,
        )
