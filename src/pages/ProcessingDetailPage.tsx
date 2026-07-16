import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { FlaskConical, Play, RefreshCcw } from "lucide-react";
import { Line, LineChart, CartesianGrid, XAxis, YAxis, Tooltip as RTooltip, ResponsiveContainer } from "recharts";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { fmtDuration, fmtSlot } from "@/lib/format";
import type { ProcessingSummary, RunDetail, RunSummary } from "@/lib/types";
import { ChiBadge, RunStatusBadge, VersionBadge } from "@/components/StatusBadge";
import { NetworkMap } from "@/components/NetworkMap";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

const COMPONENTS = ["DZ", "DX", "DY", "X", "Y", "Z", "SX", "SY", "SZ"];

export function ProcessingDetailPage() {
  const { id } = useParams();
  const processingId = Number(id);
  const { t } = useI18n();
  const navigate = useNavigate();
  const [processing, setProcessing] = useState<ProcessingSummary | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [lastRunDetail, setLastRunDetail] = useState<RunDetail | null>(null);
  const [component, setComponent] = useState("DZ");
  const [series, setSeries] = useState<Record<string, { slot: string; value: number }[]>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reprocessOpen, setReprocessOpen] = useState(false);
  const [range, setRange] = useState({ from: "2025-03-09T00:00:00.000Z", to: "2025-03-09T20:00:00.000Z" });
  const [reprocessResult, setReprocessResult] = useState<string | null>(null);
  const [compare, setCompare] = useState<{ a: number; b: number; diff: { path: string; from: unknown; to: unknown }[] } | null>(null);

  const refresh = useCallback(() => {
    api.processing(processingId).then(setProcessing).catch((e) => setError(String(e.message ?? e)));
    api.runs(processingId).then(setRuns).catch(() => undefined);
  }, [processingId]);

  useEffect(refresh, [refresh]);

  useEffect(() => {
    if (runs.length > 0) {
      api.runDetail(runs[0].id).then(setLastRunDetail).catch(() => setLastRunDetail(null));
    }
  }, [runs]);

  useEffect(() => {
    api.outputs(processingId, component).then((r) => setSeries(r.series)).catch(() => setSeries({}));
  }, [processingId, component, runs]);

  const chartData = useMemo(() => {
    const slots = new Set<string>();
    Object.values(series).forEach((rows) => rows.forEach((r) => slots.add(r.slot)));
    return [...slots].sort().map((slot) => {
      const row: Record<string, unknown> = { slot: slot.slice(5, 16) };
      for (const [point, rows] of Object.entries(series)) {
        const found = rows.find((r) => r.slot === slot);
        if (found) row[point] = Math.round(found.value * 1e6) / 1e3; // m → mm
      }
      return row;
    });
  }, [series]);

  const chartPoints = useMemo(() => Object.keys(series).slice(0, 12), [series]);

  async function runNow() {
    setBusy(true);
    setError(null);
    try {
      const run = await api.run(processingId);
      navigate(`/runs/${run.id}`);
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  }

  async function doReprocess() {
    setBusy(true);
    setReprocessResult(null);
    try {
      const result = await api.reprocess(processingId, range.from, range.to);
      setReprocessResult(`${result.slots} slots — ${result.results.filter((r) => r.status === "success").length} succès / ${result.results.filter((r) => r.status === "provisional").length} provisoires / ${result.results.filter((r) => r.status === "failed").length} échecs`);
      refresh();
    } catch (e) {
      setReprocessResult(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  }

  if (!processing) {
    return <div className="text-sm text-slate-400">{error ?? t("common.loading")}</div>;
  }

  const payload = processing.active_version?.payload;
  const sharedCount = payload ? new Set(payload.targets.map((x) => x.physical_point_id)).size : 0;

  return (
    <div className="mx-auto max-w-7xl">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-[12px] text-slate-400">
            <Link to="/" className="hover:text-slate-600">{t("processings.title")}</Link>
            <span>/</span>
            <span className="text-slate-600">#{processing.id}</span>
          </div>
          <h1 className="mt-1 text-xl font-semibold text-slate-900">{processing.name}</h1>
          <p className="mt-0.5 max-w-3xl text-[13px] text-slate-500">{processing.description}</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setReprocessOpen(true)} className="gap-1.5">
            <RefreshCcw className="h-4 w-4" /> {t("detail.reprocess")}
          </Button>
          <Button variant="outline" onClick={() => navigate(`/processings/${processing.id}/analysis`)} className="gap-1.5">
            <FlaskConical className="h-4 w-4" /> {t("detail.analysis")}
          </Button>
          <Button onClick={runNow} disabled={busy} className="gap-1.5">
            <Play className="h-4 w-4" /> {t("detail.runNow")}
          </Button>
        </div>
      </div>
      {error && <div className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</div>}

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">{t("detail.overview")}</TabsTrigger>
          <TabsTrigger value="runs">{t("detail.runs")} ({runs.length})</TabsTrigger>
          <TabsTrigger value="outputs">{t("detail.outputs")}</TabsTrigger>
          <TabsTrigger value="versions">{t("detail.versions")} ({processing.version_count})</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-4 space-y-4">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Stat label={t("detail.activeVersion")} value={processing.active_version ? `v${processing.active_version.number}` : "—"} sub={processing.active_version ? `${t("detail.validFrom")} ${fmtSlot(processing.active_version.valid_from)}` : undefined} />
            <Stat label={t("common.stations")} value={String(payload?.stations.length ?? 0)} sub={payload?.stations.map((s) => s.code).join(" · ")} />
            <Stat label={t("common.targets")} value={String(payload?.targets.length ?? 0)} sub={`${sharedCount} points physiques`} />
            <Stat label="Grille de publication" value={payload ? `${payload.output.grid_minutes} min` : "—"} sub={`Trigger: ${payload?.run.trigger ?? "—"}`} />
          </div>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-[14px]">{t("run.network")} — {lastRunDetail ? fmtSlot(lastRunDetail.slot) : ""}</CardTitle>
            </CardHeader>
            <CardContent>
              {lastRunDetail?.result?.points ? (
                <NetworkMap
                  points={lastRunDetail.result.points}
                  sights={(lastRunDetail.result.residuals ?? [])
                    .filter((r) => r.kind === "sd" && r.station_id)
                    .map((r) => ({ station_id: r.station_id, target_id: r.target_id }))}
                />
              ) : (
                <div className="py-8 text-center text-sm text-slate-400">{t("detail.noRuns")}</div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="runs" className="mt-4">
          <Card>
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b text-left text-[11.5px] uppercase tracking-wide text-slate-400">
                  <th className="px-4 py-2.5 font-medium">{t("common.slot")}</th>
                  <th className="px-4 py-2.5 font-medium">Trigger</th>
                  <th className="px-4 py-2.5 font-medium">{t("common.status")}</th>
                  <th className="px-4 py-2.5 font-medium">χ²</th>
                  <th className="px-4 py-2.5 font-medium">{t("common.version")}</th>
                  <th className="px-4 py-2.5 text-right font-medium">Durée</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.id} className="cursor-pointer border-b border-slate-100 last:border-0 hover:bg-slate-50" onClick={() => navigate(`/runs/${run.id}`)}>
                    <td className="px-4 py-2.5 font-mono text-[12.5px]">{fmtSlot(run.slot)}</td>
                    <td className="px-4 py-2.5 text-slate-500">{run.trigger}</td>
                    <td className="px-4 py-2.5"><RunStatusBadge status={run.status} /></td>
                    <td className="px-4 py-2.5"><ChiBadge status={run.chi_square_status} /></td>
                    <td className="px-4 py-2.5 text-slate-500">v{processing.versions?.find((v) => v.id === run.version_id)?.number ?? "?"}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-[12px] text-slate-500">{fmtDuration(run.duration_ms)}</td>
                  </tr>
                ))}
                {runs.length === 0 && (
                  <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-400">{t("detail.noRuns")}</td></tr>
                )}
              </tbody>
            </table>
          </Card>
        </TabsContent>

        <TabsContent value="outputs" className="mt-4">
          <Card>
            <CardHeader className="flex-row items-center justify-between pb-2">
              <CardTitle className="text-[14px]">{t("detail.outputs")} — {component} (mm)</CardTitle>
              <div className="flex gap-1">
                {COMPONENTS.map((c) => (
                  <button key={c} onClick={() => setComponent(c)} className={`rounded-md px-2 py-1 text-[11.5px] font-medium ${c === component ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-500 hover:bg-slate-200"}`}>
                    {c}
                  </button>
                ))}
              </div>
            </CardHeader>
            <CardContent>
              {chartData.length === 0 ? (
                <div className="py-8 text-center text-sm text-slate-400">{t("detail.noRuns")}</div>
              ) : (
                <ResponsiveContainer width="100%" height={360}>
                  <LineChart data={chartData} margin={{ left: 8, right: 16, top: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="slot" tick={{ fontSize: 10.5 }} stroke="#94a3b8" />
                    <YAxis tick={{ fontSize: 10.5 }} stroke="#94a3b8" tickFormatter={(v) => `${v}`} />
                    <RTooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} formatter={(v: number) => [`${v.toFixed(2)} mm`]} />
                    {chartPoints.map((point, i) => (
                      <Line key={point} type="monotone" dataKey={point} dot={{ r: 2 }} strokeWidth={1.6}
                        stroke={["#2563eb", "#059669", "#d97706", "#dc2626", "#7c3aed", "#0891b2", "#be185d", "#65a30d", "#ea580c", "#4f46e5", "#0d9488", "#a16207"][i % 12]} />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="versions" className="mt-4 space-y-3">
          {processing.versions?.map((version) => (
            <Card key={version.id} className="flex items-center gap-4 px-5 py-3.5">
              <span className="text-[15px] font-semibold text-slate-800">v{version.number}</span>
              <VersionBadge status={version.status} />
              <span className="text-[12px] text-slate-400">{version.origin}</span>
              <span className="text-[12.5px] text-slate-500">
                {t("detail.validFrom")} {fmtSlot(version.valid_from)} {t("detail.validTo")} {version.valid_to ? fmtSlot(version.valid_to) : t("detail.openEnded")}
              </span>
              <div className="ml-auto flex gap-2">
                {processing.versions && processing.versions.length > 1 && (
                  <Button
                    variant="ghost" size="sm"
                    onClick={async () => {
                      const other = processing.versions!.find((v) => v.id !== version.id)!;
                      setCompare(await api.compareVersions(processing.id, other.id, version.id));
                    }}
                  >
                    {t("detail.compare")}
                  </Button>
                )}
                {version.status !== "active" && version.status !== "archived" && (
                  <Button variant="outline" size="sm" onClick={async () => { await api.activateVersion(processing.id, version.id); refresh(); }}>
                    {t("detail.activate")}
                  </Button>
                )}
                {version.status !== "archived" && version.status !== "active" && (
                  <Button variant="ghost" size="sm" onClick={async () => { await api.archiveVersion(processing.id, version.id); refresh(); }}>
                    {t("detail.archive")}
                  </Button>
                )}
                <Button variant="outline" size="sm" onClick={async () => { await api.createDraft(processing.id, version.id); refresh(); }}>
                  {t("detail.newDraft")}
                </Button>
              </div>
            </Card>
          ))}
        </TabsContent>
      </Tabs>

      <Dialog open={reprocessOpen} onOpenChange={setReprocessOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>{t("detail.reprocess")}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <label className="block text-[12.5px] font-medium text-slate-600">{t("detail.from")}
              <Input value={range.from} onChange={(e) => setRange({ ...range, from: e.target.value })} className="mt-1 font-mono text-[12.5px]" />
            </label>
            <label className="block text-[12.5px] font-medium text-slate-600">{t("detail.to")}
              <Input value={range.to} onChange={(e) => setRange({ ...range, to: e.target.value })} className="mt-1 font-mono text-[12.5px]" />
            </label>
            <p className="text-[12px] text-slate-400">Chaque slot utilise la version valide à sa date. Les valeurs existantes sont remplacées.</p>
            {reprocessResult && <div className="rounded-lg bg-slate-50 p-2.5 text-[12.5px] text-slate-600">{reprocessResult}</div>}
            <Button onClick={doReprocess} disabled={busy} className="w-full">{busy ? t("common.loading") : t("common.run")}</Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={compare !== null} onOpenChange={() => setCompare(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader><DialogTitle>{t("detail.compare")} — v{compare?.a} vs v{compare?.b}</DialogTitle></DialogHeader>
          <div className="max-h-96 overflow-auto">
            {compare?.diff.length === 0 && <p className="text-sm text-slate-500">Aucune différence.</p>}
            {compare?.diff.map((d, i) => (
              <div key={i} className="border-b border-slate-100 py-1.5 font-mono text-[11.5px]">
                <span className="text-slate-500">{d.path}</span>
                <div><span className="text-red-500 line-through">{JSON.stringify(d.from)}</span> → <span className="text-emerald-600">{JSON.stringify(d.to)}</span></div>
              </div>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card className="px-4 py-3.5">
      <div className="text-[11.5px] font-medium uppercase tracking-wide text-slate-400">{label}</div>
      <div className="mt-1 text-lg font-semibold text-slate-900">{value}</div>
      {sub && <div className="mt-0.5 truncate text-[11.5px] text-slate-400">{sub}</div>}
    </Card>
  );
}
