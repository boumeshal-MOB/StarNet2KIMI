import { useEffect, useState } from "react";
import { Database, PackageOpen, RotateCcw } from "lucide-react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface DemoState {
  late_data: { delivered: boolean; cycle: string; count: number } | null;
  stats: Record<string, number>;
}

export function DemoPage() {
  const { t } = useI18n();
  const [state, setState] = useState<DemoState | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  function refresh() {
    api.demoState().then(setState).catch(() => undefined);
  }
  useEffect(refresh, []);

  async function reset() {
    setBusy(true);
    setMessage(null);
    try {
      await api.demoReset();
      setMessage("✓ Reset");
      refresh();
    } finally {
      setBusy(false);
    }
  }

  async function deliverLate() {
    setBusy(true);
    setMessage(null);
    try {
      const result = await api.demoDeliverLate();
      if (result.delivered) {
        const slots = result.catch_up.map((c) => `${c.slot.slice(11, 16)} → ${c.status}`).join(", ");
        setMessage(`✓ ${result.cycle} — ${t("demo.catchup")}: ${slots || "—"}`);
      } else {
        setMessage(t("demo.delivered"));
      }
      refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <h1 className="text-xl font-semibold text-slate-900">{t("demo.title")}</h1>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-[14px]"><Database className="h-4 w-4" /> {t("demo.state")}</CardTitle>
        </CardHeader>
        <CardContent>
          {state && (
            <div className="grid grid-cols-3 gap-3 text-center lg:grid-cols-6">
              {Object.entries(state.stats).map(([key, value]) => (
                <div key={key} className="rounded-lg bg-slate-50 px-2 py-3">
                  <div className="font-mono text-lg font-semibold text-slate-800">{value}</div>
                  <div className="text-[10.5px] uppercase tracking-wide text-slate-400">{key.replace(/_/g, " ")}</div>
                </div>
              ))}
            </div>
          )}
          {state?.late_data && (
            <div className="mt-3 flex items-center gap-3 rounded-lg bg-slate-50 px-3 py-2.5 text-[13px]">
              <span className={`h-2.5 w-2.5 rounded-full ${state.late_data.delivered ? "bg-emerald-500" : "bg-amber-500"}`} />
              <span className="font-mono text-[12.5px]">{state.late_data.cycle}</span>
              <span className="text-slate-500">{state.late_data.count} {t("misc.observations")}</span>
              <span className="ml-auto text-[12px] font-medium text-slate-500">
                {state.late_data.delivered ? t("demo.delivered") : t("demo.pending")}
              </span>
            </div>
          )}
          <div className="mt-4 flex gap-2">
            <Button variant="outline" onClick={deliverLate} disabled={busy || (state?.late_data?.delivered ?? false)} className="gap-1.5">
              <PackageOpen className="h-4 w-4" /> {t("demo.deliverLate")}
            </Button>
            <Button variant="outline" onClick={reset} disabled={busy} className="gap-1.5 text-red-600 hover:text-red-700">
              <RotateCcw className="h-4 w-4" /> {t("demo.reset")}
            </Button>
          </div>
          {message && <div className="mt-3 rounded-lg bg-emerald-50 px-3 py-2 font-mono text-[12.5px] text-emerald-700">{message}</div>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-[14px]">{t("demo.guide")}</CardTitle></CardHeader>
        <CardContent className="space-y-2 text-[13px] text-slate-600">
          {(["demo.scenario1", "demo.scenario2", "demo.scenario3", "demo.scenario4", "demo.scenario5", "demo.scenario6"] as const).map((key) => (
            <p key={key}>{t(key)}</p>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
