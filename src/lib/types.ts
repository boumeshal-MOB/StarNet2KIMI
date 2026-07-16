// API contract types — mirror the FastAPI responses.

export interface SensorInfo {
  id: number;
  raw_name: string;
  measurement_type: string;
  prism_constant_required_m: number;
  target_height_m: number;
}

export interface StationInfo {
  code: string;
  name: string;
  instrument_model: string;
  site: string;
  coordinates: { e: number | null; n: number | null; h: number | null };
  observation_count: number;
  last_observation_epoch: string | null;
  environment_readings: number;
  sensors: SensorInfo[];
}

export interface PhysicalPointInfo {
  id: string;
  label: string;
  known: { e: number; n: number; h: number } | null;
  sigma_m: { e: number; n: number; h: number } | null;
}

export interface TemplateInfo {
  label: string;
  prism_examples_m: number[];
  atmospheric: Record<string, unknown>;
  default_weights: Record<string, number>;
}

export interface Bootstrap {
  stations: StationInfo[];
  physical_points: PhysicalPointInfo[];
  templates: Record<string, TemplateInfo>;
}

export interface VersionPayload {
  schema?: string;
  template?: string;
  kind?: string;
  stations: StationConfig[];
  targets: TargetConfig[];
  physical_points: PhysicalPointConfig[];
  initialisation: { method: string; window_from: string | null; window_to: string | null };
  corrections: { atmospheric: AtmosphericConfig };
  adjustment: AdjustmentConfig;
  default_weights: Weights;
  run: RunConfig;
  output: { grid_minutes: number };
}

export interface StationConfig {
  code: string;
  required: boolean;
  instrument_height_m: number;
  coordinates: { mode: "fixed" | "weak" | "free"; e?: number; n?: number; h?: number; sigma_m?: number; orientation_rad?: number | null };
}

export interface TargetConfig {
  station_code: string;
  sensor_id: number;
  raw_name: string;
  physical_point_id: string;
  role: "reference" | "monitoring";
  measurement: { type: string; required_constant_m: number; already_applied_constant_m: number; target_height_m: number };
  weights: Weights;
  excluded?: boolean;
}

export interface Weights {
  direction_arcsec: number;
  zenith_arcsec: number;
  distance_mm: number;
  distance_ppm: number;
}

export interface PhysicalPointConfig {
  id: string;
  role: "reference" | "monitoring";
  known: { e: number; n: number; h: number } | null;
  constraint: { e: "fixed" | "weak" | "free"; n: "fixed" | "weak" | "free"; h: "fixed" | "weak" | "free" };
  sigma_m: { e?: number; n?: number; h?: number };
}

export interface AtmosphericConfig {
  mode: "already-applied" | "cycle-temperature-pressure" | "fixed-temperature-pressure";
  tolerance_minutes?: number;
  missing_policy?: string;
  fallback_temperature_c?: number;
  fallback_pressure_hpa?: number;
  temperature_c?: number;
  pressure_hpa?: number;
  mark_provisional?: boolean;
}

export interface AdjustmentConfig {
  dimension: string;
  units_linear: string;
  units_angular: string;
  system: string;
  coordinate_order: string;
  convergence_threshold_m: number;
  max_iterations: number;
  chi_square_significance: number;
  confidence_level: number;
  error_propagation: boolean;
  refraction_coefficient?: number;
  auto_adjust: { enabled: boolean; max_iterations: number; max_standardized_residual: number; outliers_removed_per_iteration?: number };
}

export interface RunConfig {
  trigger: string;
  cycle_tolerance_minutes: number;
  sync_tolerance_minutes: number;
  max_epoch_to_slot_minutes: number;
  max_reused_age_minutes: number;
  allow_future_minutes?: number;
  allow_reuse_last_cycle: boolean;
  missing_station_policy: string;
  catch_up_on_late_data: boolean;
}

export interface VersionSummary {
  id: number;
  processing_id: number;
  number: number;
  status: "draft" | "active" | "inactive" | "archived";
  valid_from: string;
  valid_to: string | null;
  origin: string;
  created_at: string;
  payload: VersionPayload;
}

export interface ProcessingSummary {
  id: number;
  name: string;
  description: string;
  kind: "single-station" | "network";
  template: string;
  state: string;
  created_at: string;
  active_version: VersionSummary | null;
  version_count: number;
  run_count: number;
  last_run: RunSummary | null;
  versions?: VersionSummary[];
}

export interface RunSummary {
  id: number;
  processing_id: number;
  version_id: number;
  slot: string;
  trigger: string;
  status: "success" | "provisional" | "failed";
  chi_square_status: "passed" | "failed" | "not-applicable";
  engine: string;
  duration_ms: number;
  created_at: string;
}

export interface AdjustedPoint {
  id: string;
  role: string;
  e: number;
  n: number;
  h: number;
  sigma_e: number;
  sigma_n: number;
  sigma_h: number;
  ellipse_semi_major_m: number;
  ellipse_semi_minor_m: number;
  ellipse_orientation_deg: number;
  observation_count: number;
  initial_e?: number;
  initial_n?: number;
  initial_h?: number;
  delta_e?: number;
  delta_n?: number;
  delta_h?: number;
}

export interface ResidualEntry {
  id: string;
  raw_observation_id: string;
  station_id: string;
  target_id: string;
  kind: string;
  residual: number;
  sigma: number;
  standardized_residual: number;
  normalized_residual: number;
  redundancy: number;
}

export interface RunDetail extends Omit<RunSummary, "id"> {
  result: {
    ok?: boolean;
    converged?: boolean;
    iterations?: number;
    observation_count?: number;
    rank?: number;
    rank_deficiency?: number;
    unknown_count?: number;
    degrees_of_freedom?: number;
    variance_factor?: number;
    chi_square_status?: string;
    chi_square_lower?: number;
    chi_square_upper?: number;
    max_standardized_residual?: number;
    points?: AdjustedPoint[];
    orientations?: { station_id: string; value_rad: number; sigma_rad: number; fixed: boolean }[];
    residuals?: ResidualEntry[];
    auto_adjust_attempts?: { attempt: number; excluded_scalar_observation_id: string; kind: string; standardized_residual: number; chi_square_status_after: string }[];
    error_factor_by_type?: Record<string, number>;
  };
  diagnostics: {
    failure?: string;
    provisional_reasons?: string[];
    synchronisation?: {
      slot: string;
      stations: { station_code: string; state: string; cycle_epoch?: string; age_minutes?: number; target_count?: number; expected_target_count?: number; availability_percent?: number }[];
    };
    corrections?: { count: number; mode: string; traces: CorrectionTrace[] };
    initialisation?: {
      coverage?: { available_station_target_pairs: number; expected_station_target_pairs: number; window_from: string; window_to: string };
      station_solutions?: { station_id: string; method: string; tie_count: number; horizontal_rms_m: number }[];
      failures?: { station_id: string; reason: string }[];
    };
  };
  starnet: { dat?: string; prj?: string; pts?: string; err?: string; engine_names?: Record<string, string> };
  id: number | null;
}

export interface CorrectionTrace {
  observation_id: string;
  station_code: string;
  target_name: string;
  physical_point_id: string;
  stored_slope_distance_m: number;
  prism_delta_m: number;
  atmospheric_ppm: number;
  atmospheric_source: string;
  temperature_c: number | null;
  pressure_hpa: number | null;
  final_slope_distance_m: number;
  provisional: boolean;
  warnings: string[];
}

export interface AuditEvent {
  id: number;
  ts: string;
  kind: string;
  message: string;
  processing_id: number | null;
}
