import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const RUN_STYLES: Record<string, string> = {
  success: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  provisional: "bg-amber-50 text-amber-700 ring-amber-600/25",
  failed: "bg-red-50 text-red-700 ring-red-600/20",
};

const CHI_STYLES: Record<string, string> = {
  passed: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  failed: "bg-red-50 text-red-700 ring-red-600/20",
  "not-applicable": "bg-slate-100 text-slate-600 ring-slate-500/20",
};

const VERSION_STYLES: Record<string, string> = {
  active: "bg-blue-50 text-blue-700 ring-blue-600/20",
  draft: "bg-violet-50 text-violet-700 ring-violet-600/20",
  inactive: "bg-slate-100 text-slate-600 ring-slate-500/20",
  archived: "bg-slate-100 text-slate-400 ring-slate-500/15",
};

function Badge({ value, styles, label }: { value: string; styles: Record<string, string>; label: string }) {
  return (
    <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset", styles[value] ?? "bg-slate-100 text-slate-600 ring-slate-500/20")}>
      {label}
    </span>
  );
}

export function RunStatusBadge({ status }: { status: string }) {
  const { t } = useI18n();
  const key = status === "success" ? "status.success" : status === "provisional" ? "status.provisional" : "status.failed";
  return <Badge value={status} styles={RUN_STYLES} label={t(key)} />;
}

export function ChiBadge({ status }: { status: string }) {
  const { t } = useI18n();
  const key = status === "passed" ? "status.passed" : status === "failed" ? "status.chi_failed" : "status.not-applicable";
  return <Badge value={status} styles={CHI_STYLES} label={t(key)} />;
}

export function VersionBadge({ status }: { status: string }) {
  const { t } = useI18n();
  const key = `status.${status}` as const;
  return <Badge value={status} styles={VERSION_STYLES} label={t(key as never)} />;
}

export function KindBadge({ kind }: { kind: string }) {
  const { t } = useI18n();
  return (
    <span className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600 ring-1 ring-inset ring-slate-500/20">
      {kind === "network" ? t("processings.kind.network") : t("processings.kind.single")}
    </span>
  );
}
