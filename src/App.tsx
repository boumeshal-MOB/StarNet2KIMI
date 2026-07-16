import { Route, Routes } from "react-router-dom";
import { I18nProvider } from "@/lib/i18n";
import { AppLayout } from "@/components/layout/AppLayout";
import { ProcessingsPage } from "@/pages/ProcessingsPage";
import { ProcessingDetailPage } from "@/pages/ProcessingDetailPage";
import { RunDetailPage } from "@/pages/RunDetailPage";
import { AnalysisLabPage } from "@/pages/AnalysisLabPage";
import { WizardPage } from "@/pages/wizard/WizardPage";
import { DemoPage } from "@/pages/DemoPage";
import { AuditPage } from "@/pages/AuditPage";

export default function App() {
  return (
    <I18nProvider>
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/" element={<ProcessingsPage />} />
          <Route path="/processings/new" element={<WizardPage />} />
          <Route path="/processings/:id" element={<ProcessingDetailPage />} />
          <Route path="/processings/:id/analysis" element={<AnalysisLabPage />} />
          <Route path="/runs/:id" element={<RunDetailPage />} />
          <Route path="/analysis" element={<AnalysisLabPage />} />
          <Route path="/demo" element={<DemoPage />} />
          <Route path="/audit" element={<AuditPage />} />
        </Route>
      </Routes>
    </I18nProvider>
  );
}
