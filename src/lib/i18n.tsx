import { createContext, useContext, useState, type ReactNode } from "react";

export type Lang = "fr" | "en";

const dict = {
  // App shell
  "app.title": { fr: "Topographic Adjustment", en: "Topographic Adjustment" },
  "app.subtitle": { fr: "BlueTrust Monitoring — maquette", en: "BlueTrust Monitoring — mock-up" },
  "nav.processings": { fr: "Processings", en: "Processings" },
  "nav.create": { fr: "Nouveau processing", en: "New processing" },
  "nav.demo": { fr: "Données démo", en: "Demo data" },
  "nav.audit": { fr: "Journal", en: "Audit log" },
  "nav.engine": { fr: "Moteur Python", en: "Python engine" },

  // Common
  "common.loading": { fr: "Chargement…", en: "Loading…" },
  "common.save": { fr: "Enregistrer", en: "Save" },
  "common.cancel": { fr: "Annuler", en: "Cancel" },
  "common.back": { fr: "Retour", en: "Back" },
  "common.next": { fr: "Suivant", en: "Next" },
  "common.create": { fr: "Créer", en: "Create" },
  "common.run": { fr: "Exécuter", en: "Run" },
  "common.close": { fr: "Fermer", en: "Close" },
  "common.yes": { fr: "Oui", en: "Yes" },
  "common.no": { fr: "Non", en: "No" },
  "common.error": { fr: "Erreur", en: "Error" },
  "common.enabled": { fr: "Activé", en: "Enabled" },
  "common.disabled": { fr: "Désactivé", en: "Disabled" },
  "common.advanced": { fr: "Options avancées", en: "Advanced options" },
  "common.slot": { fr: "Slot", en: "Slot" },
  "common.status": { fr: "Statut", en: "Status" },
  "common.version": { fr: "Version", en: "Version" },
  "common.station": { fr: "Station", en: "Station" },
  "common.stations": { fr: "Stations", en: "Stations" },
  "common.target": { fr: "Cible", en: "Target" },
  "common.targets": { fr: "Cibles", en: "Targets" },
  "common.reference": { fr: "Référence", en: "Reference" },
  "common.monitoring": { fr: "Surveillance", en: "Monitoring" },

  // Status
  "status.success": { fr: "Succès", en: "Success" },
  "status.provisional": { fr: "Provisoire", en: "Provisional" },
  "status.failed": { fr: "Échec", en: "Failed" },
  "status.passed": { fr: "χ² réussi", en: "χ² passed" },
  "status.chi_failed": { fr: "χ² échoué", en: "χ² failed" },
  "status.not-applicable": { fr: "χ² n/a", en: "χ² n/a" },
  "status.active": { fr: "Actif", en: "Active" },
  "status.inactive": { fr: "Inactif", en: "Inactive" },
  "status.draft": { fr: "Brouillon", en: "Draft" },
  "status.archived": { fr: "Archivé", en: "Archived" },

  // Processings list
  "processings.title": { fr: "Processings", en: "Processings" },
  "processings.subtitle": { fr: "Ajustement topographique — configuration, exécution et supervision", en: "Topographic adjustment — configure, run and supervise" },
  "processings.new": { fr: "Nouveau processing", en: "New processing" },
  "processings.kind.network": { fr: "Réseau", en: "Network" },
  "processings.kind.single": { fr: "Station seule", en: "Single station" },
  "processings.lastrun": { fr: "Dernier run", en: "Last run" },
  "processings.versions": { fr: "versions", en: "versions" },
  "processings.runs": { fr: "runs", en: "runs" },
  "processings.empty": { fr: "Aucun processing — créez le premier.", en: "No processing yet — create the first one." },

  // Wizard
  "wizard.title": { fr: "Nouveau processing", en: "New processing" },
  "wizard.step1": { fr: "Général", en: "General" },
  "wizard.step2": { fr: "Stations", en: "Stations" },
  "wizard.step3": { fr: "Instruments & mesures", en: "Instruments & setups" },
  "wizard.step4": { fr: "Cibles & points physiques", en: "Targets & physical points" },
  "wizard.step5": { fr: "Initialisation", en: "Initialisation" },
  "wizard.step6": { fr: "Ajustement", en: "Adjustment" },
  "wizard.step7": { fr: "Run", en: "Run" },
  "wizard.step8": { fr: "Sorties", en: "Output" },
  "wizard.step9": { fr: "Revue & création", en: "Review & create" },
  "wizard.name": { fr: "Nom du processing", en: "Processing name" },
  "wizard.description": { fr: "Description", en: "Description" },
  "wizard.kind": { fr: "Type d'ajustement", en: "Adjustment type" },
  "wizard.template": { fr: "Template initial", en: "Initial template" },
  "wizard.activeAfter": { fr: "Actif après création", en: "Active after creation" },
  "wizard.projectNote": { fr: "Le projet BTM courant est utilisé automatiquement.", en: "The current BTM project is used automatically." },
  "wizard.selectStations": { fr: "Sélectionnez les stations du projet", en: "Select the project stations" },
  "wizard.connectivityOk": { fr: "Réseau connecté via points communs", en: "Connected network through shared points" },
  "wizard.connectivityKo": { fr: "Réseau non connecté — confirmez des points communs à l'étape 4", en: "Not connected — confirm shared points in step 4" },
  "wizard.lastObs": { fr: "Dernière observation", en: "Last observation" },
  "wizard.required": { fr: "Obligatoire", en: "Required" },
  "wizard.optional": { fr: "Optionnelle", en: "Optional" },
  "wizard.coordsMode": { fr: "Coordonnées station", en: "Station coordinates" },
  "wizard.physicalPoint": { fr: "Point physique", en: "Physical point" },
  "wizard.sharedHint": { fr: "Deux cibles partagent un point physique uniquement par confirmation explicite — jamais sur le nom.", en: "Two targets share a physical point only by explicit confirmation — never by name." },
  "wizard.initMethod": { fr: "Méthode d'initialisation", en: "Initialisation method" },
  "wizard.knownCoords": { fr: "Coordonnées connues", en: "Known coordinates" },
  "wizard.localSystem": { fr: "Système local", en: "Local system" },
  "wizard.initWindow": { fr: "Période d'observations utilisée", en: "Observation window used" },
  "wizard.initNote": { fr: "La médiane des observations de la période calcule les coordonnées initiales. Cette période ne définit pas la validité de la configuration.", en: "Median observations over this window compute the initial coordinates. This window is not the configuration validity." },
  "wizard.blockers": { fr: "Erreurs bloquantes", en: "Blocking errors" },
  "wizard.warnings": { fr: "Avertissements", en: "Warnings" },
  "wizard.creating": { fr: "Création…", en: "Creating…" },
  "wizard.testEpoch": { fr: "Tester sur une époque avant création", en: "Test on an epoch before creating" },

  // Detail
  "detail.overview": { fr: "Vue d'ensemble", en: "Overview" },
  "detail.runs": { fr: "Runs", en: "Runs" },
  "detail.outputs": { fr: "Sorties", en: "Outputs" },
  "detail.versions": { fr: "Versions", en: "Versions" },
  "detail.runNow": { fr: "Run maintenant", en: "Run now" },
  "detail.reprocess": { fr: "Recalculer une période", en: "Reprocess a period" },
  "detail.analysis": { fr: "Analysis Lab", en: "Analysis Lab" },
  "detail.activeVersion": { fr: "Version active", en: "Active version" },
  "detail.validFrom": { fr: "Valide du", en: "Valid from" },
  "detail.validTo": { fr: "au", en: "to" },
  "detail.openEnded": { fr: "sans fin", en: "open-ended" },
  "detail.newDraft": { fr: "Nouveau brouillon", en: "New draft" },
  "detail.activate": { fr: "Activer", en: "Activate" },
  "detail.archive": { fr: "Archiver", en: "Archive" },
  "detail.compare": { fr: "Comparer", en: "Compare" },
  "detail.from": { fr: "Du", en: "From" },
  "detail.to": { fr: "Au", en: "To" },
  "detail.component": { fr: "Composante", en: "Component" },
  "detail.noRuns": { fr: "Aucun run — lancez le premier.", en: "No runs yet — launch the first one." },

  // Run detail
  "run.title": { fr: "Run", en: "Run" },
  "run.network": { fr: "Réseau", en: "Network" },
  "run.residuals": { fr: "Résidus", en: "Residuals" },
  "run.corrections": { fr: "Corrections", en: "Corrections" },
  "run.starnet": { fr: "Fichiers STAR*NET", en: "STAR*NET files" },
  "run.diagnostics": { fr: "Diagnostics", en: "Diagnostics" },
  "run.sourceEpochs": { fr: "Époques sources par station", en: "Source epochs per station" },
  "run.cycle": { fr: "Cycle", en: "Cycle" },
  "run.age": { fr: "Âge", en: "Age" },
  "run.availability": { fr: "Disponibilité", en: "Availability" },
  "run.adjustedPoints": { fr: "Points ajustés", en: "Adjusted points" },
  "run.ellipse": { fr: "Ellipse de confiance", en: "Confidence ellipse" },
  "run.converged": { fr: "Convergé", en: "Converged" },
  "run.iterations": { fr: "Itérations", en: "Iterations" },
  "run.rank": { fr: "Rang", en: "Rank" },
  "run.dof": { fr: "Degrés de liberté", en: "Degrees of freedom" },
  "run.varianceFactor": { fr: "Facteur de variance", en: "Variance factor" },
  "run.maxStdRes": { fr: "Résidu std. max", en: "Max std. residual" },
  "run.autoAdjust": { fr: "Auto Adjust", en: "Auto Adjust" },
  "run.excludedObs": { fr: "Observations exclues", en: "Excluded observations" },
  "run.formula": { fr: "Formule", en: "Formula" },
  "run.prismDelta": { fr: "Δ prisme", en: "Prism Δ" },
  "run.ppm": { fr: "ppm", en: "ppm" },
  "run.finalSd": { fr: "Distance finale", en: "Final distance" },
  "run.source": { fr: "Source", en: "Source" },
  "run.provisionalReasons": { fr: "Raisons provisoires", en: "Provisional reasons" },
  "run.sigma": { fr: "σ", en: "σ" },
  "run.deltaMm": { fr: "Δ (mm)", en: "Δ (mm)" },
  "run.stdRes": { fr: "Rés. std", en: "Std res" },
  "run.redundancy": { fr: "Rédondance", en: "Redundancy" },
  "run.stationOrientations": { fr: "Orientations station", en: "Station orientations" },

  // Analysis Lab
  "lab.title": { fr: "Analysis Lab", en: "Analysis Lab" },
  "lab.subtitle": { fr: "Ajustements d'essai — jamais de modification de la production", en: "Trial adjustments — production is never touched" },
  "lab.slot": { fr: "Époque à analyser", en: "Epoch to analyse" },
  "lab.run": { fr: "Lancer l'essai", en: "Run trial" },
  "lab.weights": { fr: "Poids d'essai", en: "Trial weights" },
  "lab.exclusions": { fr: "Exclusions", en: "Exclusions" },
  "lab.saveDraft": { fr: "Enregistrer comme brouillon", en: "Save as draft" },
  "lab.running": { fr: "Calcul…", en: "Computing…" },
  "lab.direction": { fr: "Direction (″)", en: "Direction (″)" },
  "lab.zenith": { fr: "Zénith (″)", en: "Zenith (″)" },
  "lab.distMm": { fr: "Distance (mm)", en: "Distance (mm)" },
  "lab.distPpm": { fr: "Distance (ppm)", en: "Distance (ppm)" },
  "lab.exclude": { fr: "Exclure", en: "Exclude" },
  "lab.include": { fr: "Réintégrer", en: "Include" },
  "lab.saved": { fr: "Brouillon créé", en: "Draft created" },
  "lab.params": { fr: "Paramètres d'essai", en: "Trial parameters" },

  // Demo page
  "demo.title": { fr: "Données de démonstration", en: "Demo data" },
  "demo.state": { fr: "État du monde simulé", en: "Simulated world state" },
  "demo.reset": { fr: "Réinitialiser les données", en: "Reset demo data" },
  "demo.deliverLate": { fr: "Livrer le cycle tardif ATS35 08:26", en: "Deliver late ATS35 08:26 cycle" },
  "demo.delivered": { fr: "Cycle tardif déjà livré", en: "Late cycle already delivered" },
  "demo.pending": { fr: "En attente", en: "Pending" },
  "demo.catchup": { fr: "Catch-up", en: "Catch-up" },
  "demo.guide": { fr: "Guide des scénarios", en: "Scenario guide" },
  "demo.scenario1": { fr: "1. Run réseau nominal — lancez le réseau ATS34+ATS35 sur un slot 2025-03-09.", en: "1. Nominal network run — run the ATS34+ATS35 network on a 2025-03-09 slot." },
  "demo.scenario2": { fr: "2. Station manquante → provisoire — le slot 2025-03-09 08:00 est provisoire (cycle ATS35 retenu).", en: "2. Missing station → provisional — slot 2025-03-09 08:00 is provisional (ATS35 cycle held back)." },
  "demo.scenario3": { fr: "3. Catch-up — livrez le cycle tardif ci-dessus : le slot 08:00 est recalculé en définitif.", en: "3. Catch-up — deliver the late cycle above: slot 08:00 is recomputed as final." },
  "demo.scenario4": { fr: "4. Auto Adjust — le slot 2025-03-09 16:00 contient une erreur +8 mm sur une référence : l'Auto Adjust l'exclut.", en: "4. Auto Adjust — slot 2025-03-09 16:00 carries a +8 mm blunder on a reference: Auto Adjust excludes it." },
  "demo.scenario5": { fr: "5. Analysis Lab — testez des poids ou excluez une observation sans toucher la production.", en: "5. Analysis Lab — try weights or exclude an observation without touching production." },
  "demo.scenario6": { fr: "6. Recalcul historique — recalculez 2025-03-09 00:00 → 2025-03-10 20:00 depuis la page du processing.", en: "6. Historical reprocess — recompute 2025-03-09 00:00 → 2025-03-10 20:00 from the processing page." },
  "demo.done": { fr: "Fait", en: "Done" },

  // Audit
  "audit.title": { fr: "Journal d'audit", en: "Audit log" },
  "audit.empty": { fr: "Aucun événement.", en: "No events." },

  // Misc labels
  "misc.observations": { fr: "observations", en: "observations" },
  "misc.environment": { fr: "lectures T/P", en: "T/P readings" },
  "misc.engineNote": { fr: "Moindres carrés pondérés 3D — SciPy trust-region, covariance SVD. STAR*NET Ultimate reste le moteur de production ; cette maquette génère et parse ses fichiers natifs.", en: "3D weighted least squares — SciPy trust-region, SVD covariance. STAR*NET Ultimate remains the production engine; this mock-up builds and parses its native files." },
} as const;

export type I18nKey = keyof typeof dict;

interface I18nContextValue {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: (key: I18nKey) => string;
}

const I18nContext = createContext<I18nContextValue>({
  lang: "fr",
  setLang: () => undefined,
  t: (key) => key,
});

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>("fr");
  const t = (key: I18nKey) => dict[key]?.[lang] ?? key;
  return <I18nContext.Provider value={{ lang, setLang, t }}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  return useContext(I18nContext);
}
