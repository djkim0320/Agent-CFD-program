export * from "../generated/contracts";

export interface FrameFormState {
  forwardAxis: "x" | "y" | "z";
  upAxis: "x" | "y" | "z";
  symmetryPlane: string;
  momentCenter: string;
}

export interface ReferenceValuesFormState {
  area: string;
  length: string;
  span: string;
}

export interface FlowFormState {
  velocity: string;
  mach: string;
  aoa: string;
  sideslip: string;
  altitude: string;
  density: string;
  viscosity: string;
}

export interface AnalysisFormState {
  geometryFile: File | null;
  unit: string;
  frame: FrameFormState;
  referenceValues: ReferenceValuesFormState;
  flow: FlowFormState;
  fidelity: "fast" | "balanced" | "high";
  solverPreference: "auto" | "vspaero" | "su2" | "openfoam";
  notes: string;
}
