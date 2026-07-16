import { NavLink, Outlet } from "react-router-dom";
import { Activity, FlaskConical, Globe2, LayoutList, Plus, Database, ScrollText } from "lucide-react";
import { useI18n } from "@/lib/i18n";

export function AppLayout() {
  const { lang, setLang, t } = useI18n();
  const link = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-2.5 rounded-md px-3 py-2 text-[13px] font-medium transition-colors ${
      isActive ? "bg-slate-800 text-white" : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
    }`;

  return (
    <div className="flex min-h-screen bg-slate-100">
      <aside className="fixed inset-y-0 left-0 z-30 flex w-60 flex-col bg-slate-900 px-3 py-5">
        <div className="mb-8 flex items-center gap-2.5 px-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600">
            <Activity className="h-4.5 w-4.5 text-white" strokeWidth={2.2} />
          </div>
          <div>
            <div className="text-[13px] font-semibold leading-tight text-white">{t("app.title")}</div>
            <div className="text-[10px] leading-tight text-slate-500">{t("app.subtitle")}</div>
          </div>
        </div>
        <nav className="flex flex-col gap-1">
          <NavLink to="/" end className={link}>
            <LayoutList className="h-4 w-4" />
            {t("nav.processings")}
          </NavLink>
          <NavLink to="/processings/new" className={link}>
            <Plus className="h-4 w-4" />
            {t("nav.create")}
          </NavLink>
          <NavLink to="/analysis" className={link}>
            <FlaskConical className="h-4 w-4" />
            Analysis Lab
          </NavLink>
          <NavLink to="/demo" className={link}>
            <Database className="h-4 w-4" />
            {t("nav.demo")}
          </NavLink>
          <NavLink to="/audit" className={link}>
            <ScrollText className="h-4 w-4" />
            {t("nav.audit")}
          </NavLink>
        </nav>
        <div className="mt-auto space-y-3">
          <div className="rounded-lg bg-slate-800/60 p-3 text-[10.5px] leading-relaxed text-slate-400">
            <span className="mb-1 block font-semibold text-slate-300">{t("nav.engine")} · python-lsq-v1</span>
            {t("misc.engineNote")}
          </div>
          <button
            onClick={() => setLang(lang === "fr" ? "en" : "fr")}
            className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-[12px] font-medium text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
          >
            <Globe2 className="h-4 w-4" />
            {lang === "fr" ? "Français" : "English"}
            <span className="ml-auto rounded bg-slate-700 px-1.5 py-0.5 text-[10px] uppercase text-slate-300">{lang}</span>
          </button>
        </div>
      </aside>
      <main className="ml-60 flex-1 px-8 py-7">
        <Outlet />
      </main>
    </div>
  );
}
