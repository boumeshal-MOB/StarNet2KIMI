import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ChevronRight, Plus } from "lucide-react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { fmtSlot } from "@/lib/format";
import type { ProcessingSummary } from "@/lib/types";
import { ChiBadge, KindBadge, RunStatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

export function ProcessingsPage() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [items, setItems] = useState<ProcessingSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.processings().then(setItems).catch((e) => setError(String(e.message ?? e)));
  }, []);

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">{t("processings.title")}</h1>
          <p className="mt-0.5 text-[13px] text-slate-500">{t("processings.subtitle")}</p>
        </div>
        <Button onClick={() => navigate("/processings/new")} className="gap-1.5">
          <Plus className="h-4 w-4" /> {t("processings.new")}
        </Button>
      </div>

      {error && <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</div>}
      {!items && !error && <div className="text-sm text-slate-400">{t("common.loading")}</div>}
      {items && items.length === 0 && (
        <Card className="p-10 text-center text-sm text-slate-500">{t("processings.empty")}</Card>
      )}

      <div className="grid gap-3">
        {items?.map((p) => (
          <Link key={p.id} to={`/processings/${p.id}`}>
            <Card className="group grid grid-cols-[1fr_auto] items-center gap-5 px-5 py-4 transition-shadow hover:shadow-md">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2.5">
                  <span className="truncate text-[15px] font-semibold text-slate-900">{p.name}</span>
                  <KindBadge kind={p.kind} />
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium uppercase text-slate-500 ring-1 ring-inset ring-slate-500/20">
                    {p.template}
                  </span>
                </div>
                <div className="mt-1 truncate text-[12.5px] text-slate-500">{p.description}</div>
                <div className="mt-2 flex items-center gap-4 text-[12px] text-slate-400">
                  <span>{p.version_count} {t("processings.versions")}</span>
                  <span>{p.run_count} {t("processings.runs")}</span>
                  {p.active_version && <span>v{p.active_version.number} · {t("status.active").toLowerCase()}</span>}
                </div>
              </div>
              <div className="flex items-center gap-3">
                {p.last_run ? (
                  <div className="text-right">
                    <div className="mb-1 flex items-center justify-end gap-1.5">
                      <RunStatusBadge status={p.last_run.status} />
                      <ChiBadge status={p.last_run.chi_square_status} />
                    </div>
                    <div className="text-[11.5px] text-slate-400">
                      {t("processings.lastrun")} · {fmtSlot(p.last_run.slot)}
                    </div>
                  </div>
                ) : (
                  <span className="text-[12px] text-slate-400">{t("detail.noRuns")}</span>
                )}
                <ChevronRight className="h-4 w-4 text-slate-300 transition-transform group-hover:translate-x-0.5" />
              </div>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
