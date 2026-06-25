# Maghreb Steel — Optimisation de la Planification de Production

## 1. Introduction

Ce projet est une application web d'aide à la décision pour la planification de
production d'un site sidérurgique (Maghreb Steel). Il s'appuie sur un **modèle
d'optimisation mathématique** (programmation linéaire en nombres entiers mixte)
qui détermine, sur un horizon de plusieurs semaines :

- quelles commandes accepter et lesquelles refuser,
- comment router chaque commande à travers les machines de l'usine (décapage,
  laminage à froid, recuit, galvanisation, etc.),
- comment gérer les stocks de bobines à chaud (HRC), les stocks
  interprocess et les stocks de produits finis,
- comment minimiser les retards de livraison et maximiser la marge globale,

tout en respectant les contraintes de capacité des machines, de disponibilité
matière première et de niveaux de stock min/max.

L'application est composée de deux briques :

- un **backend Python** qui lit les données d'entrée (fichier Excel), construit
  et résout le modèle d'optimisation, puis expose les résultats via une API ;
- un **frontend React** qui permet de configurer un scénario, de lancer une
  optimisation, de suivre son avancement et de visualiser/exporter les
  résultats (plan de production, stocks, commandes acceptées/refusées,
  indicateurs, etc.).

Le frontend communique avec le backend uniquement via des appels HTTP vers
l'API Flask — il n'a jamais d'accès direct aux données ou au solveur.

## 2. Architecture du projet

```
/ (dossier racine)
│── README.md
│
├── backend/
│   ├── api.py                  # Serveur Flask : expose l'API REST au frontend
│   ├── model1.py                # Construction du modèle d'optimisation (Pyomo)
│   ├── solve1_4.py              # Résolution, analyse et export des résultats
│   ├── data_loader1.py          # Lecture/parsing du fichier Excel d'entrée
│   ├── validation.py             # Script de validation a posteriori d'une solution
│   ├── Donnees_MaghrebSteel.xlsx # Jeu de données d'entrée (commandes, cadences, etc.)
│   ├── saved_runs.json          # Historique des runs sauvegardés (persistance simple)
│   └── exports/                 # Fichiers Excel générés à chaque optimisation
│
└── frontend/
    ├── src/
    │   └── App.tsx               # Application React (interface principale)
    ├
    └── fichiers de configuration React (package.json, tsconfig, etc.)
```

> Les noms de fichiers ci-dessus (`api.py`, `model1.py`, `solve1_4.py`,
> `data_loader1.py`, `validation.py`, `App.tsx`) correspondent au code livré.
> Libre à vous de les renommer (par ex. sans le suffixe numérique) du moment
> que vous adaptez les `import` correspondants.

### Rôle du backend

- **`data_loader1.py`** — Lit le fichier `Donnees_MaghrebSteel.xlsx` (feuilles
  Commandes, Cadences, Rendements, Coûts variables, Prix HRC, Arrêts
  planifiés, Stocks initiaux, Paramètres) et construit toutes les structures
  de données (dictionnaires, listes d'ensembles I/T/M/G/F/K) utilisées par le
  modèle.
- **`model1.py`** — Construit le modèle d'optimisation avec **Pyomo**
  (variables, contraintes de capacité, de flux/rendement, de stock, fonction
  objectif).
- **`solve1_4.py`** — Résout le modèle avec le solveur **HiGHS**
  (`pyomo.contrib.appsi.solvers.Highs`), analyse les résultats (commandes
  acceptées/refusées, retards, goulots d'étranglement) et exporte un rapport
  complet au format Excel.
- **`validation.py`** — Script indépendant qui relit un fichier de résultats
  Excel généré par `solve1_4.py` et vérifie a posteriori que toutes les
  contraintes du modèle sont respectées (utile pour les tests et le contrôle
  qualité).
- **`api.py`** — Serveur **Flask** qui orchestre tout : il reçoit les requêtes
  du frontend, lance les optimisations en tâche de fond (jobs asynchrones
  avec suivi de statut), gère l'upload de fichiers de paramètres, la
  sauvegarde/suppression de runs (`saved_runs.json`), et la mise à
  disposition des fichiers Excel exportés en téléchargement.

### Rôle du frontend

- **`App.tsx`** — Application React (TypeScript) qui fournit l'interface
  utilisateur : configuration des paramètres d'un scénario, lancement d'une
  optimisation, suivi de la progression, affichage des résultats sous forme
  de tableaux et de graphiques (avec `recharts`), export des données
  (avec `xlsx`), et historique des runs précédents.

### Communication via l'API Flask

Le frontend dialogue avec le backend via les routes HTTP suivantes exposées
par `api.py` :

| Méthode | Route | Rôle |
|---|---|---|
| `POST` | `/optimize` | Lance une nouvelle optimisation (job asynchrone) |
| `GET` | `/optimize/status/<job_id>` | Récupère le statut/avancement d'un job |
| `POST` | `/lire-parametres-fichier` | Lit les paramètres d'un fichier Excel uploadé |
| `POST` | `/runs` | Sauvegarde un run dans l'historique |
| `GET` | `/runs` | Liste les runs sauvegardés |
| `DELETE` | `/runs/<run_id>` | Supprime un run sauvegardé |
| `GET` | `/download/<filename>` | Télécharge un fichier de résultats exporté |

Le serveur Flask est configuré avec **CORS** activé afin d'autoriser les
appels depuis l'application React (généralement servie sur un port différent
en développement).

## 3. Technologies utilisées

**Backend**
- Python 3.x
- [Flask](https://flask.palletsprojects.com/) — serveur API REST
- [Flask-CORS](https://flask-cors.readthedocs.io/) — gestion du Cross-Origin
- [Pyomo](https://www.pyomo.org/) — modélisation du problème d'optimisation
- [HiGHS](https://highs.dev/) (via `pyomo.contrib.appsi.solvers.Highs` /
  package `highspy`) — solveur MILP
- [pandas](https://pandas.pydata.org/) / [numpy](https://numpy.org/) —
  manipulation des données
- [openpyxl](https://openpyxl.readthedocs.io/) — lecture/écriture Excel

**Frontend**
- [React](https://react.dev/) + TypeScript
- [recharts](https://recharts.org/) — graphiques
- [lucide-react](https://lucide.dev/) — icônes
- [xlsx (SheetJS)](https://sheetjs.com/) — export/lecture de fichiers Excel
  côté client

## 4. Installation

### Prérequis

- Python ≥ 3.9
- Node.js ≥ 18 et npm
- Le fichier de données `Donnees_MaghrebSteel.xlsx` (déjà fourni dans
  `backend/`)

### Backend

```bash
cd backend

# 1. Création d'un environnement virtuel
python -m venv venv

# 2. Activation de l'environnement
# Windows :
venv\Scripts\activate
# macOS / Linux :
source venv/bin/activate

# 3. Installation des dépendances
pip install flask flask-cors pandas numpy openpyxl pyomo highspy
pip install -r requirements.txt

# 4. Lancement du serveur Flask
python api.py
```

Le serveur démarre par défaut sur `http://0.0.0.0:5000` (voir la fin de
`api.py`).

> ℹ️ Le projet ne fournit pas de fichier `requirements.txt`. La liste de
> dépendances ci-dessus a été établie à partir des `import` réellement
> présents dans le code (`api.py`, `model1.py`, `solve1_4.py`,
> `data_loader1.py`). Il est recommandé de générer un `requirements.txt`
> une fois l'environnement installé, avec `pip freeze > requirements.txt`,
> afin de figer les versions pour les installations futures.

> ℹ️ `data_loader1.py` contient un chemin Excel par défaut codé en dur
> (`DEFAULT_EXCEL_PATH`, propre à l'environnement d'origine). En pratique,
> `api.py` permet d'uploader/sélectionner son propre fichier Excel via
> l'interface, donc ce chemin par défaut n'a pas besoin d'être valide pour
> utiliser l'application via le frontend.

### Frontend

```bash
cd frontend

# 1. Installation des dépendances Node.js
npm install

# 2. Lancement de l'application React
npm start
```

L'interface est alors accessible (par défaut) sur `http://localhost:3000`.

## 5. Utilisation

1. **Démarrer le backend en premier** : `python api.py` (port 5000).
2. **Démarrer ensuite le frontend** : `npm start` (port 3000), qui appellera
   automatiquement l'API backend.
3. Dans l'interface :
   - Configurez le scénario (paramètres, fichier de données, options du
     modèle) ;
   - Lancez l'optimisation — un job est créé côté serveur et résolu de
     façon asynchrone par le solveur HiGHS ; l'avancement peut être suivi en
     temps réel ;
   - Une fois le job terminé, consultez les résultats : commandes
     acceptées/refusées, plan de production semaine par semaine, niveaux de
     stocks, indicateurs de performance et graphiques ;
   - Téléchargez le rapport Excel complet généré par l'optimisation, ou
     sauvegardez le run dans l'historique pour le retrouver plus tard.
4. (Optionnel) Pour vérifier la validité d'une solution exportée
   indépendamment de l'interface, exécutez :
   ```bash
   python validation.py
   ```
   Ce script recherche automatiquement le dernier fichier de résultats
   `resultats_maghreb_steel_*.xlsx` dans le dossier courant et vérifie
   l'ensemble des contraintes du modèle.

### Lancer le solveur sans passer par l'interface

Le moteur d'optimisation peut aussi être exécuté **directement en ligne de
commande**, sans backend Flask ni frontend React. Cela est utile pour des
tests, du debug, ou des exécutions par script :

```bash
cd backend
python solve1_4.py
```

Ce fichier contient un bloc `if __name__ == "__main__":` qui, exécuté
directement :
1. charge les données depuis le fichier Excel par défaut
   (`charger_donnees()` dans `data_loader1.py`) ;
2. construit le modèle d'optimisation (`construire_modele` dans
   `model1.py`) ;
3. résout le modèle avec le solveur HiGHS (limite de temps : 600 secondes) ;
4. affiche la progression et les résultats dans la console.

> ⚠️ Dans ce mode, le chemin du fichier Excel utilisé est celui codé en dur
> dans `DEFAULT_EXCEL_PATH` (`data_loader1.py`) — assurez-vous qu'il pointe
> vers un fichier valide sur votre machine, ou modifiez-le, avant de lancer
> `solve1_4.py` directement.

Cette méthode permet donc de faire tourner l'optimiseur de façon totalement
indépendante de l'application web (utile notamment pour automatiser des
campagnes de tests ou comparer des scénarios en batch).

## 6. Notes importantes

- **Différences mineures avec le rapport académique** : le modèle
  d'optimisation utilisé dans cette interface graphique a été **légèrement
  ajusté** par rapport à la version présentée dans le rapport académique
  (ex. options activables/désactivables comme certaines contraintes
  optionnelles, gestion des surcharges de paramètres). Ces ajustements sont
  **mineurs** et **n'affectent pas grandement la formulation mathématique principale**
  du problème d'optimisation. Ils visent essentiellement à rendre le modèle
  plus flexible et utilisable depuis une interface interactive.
- **Stabilité des résultats** : si des écarts de résultats ou de
  comportement sont observés par rapport au rapport académique, ils sont
  très probablement dus à ces ajustements légers . Le script `validation.py` permet de vérifier indépendamment la cohérence de toute solution produite.
- **Support** : en cas de problème, d'incohérence dans les résultats, ou de
  question sur le fonctionnement du modèle, n'hésitez pas à nous contacter pour clarification ou correction.
