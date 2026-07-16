import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { AuditEvent } from "@/lib/types";
import { Card } from "@/components/ui/card";

export function AuditPage() {
  const { t } = useI18n();
  const [events, setEvents] = useState<AuditEvent[]>([]);

  useEffect(() => {
    api.audit().then(setEvents).catch(() => undefined);
  }, []);

  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="mb-4 text-xl font-semibold text-slate-900">{t("audit.title")}</h1>
      <Card>
        <table className="w-full text-[12.5px]">
          <thead>
            <tr className="border-b text-left text-[11px] uppercase tracking-wide text-slate-400">
              <th className="px-4 py-2.5 font-medium">Timestamp</th>
              <th className="px-4 py-2.5 font-medium">Type</th>
              <th className="px-4 py-2.5 font-medium">Message</th>
            </tr>
          </thead>
          <tbody>
            {events.map((e) => (
              <tr key={e.id} className="border-b border-slate-100 last:border-0">
                <td className="whitespace-nowrap px-4 py-2 font-mono text-[11.5px] text-slate-500">{e.ts.slice(0, 19).replace("T", " ")}</td>
                <td className="px-4 py-2"><span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-600">{e.kind}</span></td>
                <td className="px-4 py-2 text-slate-700">{e.message}</td>
              </tr>
            ))}
            {events.length === 0 && <tr><td colSpan={3} className="px-4 py-8 text-center text-slate-400">{t("audit.empty")}</td></tr>}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
