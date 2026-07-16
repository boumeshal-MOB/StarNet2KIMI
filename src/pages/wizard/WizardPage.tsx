import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Check, ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Bootstrap, VersionPayload } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";

const STEP_KEYS = ["wizard.step1", "wizard.step2", "wizard.step3", "wizard.step4", "wizard.step5", "wizard.step6", "wizard.step7", "wizard.step8", "wizard.step9"] as const;

interface General { name: string; description: string; kind: "single-station" | "network"; template: string; active: boolean }

export function WizardPage() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [boot, setBoot] = useState<Bootstrap | null>(null);
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [general, setGeneral] = useState<General>({ name: "", description: "", kind: "network", template: "uk", active: true });
  const [stationSel, setStationSel] = useState<Record<string, { selected: boolean; required: boolean; mode: "weak" | "fixed" | "free" }>>({});
  const [instrument, setInstrument] = useState<Record<string, { height: number }>>({});
  const [atmospheric, setAtmospheric] = useState<Record<string, unknown>>({ mode: "cycle-temperature-pressure", tolerance_minutes: 45, missing_policy: "fixed-fallback", fallback_temperature_c: 12, fallback_pressure_hpa: 1013.25, mark_provisional: true });
  const [defaultWeights, setDefaultWeights] = useState({ direction_arcsec: 2.0, zenith_arcsec: 2.5, distance_mm: 1.5, distance_ppm: 1.5 });
  const [targetMap, setTargetMap] = useState<Record<string, { point: string; type: string; constant: number }>>({});
  const [init, setInit] = useState({ method: "local-system", window_from: "2025-03-09T00:00:00.000Z", window_to: "2025-03-09T05:00:00.000Z" });
  const [adjustment, setAdjustment] = useState({ convergence_threshold_m: 1e-6, max_iterations: 20, chi_square_significance: 0.05, confidence_level: 0.95, error_propagation: true, auto_adjust_enabled: true, auto_adjust_max_iterations: 5, auto_adjust_max_std: 3.0, refraction_coefficient: 0.14 });
  const [runCfg, setRunCfg] = useState({ trigger: "event-driven", cycle_tolerance_minutes: 12, sync_tolerance_minutes: 60, max_epoch_to_slot_minutes: 330, max_reused_age_minutes: 300, allow_future_minutes: 45, allow_reuse_last_cycle: true, catch_up_on_late_data: true });
  const [gridMinutes, setGridMinutes] = useState(240);

  useEffect(() => {
    api.bootstrap().then(setBoot).catch((e) => setError(String(e.message ?? e)));
  }, []);

  // Template selection seeds atmospheric policy + weights.
  useEffect(() => {
    if (!boot) return;
    const tpl = boot.templates[general.template];
    if (tpl) {
      setAtmospheric({ ...tpl.atmospheric });
      setDefaultWeights({ ...(tpl.default_weights as typeof defaultWeights) });
    }
  }, [general.template, boot]);

  const stations = useMemo(() => boot?.stations ?? [], [boot]);
  const selectedStations = useMemo(() => stations.filter((s) => stationSel[s.code]?.selected), [stations, stationSel]);
  const selectedSensors = useMemo(
    () => selectedStations.flatMap((s) => s.sensors.map((sensor) => ({ station: s, sensor }))),
    [selectedStations],
  );

  // Default physical point per sensor; keep user overrides.
  useEffect(() => {
    setTargetMap((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const { station, sensor } of selectedSensors) {
        const key = `${station.code}/${sensor.id}`;
        if (!next[key]) {
          next[key] = { point: `PP_${sensor.raw_name}`, type: sensor.measurement_type, constant: sensor.prism_constant_required_m };
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [selectedSensors]);

  const connectivity = useMemo(() => {
    if (general.kind !== "network" || selectedStations.length < 2) return { ok: true, shared: 0 };
    const byPoint = new Map<string, Set<string>>();
    for (const { station, sensor } of selectedSensors) {
      const key = `${station.code}/${sensor.id}`;
      const point = targetMap[key]?.point;
      if (!point) continue;
      if (!byPoint.has(point)) byPoint.set(point, new Set());
      byPoint.get(point)!.add(station.code);
    }
    const adjacency = new Map<string, Set<string>>(selectedStations.map((s) => [s.code, new Set()]));
    let shared = 0;
    for (const codes of byPoint.values()) {
      if (codes.size > 1) shared++;
      codes.forEach((a) => codes.forEach((b) => b !== a && adjacency.get(a)!.add(b)));
    }
    const seen = new Set([selectedStations[0].code]);
    const queue = [selectedStations[0].code];
    while (queue.length) {
      const cur = queue.pop()!;
      adjacency.get(cur)?.forEach((n) => { if (!seen.has(n)) { seen.add(n); queue.push(n); } });
    }
    return { ok: seen.size === selectedStations.length, shared };
  }, [general.kind, selectedStations, selectedSensors, targetMap]);

  const blockers = useMemo(() => {
    const out: string[] = [];
    if (!general.name.trim()) out.push("Nom manquant / Missing name");
    if (selectedStations.length === 0) out.push("Aucune station / No station");
    if (general.kind === "network" && selectedStations.length < 2) out.push("Un réseau exige ≥ 2 stations / A network needs ≥ 2 stations");
    if (general.kind === "single-station" && selectedStations.length > 1) out.push("Station seule = 1 station / Single station = 1 station");
    if (!connectivity.ok) out.push("Réseau non connecté / Network not connected");
    return out;
  }, [general, selectedStations, connectivity]);

  function buildPayload(): VersionPayload {
    const targets = selectedSensors.map(({ station, sensor }) => {
      const key = `${station.code}/${sensor.id}`;
      const map = targetMap[key]!;
      const point = boot!.physical_points.find((p) => p.id === map.point);
      return {
        station_code: station.code,
        sensor_id: sensor.id,
        raw_name: sensor.raw_name,
        physical_point_id: map.point,
        role: (point?.known ? "reference" : map.point.startsWith("REF") ? "reference" : "monitoring") as "reference" | "monitoring",
        measurement: {
          type: map.type,
          required_constant_m: map.type === "reflectorless" ? 0 : map.constant,
          already_applied_constant_m: general.template === "fr" ? (Math.abs(map.constant - 0.0255) < 1e-9 ? 0.0255 : 0) : 0,
          target_height_m: sensor.target_height_m,
        },
        weights: { ...defaultWeights },
      };
    });
    const pointIds = [...new Set(targets.map((x) => x.physical_point_id))];
    const physicalPoints = pointIds.map((pid) => {
      const existing = boot!.physical_points.find((p) => p.id === pid);
      return {
        id: pid,
        role: targets.find((x) => x.physical_point_id === pid)!.role,
        known: existing?.known ?? null,
        constraint: { e: "weak" as const, n: "weak" as const, h: "weak" as const },
        sigma_m: existing?.sigma_m ?? { e: 0.002, n: 0.002, h: 0.002 },
      };
    });
    return {
      schema: "btm-topographic-adjustment/v1",
      template: general.template,
      kind: general.kind,
      stations: selectedStations.map((s) => ({
        code: s.code,
        required: stationSel[s.code]?.required ?? true,
        instrument_height_m: instrument[s.code]?.height ?? 0,
        coordinates: {
          mode: stationSel[s.code]?.mode ?? "weak",
          e: s.coordinates.e ?? undefined,
          n: s.coordinates.n ?? undefined,
          h: s.coordinates.h ?? undefined,
          sigma_m: 0.1,
        },
      })),
      targets,
      physical_points: physicalPoints,
      initialisation: { method: init.method, window_from: init.window_from, window_to: init.window_to },
      corrections: { atmospheric: atmospheric as never },
      adjustment: {
        dimension: "3D",
        units_linear: "M",
        units_angular: "DEG",
        system: init.method === "local-system" ? "LOCAL" : "GRID",
        coordinate_order: "ENH",
        convergence_threshold_m: adjustment.convergence_threshold_m,
        max_iterations: adjustment.max_iterations,
        chi_square_significance: adjustment.chi_square_significance,
        confidence_level: adjustment.confidence_level,
        error_propagation: adjustment.error_propagation,
        refraction_coefficient: adjustment.refraction_coefficient,
        auto_adjust: { enabled: adjustment.auto_adjust_enabled, max_iterations: adjustment.auto_adjust_max_iterations, max_standardized_residual: adjustment.auto_adjust_max_std },
      },
      default_weights: { ...defaultWeights },
      run: { ...runCfg, missing_station_policy: "provisional" },
      output: { grid_minutes: gridMinutes },
    };
  }

  async function create() {
    setBusy(true);
    setError(null);
    try {
      const created = await api.createProcessing({
        name: general.name,
        description: general.description,
        kind: general.kind,
        template: general.template,
        state: general.active ? "active" : "inactive",
        payload: buildPayload(),
      });
      navigate(`/processings/${created.id}`);
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  }

  if (!boot) return <div className="text-sm text-slate-400">{t("common.loading")}</div>;

  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="mb-1 text-xl font-semibold text-slate-900">{t("wizard.title")}</h1>
      <p className="mb-5 text-[12.5px] text-slate-400">{t("wizard.projectNote")}</p>

      <ol className="mb-6 flex flex-wrap gap-1">
        {STEP_KEYS.map((key, i) => (
          <li key={key}>
            <button
              onClick={() => setStep(i)}
              className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11.5px] font-medium ${
                i === step ? "bg-slate-900 text-white" : i < step ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-400"
              }`}
            >
              {i < step ? <Check className="h-3 w-3" /> : <span className="font-mono">{i + 1}</span>}
              <span className="hidden md:inline">{t(key)}</span>
            </button>
          </li>
        ))}
      </ol>

      <Card className="mb-5">
        <CardContent className="pt-5">
          {step === 0 && (
            <div className="space-y-4">
              <Field label={t("wizard.name")}><Input autoFocus value={general.name} onChange={(e) => setGeneral({ ...general, name: e.target.value })} placeholder="NTE Network — ATS34 + ATS35" /></Field>
              <Field label={t("wizard.description")}><Input value={general.description} onChange={(e) => setGeneral({ ...general, description: e.target.value })} /></Field>
              <div className="grid grid-cols-2 gap-4">
                <Field label={t("wizard.kind")}>
                  <Select value={general.kind} onValueChange={(v) => setGeneral({ ...general, kind: v as General["kind"] })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="single-station">{t("processings.kind.single")}</SelectItem>
                      <SelectItem value="network">{t("processings.kind.network")}</SelectItem>
                    </SelectContent>
                  </Select>
                </Field>
                <Field label={t("wizard.template")}>
                  <Select value={general.template} onValueChange={(v) => setGeneral({ ...general, template: v })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {Object.entries(boot.templates).map(([key, tpl]) => <SelectItem key={key} value={key}>{tpl.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </Field>
              </div>
              <label className="flex items-center gap-2.5 text-[13.5px] text-slate-700">
                <Switch checked={general.active} onCheckedChange={(v) => setGeneral({ ...general, active: v })} />
                {t("wizard.activeAfter")}
              </label>
            </div>
          )}

          {step === 1 && (
            <div className="space-y-3">
              <p className="text-[13px] text-slate-500">{t("wizard.selectStations")}</p>
              {stations.map((s) => {
                const sel = stationSel[s.code] ?? { selected: false, required: true, mode: "weak" as const };
                return (
                  <div key={s.code} className={`rounded-lg border p-3.5 ${sel.selected ? "border-blue-300 bg-blue-50/40" : "border-slate-200"}`}>
                    <div className="flex items-center gap-3">
                      <input
                        type="checkbox" className="h-4 w-4 rounded border-slate-300" checked={sel.selected}
                        onChange={(e) => setStationSel({ ...stationSel, [s.code]: { ...sel, selected: e.target.checked } })}
                      />
                      <span className="font-mono text-[14px] font-semibold text-slate-800">{s.code}</span>
                      <span className="text-[12px] text-slate-400">{s.instrument_model}</span>
                      <span className="ml-auto text-[11.5px] text-slate-400">
                        {s.sensors.length} {t("common.targets").toLowerCase()} · {s.observation_count} {t("misc.observations")} · {s.environment_readings} {t("misc.environment")}
                      </span>
                    </div>
                    {sel.selected && (
                      <div className="mt-3 flex flex-wrap items-center gap-4 border-t border-slate-200/70 pt-3 text-[12.5px]">
                        <span className="text-slate-400">{t("wizard.lastObs")}: <span className="font-mono">{s.last_observation_epoch?.slice(0, 16).replace("T", " ") ?? "—"}</span></span>
                        <label className="flex items-center gap-1.5">
                          <input type="checkbox" checked={sel.required} onChange={(e) => setStationSel({ ...stationSel, [s.code]: { ...sel, required: e.target.checked } })} className="h-3.5 w-3.5" />
                          {t("wizard.required")}
                        </label>
                        <label className="flex items-center gap-1.5">
                          {t("wizard.coordsMode")}
                          <Select value={sel.mode} onValueChange={(v) => setStationSel({ ...stationSel, [s.code]: { ...sel, mode: v as "weak" } })}>
                            <SelectTrigger className="h-7 w-28 text-[12px]"><SelectValue /></SelectTrigger>
                            <SelectContent>
                              <SelectItem value="fixed">fixed</SelectItem>
                              <SelectItem value="weak">weak (0.1 m)</SelectItem>
                              <SelectItem value="free">free</SelectItem>
                            </SelectContent>
                          </Select>
                        </label>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {step === 2 && (
            <div className="space-y-5">
              <div>
                <h3 className="mb-2 text-[13.5px] font-semibold text-slate-800">Correction atmosphérique</h3>
                <div className="grid gap-2">
                  {(
                    [
                      ["already-applied", "Déjà appliquée par la station / Already applied by the station"],
                      ["cycle-temperature-pressure", "Calculée par BTM (T/P raw_data par cycle) / Computed by BTM (cycle T/P)"],
                      ["fixed-temperature-pressure", "T/P fixes configurées / Fixed configured T/P"],
                    ] as const
                  ).map(([mode, label]) => (
                    <label key={mode} className={`flex items-center gap-2.5 rounded-lg border p-3 text-[13px] ${atmospheric.mode === mode ? "border-blue-300 bg-blue-50/40" : "border-slate-200"}`}>
                      <input type="radio" name="atmo" checked={atmospheric.mode === mode} onChange={() => setAtmospheric({ ...atmospheric, mode })} />
                      {label}
                    </label>
                  ))}
                </div>
                {atmospheric.mode === "cycle-temperature-pressure" && (
                  <div className="mt-3 grid grid-cols-2 gap-3 rounded-lg bg-slate-50 p-3 text-[12.5px]">
                    <NumField label="Tolérance T/P (min)" value={Number(atmospheric.tolerance_minutes ?? 45)} onChange={(v) => setAtmospheric({ ...atmospheric, tolerance_minutes: v })} />
                    <label className="text-slate-600">
                      Si absentes / If missing
                      <Select value={String(atmospheric.missing_policy ?? "fixed-fallback")} onValueChange={(v) => setAtmospheric({ ...atmospheric, missing_policy: v })}>
                        <SelectTrigger className="mt-1 h-8 text-[12px]"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="fixed-fallback">Valeurs fixes de secours</SelectItem>
                          <SelectItem value="continue-without-correction">Aucune correction ce cycle</SelectItem>
                          <SelectItem value="wait-or-fail">Attendre / échouer</SelectItem>
                        </SelectContent>
                      </Select>
                    </label>
                    <NumField label="T secours (°C)" value={Number(atmospheric.fallback_temperature_c ?? 12)} onChange={(v) => setAtmospheric({ ...atmospheric, fallback_temperature_c: v })} />
                    <NumField label="P secours (hPa)" value={Number(atmospheric.fallback_pressure_hpa ?? 1013.25)} onChange={(v) => setAtmospheric({ ...atmospheric, fallback_pressure_hpa: v })} />
                  </div>
                )}
                {atmospheric.mode === "fixed-temperature-pressure" && (
                  <div className="mt-3 grid grid-cols-2 gap-3 rounded-lg bg-slate-50 p-3 text-[12.5px]">
                    <NumField label="T (°C)" value={Number(atmospheric.temperature_c ?? 12)} onChange={(v) => setAtmospheric({ ...atmospheric, temperature_c: v })} />
                    <NumField label="P (hPa)" value={Number(atmospheric.pressure_hpa ?? 1013.25)} onChange={(v) => setAtmospheric({ ...atmospheric, pressure_hpa: v })} />
                  </div>
                )}
                <p className="mt-2 text-[11.5px] text-slate-400">Jamais deux corrections : la constante de prisme et le ppm sont appliqués une seule fois, .SCALE n'est jamais alimenté par la formule.</p>
              </div>
              <div>
                <h3 className="mb-2 text-[13.5px] font-semibold text-slate-800">Poids par défaut</h3>
                <div className="grid grid-cols-4 gap-3 text-[12.5px]">
                  <NumField label={t("lab.direction")} value={defaultWeights.direction_arcsec} step={0.1} onChange={(v) => setDefaultWeights({ ...defaultWeights, direction_arcsec: v })} />
                  <NumField label={t("lab.zenith")} value={defaultWeights.zenith_arcsec} step={0.1} onChange={(v) => setDefaultWeights({ ...defaultWeights, zenith_arcsec: v })} />
                  <NumField label={t("lab.distMm")} value={defaultWeights.distance_mm} step={0.1} onChange={(v) => setDefaultWeights({ ...defaultWeights, distance_mm: v })} />
                  <NumField label={t("lab.distPpm")} value={defaultWeights.distance_ppm} step={0.1} onChange={(v) => setDefaultWeights({ ...defaultWeights, distance_ppm: v })} />
                </div>
              </div>
              {selectedStations.map((s) => (
                <div key={s.code} className="flex items-center gap-3 text-[12.5px]">
                  <span className="font-mono font-semibold">{s.code}</span>
                  <NumField label="Hauteur instrument (m)" value={instrument[s.code]?.height ?? 0} step={0.001} onChange={(v) => setInstrument({ ...instrument, [s.code]: { height: v } })} />
                </div>
              ))}
            </div>
          )}

          {step === 3 && (
            <div>
              <p className="mb-3 rounded-lg bg-blue-50 px-3 py-2 text-[12.5px] text-blue-800">{t("wizard.sharedHint")}</p>
              <div className="max-h-[460px] overflow-auto">
                <table className="w-full text-[12px]">
                  <thead className="sticky top-0 bg-white">
                    <tr className="border-b text-left text-[10.5px] uppercase text-slate-400">
                      <th className="px-2 py-1.5 font-medium">{t("common.station")}</th>
                      <th className="px-2 py-1.5 font-medium">{t("common.target")}</th>
                      <th className="px-2 py-1.5 font-medium">Mesure</th>
                      <th className="px-2 py-1.5 font-medium">Cst prisme</th>
                      <th className="px-2 py-1.5 font-medium">{t("wizard.physicalPoint")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedSensors.map(({ station, sensor }) => {
                      const key = `${station.code}/${sensor.id}`;
                      const map = targetMap[key] ?? { point: "", type: sensor.measurement_type, constant: sensor.prism_constant_required_m };
                      const shared = selectedSensors.filter((x) => targetMap[`${x.station.code}/${x.sensor.id}`]?.point === map.point).length > 1;
                      return (
                        <tr key={key} className="border-b border-slate-100">
                          <td className="px-2 py-1.5 font-mono text-slate-500">{station.code.replace("NTE_", "")}</td>
                          <td className="px-2 py-1.5 font-mono">{sensor.raw_name}</td>
                          <td className="px-2 py-1.5">
                            <Select value={map.type} onValueChange={(v) => setTargetMap({ ...targetMap, [key]: { ...map, type: v } })}>
                              <SelectTrigger className="h-7 w-32 text-[11.5px]"><SelectValue /></SelectTrigger>
                              <SelectContent>
                                <SelectItem value="prism">prisme</SelectItem>
                                <SelectItem value="reflective-sheet">feuille</SelectItem>
                                <SelectItem value="reflectorless">sans prisme</SelectItem>
                              </SelectContent>
                            </Select>
                          </td>
                          <td className="px-2 py-1.5">
                            <Input type="number" step="0.0001" disabled={map.type === "reflectorless"} value={map.constant}
                              onChange={(e) => setTargetMap({ ...targetMap, [key]: { ...map, constant: Number(e.target.value) } })}
                              className="h-7 w-24 font-mono text-[11.5px]" />
                          </td>
                          <td className="px-2 py-1.5">
                            <div className="flex items-center gap-1.5">
                              <Input value={map.point} list={`points-${key}`} onChange={(e) => setTargetMap({ ...targetMap, [key]: { ...map, point: e.target.value } })}
                                className={`h-7 w-44 font-mono text-[11.5px] ${shared ? "border-emerald-400 bg-emerald-50" : ""}`} />
                              <datalist id={`points-${key}`}>
                                {boot.physical_points.map((p) => <option key={p.id} value={p.id} />)}
                              </datalist>
                              {shared && <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700">commun</span>}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <div className={`mt-3 rounded-lg px-3 py-2 text-[12.5px] ${connectivity.ok ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"}`}>
                {connectivity.ok ? `✓ ${t("wizard.connectivityOk")} (${connectivity.shared})` : `✗ ${t("wizard.connectivityKo")}`}
              </div>
            </div>
          )}

          {step === 4 && (
            <div className="space-y-4">
              <div className="grid gap-2">
                {(
                  [
                    ["known-coordinates", t("wizard.knownCoords")],
                    ["local-system", t("wizard.localSystem") + " (0/0/0/0 possible)"],
                  ] as const
                ).map(([method, label]) => (
                  <label key={method} className={`flex items-center gap-2.5 rounded-lg border p-3 text-[13px] ${init.method === method ? "border-blue-300 bg-blue-50/40" : "border-slate-200"}`}>
                    <input type="radio" name="init" checked={init.method === method} onChange={() => setInit({ ...init, method })} />
                    {label}
                  </label>
                ))}
              </div>
              <p className="text-[12.5px] text-slate-500">{t("wizard.initNote")}</p>
              <div className="grid grid-cols-2 gap-3 text-[12.5px]">
                <label className="text-slate-600">{t("detail.from")}
                  <Input value={init.window_from} onChange={(e) => setInit({ ...init, window_from: e.target.value })} className="mt-1 font-mono text-[12px]" />
                </label>
                <label className="text-slate-600">{t("detail.to")}
                  <Input value={init.window_to} onChange={(e) => setInit({ ...init, window_to: e.target.value })} className="mt-1 font-mono text-[12px]" />
                </label>
              </div>
            </div>
          )}

          {step === 5 && (
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-3 text-[12.5px]">
                <NumField label="Seuil convergence (m)" value={adjustment.convergence_threshold_m} step={0.000001} onChange={(v) => setAdjustment({ ...adjustment, convergence_threshold_m: v })} />
                <NumField label="Itérations max" value={adjustment.max_iterations} step={1} onChange={(v) => setAdjustment({ ...adjustment, max_iterations: Math.round(v) })} />
                <NumField label="χ² significativité" value={adjustment.chi_square_significance} step={0.01} onChange={(v) => setAdjustment({ ...adjustment, chi_square_significance: v })} />
                <NumField label="Confiance" value={adjustment.confidence_level} step={0.01} onChange={(v) => setAdjustment({ ...adjustment, confidence_level: v })} />
                <NumField label="Réfraction" value={adjustment.refraction_coefficient} step={0.01} onChange={(v) => setAdjustment({ ...adjustment, refraction_coefficient: v })} />
              </div>
              <label className="flex items-center gap-2 text-[13px] text-slate-700">
                <Switch checked={adjustment.error_propagation} onCheckedChange={(v) => setAdjustment({ ...adjustment, error_propagation: v })} />
                Propagation des erreurs
              </label>
              <div className="rounded-lg border border-slate-200 p-3">
                <label className="flex items-center gap-2 text-[13px] font-medium text-slate-800">
                  <Switch checked={adjustment.auto_adjust_enabled} onCheckedChange={(v) => setAdjustment({ ...adjustment, auto_adjust_enabled: v })} />
                  {t("run.autoAdjust")} — jamais si χ² non interprétable
                </label>
                {adjustment.auto_adjust_enabled && (
                  <div className="mt-3 grid grid-cols-2 gap-3 text-[12.5px]">
                    <NumField label="Itérations max" value={adjustment.auto_adjust_max_iterations} step={1} onChange={(v) => setAdjustment({ ...adjustment, auto_adjust_max_iterations: Math.round(v) })} />
                    <NumField label="Seuil résidu std" value={adjustment.auto_adjust_max_std} step={0.5} onChange={(v) => setAdjustment({ ...adjustment, auto_adjust_max_std: v })} />
                  </div>
                )}
              </div>
              <details className="rounded-lg bg-slate-50 p-3 text-[12.5px] text-slate-500">
                <summary className="cursor-pointer font-medium text-slate-700">{t("common.advanced")}</summary>
                <div className="mt-2 grid grid-cols-2 gap-2 font-mono text-[11.5px]">
                  <span>DIMENSION: 3D</span><span>UNITS: M / DEG</span>
                  <span>SYSTEM: {init.method === "local-system" ? "LOCAL" : "GRID"}</span><span>ORDER: ENH</span>
                  <span>.SCALE: 1.0 (jamais atmosphérique)</span><span>Corrections: upstream BTM</span>
                </div>
              </details>
            </div>
          )}

          {step === 6 && (
            <div className="space-y-4">
              <div className="grid gap-2">
                {(
                  [
                    ["event-driven", "Event-driven (défaut)"],
                    ["scheduled", "Planifié toutes les X minutes"],
                    ["manual", "Manuel"],
                  ] as const
                ).map(([mode, label]) => (
                  <label key={mode} className={`flex items-center gap-2.5 rounded-lg border p-3 text-[13px] ${runCfg.trigger === mode ? "border-blue-300 bg-blue-50/40" : "border-slate-200"}`}>
                    <input type="radio" name="trigger" checked={runCfg.trigger === mode} onChange={() => setRunCfg({ ...runCfg, trigger: mode })} />
                    {label}
                  </label>
                ))}
              </div>
              <div className="grid grid-cols-3 gap-3 text-[12.5px]">
                <NumField label="Tolérance synchro (min)" value={runCfg.sync_tolerance_minutes} step={5} onChange={(v) => setRunCfg({ ...runCfg, sync_tolerance_minutes: v })} />
                <NumField label="Âge max réutilisation (min)" value={runCfg.max_reused_age_minutes} step={15} onChange={(v) => setRunCfg({ ...runCfg, max_reused_age_minutes: v })} />
                <NumField label="Fenêtre époque→slot (min)" value={runCfg.max_epoch_to_slot_minutes} step={15} onChange={(v) => setRunCfg({ ...runCfg, max_epoch_to_slot_minutes: v })} />
              </div>
              <label className="flex items-center gap-2 text-[13px] text-slate-700">
                <Switch checked={runCfg.allow_reuse_last_cycle} onCheckedChange={(v) => setRunCfg({ ...runCfg, allow_reuse_last_cycle: v })} />
                Réutiliser le dernier cycle d'une station (résultat provisoire, tracé)
              </label>
              <label className="flex items-center gap-2 text-[13px] text-slate-700">
                <Switch checked={runCfg.catch_up_on_late_data} onCheckedChange={(v) => setRunCfg({ ...runCfg, catch_up_on_late_data: v })} />
                Catch-up automatique sur donnée tardive (idempotent)
              </label>
            </div>
          )}

          {step === 7 && (
            <div className="space-y-4">
              <NumField label="Grille de publication UTC (minutes)" value={gridMinutes} step={30} onChange={(v) => setGridMinutes(Math.max(5, Math.round(v)))} />
              <div className="rounded-lg bg-slate-50 p-3 font-mono text-[12px] text-slate-600">
                <p>Variables publiées par cible (une seule fois, réutilisées entre versions) :</p>
                <p className="mt-1">Adjusted X/Y/Z · Delta X/Y/Z · Sigma X/Y/Z</p>
                <p className="mt-2 text-slate-400">Indicateurs globaux : χ² · facteur de variance · références · disponibilité · provisoire</p>
              </div>
              <p className="text-[12px] text-slate-400">Une cible absente ne reçoit aucune coordonnée inventée. Un recalcul remplace la valeur au même timestamp.</p>
            </div>
          )}

          {step === 8 && (
            <div className="space-y-4">
              {blockers.length > 0 ? (
                <div className="rounded-lg bg-red-50 p-3">
                  <div className="mb-1 text-[13px] font-semibold text-red-700">{t("wizard.blockers")}</div>
                  <ul className="list-inside list-disc text-[12.5px] text-red-600">
                    {blockers.map((b) => <li key={b}>{b}</li>)}
                  </ul>
                </div>
              ) : (
                <div className="rounded-lg bg-emerald-50 p-3 text-[13px] font-medium text-emerald-700">✓ Configuration valide</div>
              )}
              <Review payload={buildPayload()} general={general} sharedCount={connectivity.shared} />
            </div>
          )}
        </CardContent>
      </Card>

      {error && <div className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</div>}

      <div className="flex justify-between">
        <Button variant="outline" onClick={() => setStep(Math.max(0, step - 1))} disabled={step === 0} className="gap-1">
          <ChevronLeft className="h-4 w-4" /> {t("common.back")}
        </Button>
        {step < 8 ? (
          <Button onClick={() => setStep(step + 1)} className="gap-1">
            {t("common.next")} <ChevronRight className="h-4 w-4" />
          </Button>
        ) : (
          <Button onClick={create} disabled={busy || blockers.length > 0} className="gap-1.5">
            {busy && <Loader2 className="h-4 w-4 animate-spin" />}
            {busy ? t("wizard.creating") : t("common.create")}
          </Button>
        )}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block text-[13px] font-medium text-slate-700">
      {label}
      <div className="mt-1">{children}</div>
    </label>
  );
}

function NumField({ label, value, onChange, step = 1 }: { label: string; value: number; onChange: (v: number) => void; step?: number }) {
  return (
    <label className="block text-slate-600">
      {label}
      <Input type="number" value={value} step={step} onChange={(e) => onChange(Number(e.target.value))} className="mt-1 h-8 font-mono text-[12px]" />
    </label>
  );
}

function Review({ payload, general, sharedCount }: { payload: VersionPayload; general: General; sharedCount: number }) {
  const rows: [string, string][] = [
    ["Nom", general.name],
    ["Type", general.kind],
    ["Template", general.template],
    ["Stations", payload.stations.map((s) => `${s.code} (${s.coordinates.mode})`).join(", ")],
    ["Cibles", `${payload.targets.length} → ${payload.physical_points.length} points physiques (${sharedCount} communs)`],
    ["Références connues", String(payload.physical_points.filter((p) => p.known).length)],
    ["Initialisation", `${payload.initialisation.method} — ${payload.initialisation.window_from?.slice(0, 16)} → ${payload.initialisation.window_to?.slice(0, 16)}`],
    ["Atmosphère", String(payload.corrections.atmospheric.mode)],
    ["Ajustement", `3D · seuil ${payload.adjustment.convergence_threshold_m} · χ² ${payload.adjustment.chi_square_significance} · confiance ${payload.adjustment.confidence_level} · AutoAdjust ${payload.adjustment.auto_adjust.enabled ? "ON" : "OFF"}`],
    ["Run", `${payload.run.trigger} · synchro ±${payload.run.sync_tolerance_minutes} min · réutilisation ≤ ${payload.run.max_reused_age_minutes} min`],
    ["Sorties", `grille ${payload.output.grid_minutes} min`],
  ];
  return (
    <Card>
      <CardHeader className="pb-2"><CardTitle className="text-[14px]">Synthèse</CardTitle></CardHeader>
      <CardContent className="p-0">
        <table className="w-full text-[12.5px]">
          <tbody>
            {rows.map(([k, v]) => (
              <tr key={k} className="border-b border-slate-100 last:border-0">
                <td className="w-44 px-4 py-2 font-medium text-slate-500">{k}</td>
                <td className="px-4 py-2 font-mono text-[12px] text-slate-800">{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}
