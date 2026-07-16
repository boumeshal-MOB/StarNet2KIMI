import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { FlaskConical, Save } from "lucide-react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { fmtSlot } from "@/lib/format";
import type { ProcessingSummary, RunDetail } from "@/lib/types";
import { ChiBadge, RunStatusBadge } from "@/components/StatusBadge";
import { NetworkMap } from "@/components/NetworkMap";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export function AnalysisLabPage() {
  const { id } = useParams();
  const { t } = useI18n();
  const navigate = useNavigate();
  const [processings, setProcessings] = useState<ProcessingSummary[]>([]);
  const [processingId, setProcessingId] = useState<number | null>(id ? Number(id) : null);
  const [slot, setSlot] = useState("2025-03-09T16:00:00.000Z");
  const [weights, setWeights] = useState({ direction_arcsec: 3.0, zenith_arcsec: 3.5, distance_mm: 2.0, distance_ppm: 2.0 });
  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  const [autoAdjust, setAutoAdjust] = useState(true);
  const [result, setResult] = useState<RunDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  useEffect(() => {
    api.processings().then((items) => {
      setProcessings(items);
      if (!processingId && items.length > 0) setProcessingId(items[0].id);
    });
  }, []);

  const processing = processings.find((p) => p.id === processingId) ?? null;
  const residualRows = useMemo(() => {
    if (!result?.result?.residuals) return [];
    return [...result.result.residuals]
      .filter((r) => r.kind !== "constraint")
      .sort((a, b) => b.standardized_residual - a.standardized_residual)
      .slice(0, 40);
  }, [result]);

  async function runTrial(newExcluded?: Set<string>) {
    if (!processingId) return;
    setBusy(true);
    setError(null);
    setSaved(null);
    const ex = newExcluded ?? excluded;
    try {
      const trial = await api.analysisTrial({
        processing_id: processingId,
        slot,
        overrides: {
          default_weights: weights,
          excluded_observation_ids: [...ex],
          adjustment: { auto_adjust: { enabled: autoAdjust, max_iterations: 5, max_standardized_residual: 3.0 } },
        },
      });
      setResult(trial);
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  }

  function toggleExclusion(rawId: string) {
    const next = new Set(excluded);
    if (next.has(rawId)) next.delete(rawId);
    else next.add(rawId);
    setExcluded(next);
    runTrial(next);
  }

  async function saveDraft() {
    if (!processing?.active_version) return;
    setBusy(true);
    try {
      const payload = JSON.parse(JSON.stringify(processing.active_version.payload));
      payload.default_weights = { ...weights };
      payload.adjustment.auto_adjust.enabled = autoAdjust;
      const draft = await api.analysisSaveDraft({
        processing_id: processing.id,
        base_version_id: processing.active_version.id,
        payload,
        note: `Analysis Lab ${slot}`,
      });
      setSaved(`v${draft.number}`);
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  }

  const res = result?.result;

  return (
    <div className="mx-auto max-w-7xl">
      <div className="mb-5">
        <h1 className="flex items-center gap-2 text-xl font-semibold text-slate-900">
          <FlaskConical className="h-5 w-5 text-violet-600" /> {t("lab.title")}
        </h1>
        <p className="mt-0.5 text-[13px] text-slate-500">{t("lab.subtitle")}</p>
      </div>

      <Card className="mb-4">
        <CardContent className="flex flex-wrap items-end gap-3 pt-4">
          {!id && (
            <label className="text-[12px] font-medium text-slate-600">
              Processing
              <Select value={processingId ? String(processingId) : undefined} onValueChange={(v) => { setProcessingId(Number(v)); setResult(null); }}>
                <SelectTrigger className="mt-1 w-72"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {processings.map((p) => <SelectItem key={p.id} value={String(p.id)}>{p.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </label>
          )}
          <label className="text-[12px] font-medium text-slate-600">
            {t("lab.slot")}
            <Input value={slot} onChange={(e) => setSlot(e.target.value)} className="mt-1 w-64 font-mono text-[12.5px]" />
          </label>
          {(
            [
              ["direction_arcsec", t("lab.direction")],
              ["zenith_arcsec", t("lab.zenith")],
              ["distance_mm", t("lab.distMm")],
              ["distance_ppm", t("lab.distPpm")],
            ] as const
          ).map(([key, label]) => (
            <label key={key} className="text-[12px] font-medium text-slate-600">
              {label}
              <Input
                type="number" step="0.1" min="0.1" value={weights[key]}
                onChange={(e) => setWeights({ ...weights, [key]: Number(e.target.value) })}
                className="mt-1 w-24 font-mono text-[12.5px]"
              />
            </label>
          ))}
          <label className="flex items-center gap-2 text-[12.5px] font-medium text-slate-600">
            <input type="checkbox" checked={autoAdjust} onChange={(e) => setAutoAdjust(e.target.checked)} className="h-4 w-4 rounded border-slate-300" />
            {t("run.autoAdjust")}
          </label>
          <Button onClick={() => runTrial()} disabled={busy || !processingId} className="gap-1.5">
            {busy ? t("lab.running") : t("lab.run")}
          </Button>
          {result && processing?.active_version && (
            <Button variant="outline" onClick={saveDraft} disabled={busy} className="gap-1.5">
              <Save className="h-4 w-4" /> {t("lab.saveDraft")}
            </Button>
          )}
          {saved && (
            <span className="text-[12.5px] font-medium text-emerald-600">
              {t("lab.saved")} {saved} — <button className="underline" onClick={() => navigate(`/processings/${processingId}`)}>{t("detail.versions")}</button>
            </span>
          )}
        </CardContent>
      </Card>
      {error && <div className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</div>}

      {result && res && (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <RunStatusBadge status={result.status} />
            <ChiBadge status={result.chi_square_status} />
            <span className="font-mono text-[12.5px] text-slate-500">
              vf {Number.isFinite(res.variance_factor) ? res.variance_factor!.toFixed(3) : "—"} · {t("run.dof")} {res.degrees_of_freedom} ·{" "}
              {t("run.rank")} {res.rank}/{res.unknown_count ?? res.rank} · {t("run.maxStdRes")} {res.max_standardized_residual?.toFixed(2)}
            </span>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-[13.5px]">{t("run.network")}</CardTitle></CardHeader>
              <CardContent>
                <NetworkMap
                  points={res.points ?? []}
                  sights={(res.residuals ?? []).filter((r) => r.kind === "sd" && r.station_id).map((r) => ({ station_id: r.station_id, target_id: r.target_id }))}
                  height={380}
                />
              </CardContent>
            </Card>
            <Card className="max-h-[480px] overflow-auto">
              <CardHeader className="pb-2">
                <CardTitle className="text-[13.5px]">{t("run.residuals")} — {t("lab.exclusions").toLowerCase()}</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <table className="w-full text-[11.5px]">
                  <thead className="sticky top-0 bg-white">
                    <tr className="border-b text-left text-[10.5px] uppercase text-slate-400">
                      <th className="px-3 py-1.5 font-medium">Observation</th>
                      <th className="px-2 py-1.5 text-right font-medium">{t("run.stdRes")}</th>
                      <th className="px-2 py-1.5 text-right font-medium">{t("run.redundancy")}</th>
                      <th className="px-2 py-1.5" />
                    </tr>
                  </thead>
                  <tbody className="font-mono">
                    {residualRows.map((r) => {
                      const isExcluded = excluded.has(r.raw_observation_id);
                      return (
                        <tr key={r.id} className={`border-b border-slate-100 ${isExcluded ? "opacity-40 line-through" : r.standardized_residual > 3 ? "bg-red-50/50" : ""}`}>
                          <td className="max-w-[220px] truncate px-3 py-1.5">{r.id}</td>
                          <td className={`px-2 py-1.5 text-right font-semibold ${r.standardized_residual > 3 ? "text-red-600" : ""}`}>{r.standardized_residual.toFixed(2)}</td>
                          <td className="px-2 py-1.5 text-right text-slate-500">{r.redundancy.toFixed(2)}</td>
                          <td className="px-2 py-1.5 text-right">
                            <button onClick={() => toggleExclusion(r.raw_observation_id)} className="rounded bg-slate-100 px-1.5 py-0.5 font-sans text-[10.5px] text-slate-600 hover:bg-slate-200">
                              {isExcluded ? t("lab.include") : t("lab.exclude")}
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          </div>
        </>
      )}
      {!result && !busy && (
        <Card className="p-10 text-center text-sm text-slate-400">
          {t("lab.slot")} — {fmtSlot(slot)}
        </Card>
      )}
    </div>
  );
}
