import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { fmtCoord, fmtDuration, fmtMm, fmtSlot } from "@/lib/format";
import type { RunDetail } from "@/lib/types";
import { ChiBadge, RunStatusBadge } from "@/components/StatusBadge";
import { NetworkMap } from "@/components/NetworkMap";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export function RunDetailPage() {
  const { id } = useParams();
  const { t } = useI18n();
  const [run, setRun] = useState<RunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starnetTab, setStarnetTab] = useState<"dat" | "prj" | "pts" | "err">("dat");

  useEffect(() => {
    api.runDetail(Number(id)).then(setRun).catch((e) => setError(String(e.message ?? e)));
  }, [id]);

  const residualChart = useMemo(() => {
    if (!run?.result?.residuals) return [];
    return run.result.residuals
      .filter((r) => r.kind !== "constraint")
      .map((r) => ({
        id: r.id.replace(/^obs-/, "").slice(0, 26),
        std: Math.round(r.standardized_residual * 100) / 100,
        kind: r.kind,
      }));
  }, [run]);

  if (error) return <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</div>;
  if (!run) return <div className="text-sm text-slate-400">{t("common.loading")}</div>;

  const result = run.result ?? {};
  const diag = run.diagnostics ?? {};
  const syncStations = diag.synchronisation?.stations ?? [];
  const attempts = result.auto_adjust_attempts ?? [];
  const sights = (result.residuals ?? [])
    .filter((r) => r.kind === "sd" && r.station_id)
    .map((r) => ({ station_id: r.station_id, target_id: r.target_id }));

  return (
    <div className="mx-auto max-w-7xl">
      <div className="mb-5">
        <div className="flex items-center gap-2 text-[12px] text-slate-400">
          <Link to="/" className="hover:text-slate-600">{t("processings.title")}</Link>
          <span>/</span>
          <Link to={`/processings/${run.processing_id}`} className="hover:text-slate-600">#{run.processing_id}</Link>
          <span>/</span>
          <span className="text-slate-600">{t("run.title")} #{run.id}</span>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="font-mono text-lg font-semibold text-slate-900">{fmtSlot(run.slot)}</h1>
          <RunStatusBadge status={run.status} />
          <ChiBadge status={run.chi_square_status} />
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-500 ring-1 ring-inset ring-slate-500/20">{run.trigger}</span>
          <span className="ml-auto font-mono text-[12px] text-slate-400">{run.engine} · {fmtDuration(run.duration_ms)}</span>
        </div>
      </div>

      {diag.failure && <div className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{diag.failure}</div>}
      {diag.provisional_reasons && diag.provisional_reasons.length > 0 && (
        <div className="mb-4 rounded-lg bg-amber-50 p-3 text-[13px] text-amber-800">
          <span className="font-medium">{t("run.provisionalReasons")}:</span> {[...new Set(diag.provisional_reasons)].join(" · ")}
        </div>
      )}

      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-6">
        <Kpi label={t("run.converged")} value={result.converged ? t("common.yes") : t("common.no")} tone={result.converged ? "ok" : "ko"} />
        <Kpi label={t("run.iterations")} value={String(result.iterations ?? "—")} />
        <Kpi label={t("run.rank")} value={`${result.rank ?? "—"}${result.rank_deficiency ? ` (−${result.rank_deficiency})` : ""}`} tone={result.rank_deficiency ? "ko" : "ok"} />
        <Kpi label={t("run.dof")} value={String(result.degrees_of_freedom ?? "—")} />
        <Kpi label={t("run.varianceFactor")} value={result.variance_factor !== undefined && Number.isFinite(result.variance_factor) ? result.variance_factor.toFixed(3) : "—"} />
        <Kpi label={t("run.maxStdRes")} value={result.max_standardized_residual?.toFixed(2) ?? "—"} tone={(result.max_standardized_residual ?? 0) > 3 ? "warn" : "ok"} />
      </div>

      {attempts.length > 0 && (
        <Card className="mb-4 border-violet-200 bg-violet-50/40">
          <CardHeader className="pb-2"><CardTitle className="text-[13.5px] text-violet-900">{t("run.autoAdjust")} — {attempts.length} {t("run.excludedObs").toLowerCase()}</CardTitle></CardHeader>
          <CardContent className="space-y-1">
            {attempts.map((a, i) => (
              <div key={i} className="flex items-center gap-3 font-mono text-[12px] text-violet-800">
                <span className="rounded bg-violet-100 px-1.5 py-0.5 text-[10.5px]">#{a.attempt}</span>
                <span className="truncate">{a.excluded_scalar_observation_id}</span>
                <span className="ml-auto">std {a.standardized_residual.toFixed(1)}</span>
                <ChiBadge status={a.chi_square_status_after} />
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <Tabs defaultValue="network">
        <TabsList>
          <TabsTrigger value="network">{t("run.network")}</TabsTrigger>
          <TabsTrigger value="points">{t("run.adjustedPoints")} ({result.points?.length ?? 0})</TabsTrigger>
          <TabsTrigger value="residuals">{t("run.residuals")} ({result.residuals?.length ?? 0})</TabsTrigger>
          <TabsTrigger value="corrections">{t("run.corrections")}</TabsTrigger>
          <TabsTrigger value="starnet">{t("run.starnet")}</TabsTrigger>
          <TabsTrigger value="diagnostics">{t("run.diagnostics")}</TabsTrigger>
        </TabsList>

        <TabsContent value="network" className="mt-4">
          <Card><CardContent className="pt-4">
            <NetworkMap points={result.points ?? []} sights={sights} height={460} />
          </CardContent></Card>
        </TabsContent>

        <TabsContent value="points" className="mt-4">
          <Card className="overflow-auto">
            <table className="w-full text-[12.5px]">
              <thead>
                <tr className="border-b text-left text-[11px] uppercase tracking-wide text-slate-400">
                  <th className="px-3 py-2 font-medium">Point</th>
                  <th className="px-3 py-2 font-medium">Rôle</th>
                  <th className="px-3 py-2 text-right font-medium">E</th>
                  <th className="px-3 py-2 text-right font-medium">N</th>
                  <th className="px-3 py-2 text-right font-medium">H</th>
                  <th className="px-3 py-2 text-right font-medium">ΔE (mm)</th>
                  <th className="px-3 py-2 text-right font-medium">ΔN (mm)</th>
                  <th className="px-3 py-2 text-right font-medium">ΔH (mm)</th>
                  <th className="px-3 py-2 text-right font-medium">σE</th>
                  <th className="px-3 py-2 text-right font-medium">σN</th>
                  <th className="px-3 py-2 text-right font-medium">σH</th>
                  <th className="px-3 py-2 text-right font-medium">Obs</th>
                </tr>
              </thead>
              <tbody className="font-mono">
                {(result.points ?? []).map((p) => (
                  <tr key={p.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                    <td className="px-3 py-1.5 font-sans font-medium text-slate-700">{p.id}</td>
                    <td className="px-3 py-1.5 font-sans text-slate-500">{p.role}</td>
                    <td className="px-3 py-1.5 text-right">{fmtCoord(p.e)}</td>
                    <td className="px-3 py-1.5 text-right">{fmtCoord(p.n)}</td>
                    <td className="px-3 py-1.5 text-right">{fmtCoord(p.h)}</td>
                    <DeltaCell value={p.delta_e} />
                    <DeltaCell value={p.delta_n} />
                    <DeltaCell value={p.delta_h} />
                    <td className="px-3 py-1.5 text-right text-slate-500">{fmtMm(p.sigma_e, 1)}</td>
                    <td className="px-3 py-1.5 text-right text-slate-500">{fmtMm(p.sigma_n, 1)}</td>
                    <td className="px-3 py-1.5 text-right text-slate-500">{fmtMm(p.sigma_h, 1)}</td>
                    <td className="px-3 py-1.5 text-right text-slate-500">{p.observation_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </TabsContent>

        <TabsContent value="residuals" className="mt-4 space-y-4">
          <Card>
            <CardHeader className="pb-0"><CardTitle className="text-[13.5px]">{t("run.stdRes")} — ±3σ</CardTitle></CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={residualChart} margin={{ left: 0, right: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="id" tick={false} />
                  <YAxis tick={{ fontSize: 10.5 }} stroke="#94a3b8" />
                  <RTooltip contentStyle={{ fontSize: 11.5, borderRadius: 8 }} />
                  <ReferenceLine y={3} stroke="#dc2626" strokeDasharray="4 3" />
                  <ReferenceLine y={-3} stroke="#dc2626" strokeDasharray="4 3" />
                  <Bar dataKey="std" radius={[2, 2, 0, 0]}>
                    {residualChart.map((r, i) => (
                      <Cell key={i} fill={Math.abs(r.std) > 3 ? "#dc2626" : r.kind === "hz" ? "#2563eb" : r.kind === "vz" ? "#059669" : "#d97706"} fillOpacity={0.85} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
          <Card className="max-h-[480px] overflow-auto">
            <table className="w-full text-[12px]">
              <thead className="sticky top-0 bg-white">
                <tr className="border-b text-left text-[11px] uppercase tracking-wide text-slate-400">
                  <th className="px-3 py-2 font-medium">Observation</th>
                  <th className="px-3 py-2 font-medium">Type</th>
                  <th className="px-3 py-2 text-right font-medium">{t("run.stdRes")}</th>
                  <th className="px-3 py-2 text-right font-medium">{t("run.redundancy")}</th>
                  <th className="px-3 py-2 text-right font-medium">σ</th>
                </tr>
              </thead>
              <tbody className="font-mono">
                {[...(result.residuals ?? [])]
                  .sort((a, b) => b.standardized_residual - a.standardized_residual)
                  .map((r) => (
                    <tr key={r.id} className={`border-b border-slate-100 last:border-0 ${r.standardized_residual > 3 ? "bg-red-50/60" : ""}`}>
                      <td className="max-w-[340px] truncate px-3 py-1.5">{r.id}</td>
                      <td className="px-3 py-1.5">{r.kind}</td>
                      <td className={`px-3 py-1.5 text-right font-semibold ${r.standardized_residual > 3 ? "text-red-600" : "text-slate-700"}`}>{r.standardized_residual.toFixed(2)}</td>
                      <td className="px-3 py-1.5 text-right text-slate-500">{r.redundancy.toFixed(2)}</td>
                      <td className="px-3 py-1.5 text-right text-slate-500">{r.kind === "sd" ? fmtMm(r.sigma, 2) : `${(r.sigma * 206265).toFixed(2)}″`}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </Card>
        </TabsContent>

        <TabsContent value="corrections" className="mt-4">
          <Card className="max-h-[560px] overflow-auto">
            <CardHeader className="pb-2">
              <CardTitle className="text-[13.5px]">
                {t("run.formula")}: ppm = 281.8 − 0.29065·P/(1+T/273.15) · {diag.corrections?.count ?? 0} distances · {t("run.source")}: {diag.corrections?.mode}
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <table className="w-full text-[12px]">
                <thead className="sticky top-0 bg-white">
                  <tr className="border-b text-left text-[11px] uppercase tracking-wide text-slate-400">
                    <th className="px-3 py-2 font-medium">{t("common.target")}</th>
                    <th className="px-3 py-2 text-right font-medium">Sd brute</th>
                    <th className="px-3 py-2 text-right font-medium">{t("run.prismDelta")}</th>
                    <th className="px-3 py-2 text-right font-medium">{t("run.ppm")}</th>
                    <th className="px-3 py-2 text-right font-medium">T/P</th>
                    <th className="px-3 py-2 text-right font-medium">{t("run.finalSd")}</th>
                    <th className="px-3 py-2 text-right font-medium">{t("run.source")}</th>
                  </tr>
                </thead>
                <tbody className="font-mono">
                  {(diag.corrections?.traces ?? []).map((c) => (
                    <tr key={c.observation_id} className="border-b border-slate-100 last:border-0">
                      <td className="max-w-[200px] truncate px-3 py-1.5 font-sans text-slate-700">{c.target_name}</td>
                      <td className="px-3 py-1.5 text-right">{c.stored_slope_distance_m.toFixed(4)}</td>
                      <td className={`px-3 py-1.5 text-right ${c.prism_delta_m !== 0 ? "font-semibold text-blue-600" : "text-slate-400"}`}>
                        {c.prism_delta_m !== 0 ? `+${fmtMm(c.prism_delta_m, 1)} mm` : "0"}
                      </td>
                      <td className="px-3 py-1.5 text-right">{c.atmospheric_ppm.toFixed(1)}</td>
                      <td className="px-3 py-1.5 text-right text-slate-500">
                        {c.temperature_c !== null ? `${c.temperature_c.toFixed(1)}°C ${c.pressure_hpa?.toFixed(0)}hPa` : "—"}
                      </td>
                      <td className="px-3 py-1.5 text-right font-semibold">{c.final_slope_distance_m.toFixed(4)}</td>
                      <td className="px-3 py-1.5 text-right font-sans text-slate-500">{c.atmospheric_source}{c.provisional ? " ⚠" : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="starnet" className="mt-4">
          <Card>
            <CardHeader className="flex-row items-center justify-between pb-2">
              <CardTitle className="text-[13.5px]">STAR*NET — dossier temporaire du run (supprimé après ingestion)</CardTitle>
              <div className="flex gap-1">
                {(["dat", "prj", "pts", "err"] as const).map((f) => (
                  <button key={f} onClick={() => setStarnetTab(f)} className={`rounded-md px-2.5 py-1 font-mono text-[11.5px] font-medium ${starnetTab === f ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-500 hover:bg-slate-200"}`}>
                    .{f}
                  </button>
                ))}
              </div>
            </CardHeader>
            <CardContent>
              <pre className="max-h-[520px] overflow-auto rounded-lg bg-slate-900 p-4 font-mono text-[11.5px] leading-relaxed text-slate-100">
                {run.starnet?.[starnetTab] ?? "—"}
              </pre>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="diagnostics" className="mt-4 space-y-4">
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-[13.5px]">{t("run.sourceEpochs")}</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              {syncStations.map((s) => (
                <div key={s.station_code} className="flex items-center gap-3 rounded-lg bg-slate-50 px-3 py-2 text-[12.5px]">
                  <span className="font-mono font-semibold">{s.station_code}</span>
                  <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${s.state === "fresh" ? "bg-emerald-100 text-emerald-700" : s.state === "reused" ? "bg-amber-100 text-amber-700" : "bg-red-100 text-red-700"}`}>
                    {s.state}
                  </span>
                  {s.cycle_epoch && <span className="font-mono text-slate-500">{t("run.cycle")} {fmtSlot(s.cycle_epoch)}</span>}
                  {s.age_minutes !== undefined && s.age_minutes > 0 && <span className="text-slate-400">{t("run.age")} {s.age_minutes.toFixed(0)} min</span>}
                  <span className="ml-auto text-slate-500">
                    {s.target_count ?? 0}/{s.expected_target_count ?? "—"} · {s.availability_percent?.toFixed(0) ?? 0}%
                  </span>
                </div>
              ))}
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-[13.5px]">Initialisation</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-[12.5px]">
              {diag.initialisation?.station_solutions?.map((s) => (
                <div key={s.station_id} className="flex items-center gap-3 rounded-lg bg-slate-50 px-3 py-2">
                  <span className="font-mono font-semibold">{s.station_id}</span>
                  <span className="text-slate-500">{s.method}</span>
                  <span className="text-slate-400">{s.tie_count} ties</span>
                  {s.horizontal_rms_m > 0 && <span className="ml-auto font-mono text-slate-500">RMS {fmtMm(s.horizontal_rms_m, 1)} mm</span>}
                </div>
              ))}
              {diag.initialisation?.coverage && (
                <div className="text-slate-500">
                  {t("wizard.initWindow")}: {fmtSlot(diag.initialisation.coverage.window_from)} → {fmtSlot(diag.initialisation.coverage.window_to)} ·{" "}
                  {diag.initialisation.coverage.available_station_target_pairs}/{diag.initialisation.coverage.expected_station_target_pairs} couples station/cible
                </div>
              )}
              {(diag.initialisation?.failures ?? []).map((f) => (
                <div key={f.station_id} className="rounded-lg bg-red-50 px-3 py-2 text-red-700">{f.station_id}: {f.reason}</div>
              ))}
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-[13.5px]">{t("run.stationOrientations")}</CardTitle></CardHeader>
            <CardContent className="space-y-1 font-mono text-[12.5px]">
              {(result.orientations ?? []).map((o) => (
                <div key={o.station_id} className="flex gap-3">
                  <span className="font-semibold">{o.station_id}</span>
                  <span>{((o.value_rad * 180) / Math.PI).toFixed(5)}°</span>
                  <span className="text-slate-400">σ {(o.sigma_rad * 206265).toFixed(1)}″</span>
                  {o.fixed && <span className="text-slate-400">(fixe)</span>}
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function Kpi({ label, value, tone }: { label: string; value: string; tone?: "ok" | "ko" | "warn" }) {
  const color = tone === "ok" ? "text-emerald-600" : tone === "ko" ? "text-red-600" : tone === "warn" ? "text-amber-600" : "text-slate-900";
  return (
    <Card className="px-3.5 py-3">
      <div className="text-[10.5px] font-medium uppercase tracking-wide text-slate-400">{label}</div>
      <div className={`mt-0.5 font-mono text-[15px] font-semibold ${color}`}>{value}</div>
    </Card>
  );
}

function DeltaCell({ value }: { value?: number }) {
  if (value === undefined) return <td className="px-3 py-1.5 text-right text-slate-300">—</td>;
  const mm = value * 1000;
  const color = Math.abs(mm) > 3 ? "font-semibold text-amber-600" : "text-slate-600";
  return <td className={`px-3 py-1.5 text-right ${color}`}>{mm.toFixed(2)}</td>;
}
