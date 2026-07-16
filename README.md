# BTM Topographic Adjustment — maquette full-stack

Refonte complète des deux prototypes précédents (`StarNet`, `btm-topographic-adjustment-mockup`)
en **une seule application** : backend Python pour les moteurs de calcul et les packages de
correction, frontend React sobre et bilingue FR/EN.

## Architecture

```
app/
├── backend/                  # FastAPI + noyau scientifique Python
│   ├── core/btm_topography/  # Moindres carrés 3D, corrections, initialisation, synchro (vendoré, testé)
│   ├── app/
│   │   ├── models.py         # SQLite = base BTM simulée (raw_data, versions, runs, sorties)
│   │   ├── seed.py           # Monde démo : ATS34 réel + ATS35 synthétique cohérent
│   │   ├── services/engine.py# Pipeline : synchro → corrections → init → ajustement → STAR*NET → publication
│   │   ├── services/starnet/ # Package STAR*NET : build .dat/.prj, parse .pts/.err
│   │   └── api/              # processings, versions, runs, analysis lab, demo
│   ├── data/                 # ats34.generated.json (réel), ats35.generated.json (généré)
│   ├── scripts/generate_ats35.py
│   └── tests/                # 12 tests (moteur, STAR*NET, API)
├── src/                      # React + TS + Tailwind + shadcn/ui
│   ├── pages/                # Processings, Détail, Run, Analysis Lab, Wizard 9 étapes, Démo, Journal
│   └── components/           # NetworkMap (ellipses 95 %), badges, layout
└── Dockerfile                # Image unique : build frontend + uvicorn
```

## Lancer

```bash
# Docker (tout-en-un)
docker build -t btm-topo . && docker run -p 8000:8000 btm-topo

# ou en dev
cd backend && pip install -r requirements.txt && uvicorn app.main:app --port 8000
npm install && npm run dev        # proxy /api → :8000
```

## Ce qui est démontré

- **Réseau 2 stations réel** : ATS34 (données réelles du classeur, 09–10/03/2025, cycles 4 h) +
  ATS35 (station synthétique cohérente, 5 références physiques communes, orientation/position
  retrouvées par le calcul : erreur < 3 mm).
- **Pipeline complet** : synchronisation multi-stations désynchronisées (:05 / :29) → corrections
  prisme + atmosphériques appliquées une seule fois et tracées → coordonnées initiales par médianes →
  ajustement moindres carrés pondéré → χ² → Auto Adjust → publication idempotente sur grille 4 h.
- **Scénarios** : station manquante → provisoire (08:00) ; livraison tardive → catch-up automatique ;
  erreur +8 mm sur référence redondante → exclusion par Auto Adjust (16:00) ; recalcul historique
  par période ; Analysis Lab (poids/exclusions d'essai, jamais en production) ; versions avec
  validité temporelle, activation, comparaison.
- **STAR*NET** : fichiers `.dat`/`.prj` générés par run (visibles dans l'onglet dédié), `.pts`/`.err`
  parsés en retour — la voie prête pour le worker Windows de production.

## Tests

```bash
cd backend && python -m pytest tests/ -q   # 12 passed
```
