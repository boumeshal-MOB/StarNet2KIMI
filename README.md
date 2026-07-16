# BTM Topographic Adjustment — maquette full-stack

Refonte complète des deux prototypes précédents (`StarNet`, `btm-topographic-adjustment-mockup`)
en **une seule application** : backend Python pour les moteurs de calcul et les packages de
correction, frontend React sobre et bilingue FR/EN.

## Architecture

```
app/
├── backend/                  # FastAPI + noyau scientifique Python
│   ├── core/btm_topography/  # Moindres carrés 3D, corrections, initialisation, synchro (vendoré, testé)
│   ├── lambda_app/           # Adaptateur AWS Lambda stateless et contrat BTM versionné
│   ├── app/
│   │   ├── models.py         # SQLite = base BTM simulée (raw_data, versions, runs, sorties)
│   │   ├── seed.py           # Monde démo : ATS34 réel + ATS35 synthétique cohérent
│   │   ├── services/engine.py# Pipeline démo : synchro → corrections → init → ajustement → publication
│   │   ├── services/starnet/ # Package STAR*NET : build .dat/.prj, parse .pts/.err
│   │   └── api/              # processings, versions, runs, analysis lab, demo
│   ├── data/                 # ats34.generated.json (réel), ats35.generated.json (généré)
│   ├── scripts/generate_ats35.py
│   └── tests/                # moteur, STAR*NET, API et contrat Lambda
├── src/                      # React + TS + Tailwind + shadcn/ui
│   ├── pages/                # Processings, Détail, Run, Analysis Lab, Wizard 9 étapes, Démo, Journal
│   └── components/           # NetworkMap (ellipses 95 %), badges, layout
├── Dockerfile                # Image démo full-stack : build frontend + uvicorn
├── Dockerfile.lambda         # Image AWS Lambda Python 3.12, sans FastAPI ni SQLite
├── template.lambda.yaml      # Déploiement AWS SAM de la Lambda de calcul
└── vercel.json               # Build Vite et réécriture SPA pour le frontend
```

## Lancer la maquette

```bash
# Docker (tout-en-un)
docker build -t btm-topo . && docker run -p 8000:8000 btm-topo

# ou en dev
cd backend && pip install -r requirements.txt && uvicorn app.main:app --port 8000
npm install && npm run dev        # proxy /api → :8000
```

## Déployer le frontend sur Vercel

Le build Vercel est configuré dans `vercel.json` :

- framework : Vite ;
- installation : `npm ci` ;
- build : `npm run build` ;
- sortie : `dist` ;
- réécriture SPA vers `index.html`.

Pour utiliser une API déployée séparément, définir dans Vercel :

```text
VITE_API_BASE_URL=https://votre-api-btm.example.com/api
```

Sans cette variable, le frontend appelle `/api` sur le même domaine. La Lambda de calcul ne
remplace pas à elle seule toutes les routes CRUD de la maquette (`processings`, `versions`, `runs`,
`audit`). Pour une application complète, Vercel doit pointer vers le backend BTM ou vers une API
FastAPI/API Gateway fournissant ces routes et déclenchant la Lambda de calcul.

## Lambda de calcul BTM

La Lambda est stateless : le backend BTM prépare un snapshot immuable avec la configuration,
les observations et les mesures environnementales. La Lambda calcule et renvoie le résultat,
les diagnostics, les valeurs X/Y/Z, DX/DY/DZ, SX/SY/SZ et les entrées STAR*NET. BTM reste
responsable de la base de données, des runs, des droits et de la publication.

```bash
docker build -f Dockerfile.lambda -t btm-topographic-lambda .
sam build -t template.lambda.yaml
sam deploy --guided
```

Contrat : `btm.topographic-adjustment.lambda.v1`.
Documentation détaillée : [`docs/BTM_LAMBDA_HANDOFF.md`](docs/BTM_LAMBDA_HANDOFF.md).

Opérations principales :

- `run-processing` : pipeline complet depuis un snapshot résolu par BTM ;
- `calculate` : calcul sur des points et visées déjà préparés ;
- `build-starnet-inputs` : génération réelle des fichiers `.dat` et `.prj` ;
- `parse-starnet-outputs` : lecture des `.pts` et `.err` retournés par le futur worker Windows.

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
- **STAR*NET** : fichiers `.dat`/`.prj` générés par run et par la Lambda, `.pts`/`.err` parsés en
  retour. STAR*NET Ultimate reste destiné au worker Windows licencié contrôlé par BTM.

## Tests

```bash
cd backend && python -m pytest tests/ -q
npm run lint && npm run build
docker build -f Dockerfile.lambda -t btm-topographic-lambda:test .
```
