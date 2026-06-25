"""
robustesse_B9.py
================
Analyse de robustesse par simulation Monte Carlo — Maghreb Steel
Réponse à la question B9 :
  "Si les cadences réelles sont incertaines de ±5%,
   le plan optimal reste-t-il faisable ?
   Quel niveau de marge de sécurité doit-on prévoir ?"

MÉTHODE :
  1. Résoudre le modèle nominal → plan optimal de référence (baseline)
  2. Générer N tirages aléatoires de cadences dans [−5%, +5%]
  3. Pour chaque tirage : re-résoudre le modèle avec ces cadences perturbées
  4. Comparer marge, commandes acceptées, faisabilité
  5. Calculer les statistiques de robustesse et la marge de sécurité recommandée
  6. Exporter les résultats dans un fichier Excel

Dépendances : pyomo, highspy, pandas, numpy, matplotlib, openpyxl
"""

import copy
import gc
import io
import sys
import time
import warnings
from datetime import datetime

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # pas d affichage interactif, sauvegarde en PNG
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
import pyomo.environ as pyo
from pyomo.contrib.appsi.solvers import Highs as AppsiHighs

# ── imports projet (fichiers intacts) ───────────────────────────────────────
from data_loader1 import charger_donnees
from model1 import construire_modele

warnings.filterwarnings("ignore")

# ============================================================
# PARAMÈTRES
# ============================================================
N_SIMULATIONS   = 50        # nombre de tirages Monte Carlo
INCERTITUDE     = 0.05      # ±5% sur les cadences
TIME_LIMIT      = 12000      # secondes par run (120s suffisent sans B4)
ACTIVER_B2      = True      # retards activés
ACTIVER_B4      = True    # désactivé pour vitesse + shadow prices
GRAINE_ALEATOIRE = 42       # reproductibilité des tirages

MACHINES = ["PK", "CRMA", "CRMB", "BAF", "SKP", "LGA", "LGB"]


# ============================================================
# SECTION 1 — SOLVEUR (silencieux)
# ============================================================

def resoudre_silencieux(m, time_limit=TIME_LIMIT):
    """
    Résout le modèle avec HiGHS APPSI.
    Accepte les solutions optimales ET suboptimales (time_limit atteint).
    Retourne (marge, n_acceptees, taux, refused, statut_str, wall_time).
    """
    try:
        solver = AppsiHighs()
        solver.config.time_limit    = time_limit
        solver.config.stream_solver = False
        try:
            solver.highs_options['mip_rel_gap'] = 0.02  # gap 2% pour vitesse MC
        except Exception:
            pass

        debut = time.time()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            results = solver.solve(m)
        elapsed = time.time() - debut

        tc = str(results.termination_condition).lower()
        statut_ok = any(s in tc for s in ('optimal', 'feasible', 'suboptimal'))

        if statut_ok:
            try:
                val = pyo.value(m.obj)
                statut_ok = (val is not None)
            except Exception:
                statut_ok = False

        if not statut_ok:
            return None, None, None, [], "INFAISABLE", elapsed

        marge  = pyo.value(m.obj)
        n_acc  = sum(1 for i in data_ref["I"] if pyo.value(m.y[i]) > 0.5)
        taux   = 100.0 * n_acc / len(data_ref["I"])
        refused = [i for i in data_ref["I"] if pyo.value(m.y[i]) < 0.5]
        statut = "OPTIMAL" if 'optimal' in tc else "SUBOPTIMAL"

        return marge, n_acc, taux, refused, statut, elapsed

    except Exception as e:
        return None, None, None, [], f"ERREUR:{e}", 0.0


# ============================================================
# SECTION 2 — CONSTRUCTION SILENCIEUSE DU MODÈLE
# ============================================================

def construire_silencieux(data_mod):
    """Construit le modèle sans afficher les prints de model1.py."""
    old = sys.stdout
    sys.stdout = io.StringIO()
    try:
        m, IP, IPM = construire_modele(data_mod, activer_B2=ACTIVER_B2, activer_B4=ACTIVER_B4)
    finally:
        sys.stdout = old
    return m, IP, IPM


# ============================================================
# SECTION 3 — TIRAGE MONTE CARLO
# ============================================================

def tirer_cadences_perturbees(data_base, rng, incertitude=INCERTITUDE):
    """
    Génère une copie de data avec des cadences multipliées par un facteur
    aléatoire uniforme dans [1 − incertitude, 1 + incertitude] pour chaque machine.

    Chaque machine a son propre facteur (corrélation nulle entre machines).
    C'est le scénario le plus pessimiste : toutes les machines peuvent être
    dégradées indépendamment et simultanément.

    Retourne (data_perturbé, dict des facteurs appliqués).
    """
    d = copy.deepcopy(data_base)
    facteurs = {}

    for mach in MACHINES:
        # Tirage uniforme dans [1-ε, 1+ε]
        f = rng.uniform(1.0 - incertitude, 1.0 + incertitude)
        facteurs[mach] = round(f, 4)
        # Application à toutes les familles de cette machine
        for (m_key, fam_key) in d["cadences"]:
            if m_key == mach and d["cadences"][(m_key, fam_key)] > 0:
                d["cadences"][(m_key, fam_key)] *= f

    return d, facteurs


# ============================================================
# SECTION 4 — VÉRIFICATION DE FAISABILITÉ DU PLAN FIXÉ
# ============================================================

def verifier_plan_fixe(plan_baseline, facteurs, data_base):
    """
    Vérifie si le plan optimal du baseline reste faisable
    avec des cadences perturbées, SANS re-optimiser.

    Le plan est défini par les valeurs de x[i,p,mach,t] du baseline.
    On vérifie pour chaque (machine, famille, semaine) :
        charge_planifiée ≤ cadence_perturbée × jours_disponibles

    Retourne un dict {(mach, fam, t): (charge, capacite, violation)}
    """
    violations = {}
    arrets = data_base["arrets"]
    jours  = data_base["params"]["jours_semaine"]

    for mach in MACHINES:
        for fam in data_base["F"]:
            cad_nominale = data_base["cadences"].get((mach, fam), 0.0)
            if cad_nominale == 0.0:
                continue
            cad_perturbee = cad_nominale * facteurs[mach]

            for t in data_base["T"]:
                jours_dispo  = jours - arrets.get((mach, t), 0)
                capacite     = cad_perturbee * jours_dispo
                charge       = plan_baseline.get((mach, fam, t), 0.0)

                if charge > capacite + 1e-3:  # tolérance numérique 1 kg
                    violations[(mach, fam, t)] = {
                        "charge"    : round(charge, 1),
                        "capacite"  : round(capacite, 1),
                        "depassement": round(charge - capacite, 1),
                        "facteur"   : facteurs[mach],
                    }

    return violations


def extraire_plan_baseline(m, data):
    """
    Extrait le plan de production du baseline sous forme de dict
    {(mach, fam, t): charge_totale} pour la vérification de faisabilité.
    """
    plan = {}
    cmd = data["commandes"]
    for i in data["I"]:
        if pyo.value(m.y[i]) < 0.5:
            continue
        c = cmd[i]
        for p in range(len(c["chemins"])):
            for mach in c["chemins"][p]:
                for t in data["T"]:
                    val = pyo.value(m.x[i, p, mach, t])
                    if val is None or val < 1e-6:
                        continue
                    key = (mach, c["famille"], t)
                    plan[key] = plan.get(key, 0.0) + val
    return plan


# ============================================================
# SECTION 5 — SIMULATION MONTE CARLO PRINCIPALE
# ============================================================

def lancer_monte_carlo(data_base, m_baseline, plan_baseline, ref_marge):
    """
    Lance N_SIMULATIONS résolutions avec cadences perturbées.
    Pour chaque run :
      - Vérifie si le plan baseline est encore faisable (check rapide)
      - Re-optimise avec les cadences perturbées (marge réelle atteignable)
      - Collecte les statistiques

    Retourne la liste des résultats.
    """
    rng = np.random.default_rng(GRAINE_ALEATOIRE)
    resultats = []

    print(f"\n  Lancement de {N_SIMULATIONS} simulations Monte Carlo...")
    print(f"  Incertitude : ±{INCERTITUDE*100:.0f}% sur chaque machine (uniforme, indépendant)")
    print(f"  Solveur     : B2={ACTIVER_B2}, B4={ACTIVER_B4}, time_limit={TIME_LIMIT}s")
    print()
    print(f"  {'Run':>4}  {'Facteurs clés (CRMB/BAF/LGA)':30}  {'Marge (MAD)':>15}  "
          f"{'Δ Marge':>12}  {'Acc':>4}  {'Viol.':>5}  {'Statut':10}  {'Tps':>5}")
    print("  " + "─" * 105)

    for sim in range(1, N_SIMULATIONS + 1):
        # 1. Tirage des cadences perturbées
        d_pert, facteurs = tirer_cadences_perturbees(data_base, rng)

        # 2. Vérification rapide du plan fixé (sans re-optimiser)
        violations = verifier_plan_fixe(plan_baseline, facteurs, data_base)
        n_violations = len(violations)

        # 3. Re-optimisation avec cadences perturbées
        m_pert, _, _ = construire_silencieux(d_pert)
        marge, n_acc, taux, refused, statut, wall_time = resoudre_silencieux(m_pert)

        del m_pert
        gc.collect()

        delta = (marge - ref_marge) if marge is not None else None

        # Affichage compact
        f_crmb = facteurs.get("CRMB", 1.0)
        f_baf  = facteurs.get("BAF",  1.0)
        f_lga  = facteurs.get("LGA",  1.0)
        cles   = f"CRMB={f_crmb:.3f} BAF={f_baf:.3f} LGA={f_lga:.3f}"

        marge_str = f"{marge:>15,.0f}" if marge is not None else f"{'INFAISABLE':>15}"
        delta_str = f"{delta:>+12,.0f}" if delta is not None else f"{'—':>12}"
        n_acc_str = f"{n_acc:>4}" if n_acc is not None else f"{'—':>4}"

        print(f"  {sim:>4}  {cles:30}  {marge_str}  {delta_str}  "
              f"{n_acc_str}  {n_violations:>5}  {statut:10}  {wall_time:>4.0f}s")

        resultats.append({
            "sim"          : sim,
            "facteurs"     : facteurs,
            "marge"        : marge,
            "delta_marge"  : delta,
            "n_acceptees"  : n_acc,
            "taux_service" : taux,
            "refused"      : refused,
            "n_violations" : n_violations,
            "violations"   : violations,
            "statut"       : statut,
            "wall_time"    : wall_time,
        })

    return resultats


# ============================================================
# SECTION 6 — STATISTIQUES DE ROBUSTESSE
# ============================================================

def calculer_statistiques(resultats, ref_marge):
    """
    Calcule les statistiques de robustesse à partir des résultats Monte Carlo.
    Retourne un dict de statistiques et des DataFrames pour l'export Excel.
    """
    marges_valides = [r["marge"] for r in resultats if r["marge"] is not None]
    deltas_valides = [r["delta_marge"] for r in resultats if r["delta_marge"] is not None]
    n_runs         = len(resultats)
    n_faisables    = len(marges_valides)
    n_infaisables  = n_runs - n_faisables

    # Taux de faisabilité du plan fixé
    n_plan_ok      = sum(1 for r in resultats if r["n_violations"] == 0)
    taux_plan_ok   = 100.0 * n_plan_ok / n_runs

    # Statistiques sur la marge re-optimisée
    if marges_valides:
        marge_moy   = np.mean(marges_valides)
        marge_std   = np.std(marges_valides)
        marge_min   = np.min(marges_valides)
        marge_max   = np.max(marges_valides)
        marge_p5    = np.percentile(marges_valides, 5)   # pire cas 5%
        marge_p10   = np.percentile(marges_valides, 10)  # pire cas 10%
        marge_p25   = np.percentile(marges_valides, 25)  # Q1
        marge_p95   = np.percentile(marges_valides, 95)  # meilleur cas 5%
    else:
        marge_moy = marge_std = marge_min = marge_max = None
        marge_p5  = marge_p10 = marge_p25 = marge_p95 = None

    # Marge de sécurité recommandée = écart entre baseline et P10 (pire 10%)
    marge_securite = (ref_marge - marge_p10) if marge_p10 is not None else None

    # Machines les plus souvent en violation
    compteur_violations = {}
    for r in resultats:
        for (mach, fam, t) in r["violations"]:
            cle = f"{mach}/{fam}/S{t}"
            compteur_violations[cle] = compteur_violations.get(cle, 0) + 1

    # Commandes les plus souvent refusées sous perturbation
    compteur_refus = {}
    for r in resultats:
        for i in r["refused"]:
            compteur_refus[i] = compteur_refus.get(i, 0) + 1

    stats = {
        "n_runs"            : n_runs,
        "n_faisables"       : n_faisables,
        "n_infaisables"     : n_infaisables,
        "taux_faisabilite"  : 100.0 * n_faisables / n_runs,
        "n_plan_ok"         : n_plan_ok,
        "taux_plan_ok"      : taux_plan_ok,
        "ref_marge"         : ref_marge,
        "marge_moy"         : marge_moy,
        "marge_std"         : marge_std,
        "marge_min"         : marge_min,
        "marge_max"         : marge_max,
        "marge_p5"          : marge_p5,
        "marge_p10"         : marge_p10,
        "marge_p25"         : marge_p25,
        "marge_p95"         : marge_p95,
        "marge_securite_recommandee": marge_securite,
        "machines_critiques": sorted(compteur_violations.items(),
                                     key=lambda x: x[1], reverse=True)[:10],
        "commandes_fragiles": sorted(compteur_refus.items(),
                                     key=lambda x: x[1], reverse=True)[:10],
    }

    return stats


# ============================================================
# SECTION 7 — AFFICHAGE DES RÉSULTATS
# ============================================================

def afficher_resultats(stats, ref_marge):
    print("\n" + "═" * 70)
    print("  RÉSULTATS DE L'ANALYSE DE ROBUSTESSE — MONTE CARLO")
    print("═" * 70)

    print(f"""
  ┌─────────────────────────────────────────────────────┐
  │  FAISABILITÉ                                        │
  │  Runs total              : {stats['n_runs']:>6}                    │
  │  Solutions trouvées      : {stats['n_faisables']:>6} ({stats['taux_faisabilite']:>5.1f}%)           │
  │  Infaisables             : {stats['n_infaisables']:>6}                    │
  │  Plan baseline encore OK : {stats['n_plan_ok']:>6} / {stats['n_runs']} ({stats['taux_plan_ok']:>5.1f}%)    │
  └─────────────────────────────────────────────────────┘
""")

    if stats["marge_moy"] is not None:
        print(f"  DISTRIBUTION DE LA MARGE RE-OPTIMISÉE")
        print(f"  {'Référence (baseline)':<35} : {ref_marge:>15,.0f} MAD")
        print(f"  {'Moyenne':<35} : {stats['marge_moy']:>15,.0f} MAD")
        print(f"  {'Écart-type':<35} : {stats['marge_std']:>15,.0f} MAD")
        print(f"  {'Minimum (pire tirage)':<35} : {stats['marge_min']:>15,.0f} MAD")
        print(f"  {'Maximum (meilleur tirage)':<35} : {stats['marge_max']:>15,.0f} MAD")
        print(f"  {'Percentile 5% (pire cas 5%)':<35} : {stats['marge_p5']:>15,.0f} MAD")
        print(f"  {'Percentile 10% (pire cas 10%)':<35} : {stats['marge_p10']:>15,.0f} MAD")
        print(f"  {'Percentile 95% (meilleur cas 5%)':<35} : {stats['marge_p95']:>15,.0f} MAD")

        print(f"""
  ┌─────────────────────────────────────────────────────────────────┐
  │  MARGE DE SÉCURITÉ RECOMMANDÉE                                  │
  │                                                                 │
  │  Baseline                    : {ref_marge:>15,.0f} MAD            │
  │  Pire cas 10% (P10)          : {stats['marge_p10']:>15,.2f} MAD            │
  │  → Marge de sécurité P10     : {stats['marge_securite_recommandee']:>15,.2f} MAD            │
  │                                                                 │
  │  Interprétation : prévoir {100*stats['marge_securite_recommandee']/ref_marge:>4.6f}% de coussin sur la marge  │
  │  pour absorber l'incertitude ±5% des cadences.                  │
  └─────────────────────────────────────────────────────────────────┘
""")

    # Machines les plus critiques
    if stats["machines_critiques"]:
        print("  MACHINES LES PLUS SOUVENT EN VIOLATION DE CAPACITÉ")
        print(f"  {'Machine/Famille/Semaine':<30} {'Violations':>12} {'Fréquence':>10}")
        print("  " + "─" * 55)
        for cle, nb in stats["machines_critiques"]:
            freq = 100.0 * nb / stats["n_runs"]
            print(f"  {cle:<30} {nb:>12}    {freq:>8.1f}%")

    # Commandes les plus fragiles
    if stats["commandes_fragiles"]:
        print(f"\n  COMMANDES LES PLUS SOUVENT REFUSÉES SOUS PERTURBATION")
        print(f"  {'Commande':<15} {'Refus':>8} {'Fréquence':>10}")
        print("  " + "─" * 36)
        for cmd_id, nb in stats["commandes_fragiles"]:
            freq = 100.0 * nb / stats["n_runs"]
            print(f"  {cmd_id:<15} {nb:>8}    {freq:>8.1f}%")

    print()


# ============================================================
# SECTION 8 — EXPORT EXCEL
# ============================================================

def exporter_excel(resultats, stats, ref_marge, timestamp, data_ref=None, refused_base=None):
    """
    Export Excel exhaustif — 9 onglets.

    1. Résumé          — KPI globaux, marge de sécurité, interprétation
    2. Détail_runs     — Une ligne par run avec TOUS les facteurs machines + commandes refusées
    3. Config_min      — Configuration exacte du run avec la marge la plus basse
    4. Config_max      — Configuration exacte du run avec la marge la plus haute
    5. Impact_machines — Corrélation de chaque machine avec la marge (classement)
    6. Violations      — Chaque violation de capacité détaillée
    7. Cmdes_fragiles  — Commandes refusées avec fréquence + profil (famille, grade, prix)
    8. Machines_crit   — Fréquence de violation par point du plan
    9. Percentiles     — Distribution complète (deciles)
    """
    nom = f"robustesse_B9_{timestamp}.xlsx"
    print(f"  Export Excel → {nom}")

    # Préparation des données utiles
    runs_valides = [r for r in resultats if r["marge"] is not None]
    cmd_data     = data_ref["commandes"] if data_ref else {}

    try:
        with pd.ExcelWriter(nom, engine="openpyxl") as writer:

            # ══════════════════════════════════════════════════════════════
            # ONGLET 1 — RÉSUMÉ
            # ══════════════════════════════════════════════════════════════
            ms  = stats["marge_securite_recommandee"]
            pct = round(100 * ms / ref_marge, 2) if ms and ref_marge else None

            # Interprétation automatique de la marge de sécurité
            if ms is not None and ms < 0:
                interpretation = (
                    "La marge re-optimisée DÉPASSE le baseline dans 90% des cas. "
                    "Le plan est robuste : les perturbations ±5% permettent souvent "
                    "de mieux charger les lignes. Aucune marge de sécurité négative "
                    "n'est à provisionner."
                )
            elif ms is not None and pct < 2:
                interpretation = (
                    f"Coussin de {pct:.1f}% : risque faible. "
                    "Le plan reste quasi-identique sous perturbation."
                )
            elif ms is not None:
                interpretation = (
                    f"Coussin de {pct:.1f}% recommandé pour garantir la marge "
                    "dans 90% des scénarios de perturbation."
                )
            else:
                interpretation = "Données insuffisantes."

            rows_resume = [
                ("── PARAMÈTRES ──", ""),
                ("N simulations",          stats["n_runs"]),
                ("Incertitude cadences",   f"±{INCERTITUDE*100:.0f}%"),
                ("Distribution tirages",   "Uniforme indépendante par machine"),
                ("B2 activé (retards)",    ACTIVER_B2),
                ("B4 activé (campagnes)",  ACTIVER_B4),
                ("Graine aléatoire",       GRAINE_ALEATOIRE),
                ("", ""),
                ("── FAISABILITÉ ──", ""),
                ("Runs total",             stats["n_runs"]),
                ("Solutions trouvées",     stats["n_faisables"]),
                ("Taux faisabilité (%)",   round(stats["taux_faisabilite"], 1)),
                ("Infaisables",            stats["n_infaisables"]),
                ("Plan baseline inchangé valide", stats["n_plan_ok"]),
                ("Taux plan baseline OK (%)", round(stats["taux_plan_ok"], 1)),
                ("", ""),
                ("── DISTRIBUTION MARGE RE-OPTIMISÉE (MAD) ──", ""),
                ("Référence baseline",     round(ref_marge, 0)),
                ("Moyenne Monte Carlo",    round(stats["marge_moy"], 0) if stats["marge_moy"] else None),
                ("Écart-type",             round(stats["marge_std"], 0) if stats["marge_std"] else None),
                ("Minimum absolu",         round(stats["marge_min"], 0) if stats["marge_min"] else None),
                ("Maximum absolu",         round(stats["marge_max"], 0) if stats["marge_max"] else None),
                ("Percentile 5%  (P5)",    round(stats["marge_p5"],  0) if stats["marge_p5"]  else None),
                ("Percentile 10% (P10)",   round(stats["marge_p10"], 0) if stats["marge_p10"] else None),
                ("Percentile 25% (Q1)",    round(stats["marge_p25"], 0) if stats["marge_p25"] else None),
                ("Percentile 95% (P95)",   round(stats["marge_p95"], 0) if stats["marge_p95"] else None),
                ("", ""),
                ("── MARGE DE SÉCURITÉ ──", ""),
                ("Marge de sécurité P10 (MAD)", round(ms, 0) if ms else None),
                ("Coussin recommandé (%)",       pct),
                ("Interprétation",               interpretation),
            ]
            pd.DataFrame(rows_resume, columns=["Indicateur", "Valeur"]) \
              .to_excel(writer, sheet_name="Résumé", index=False)

            # ══════════════════════════════════════════════════════════════
            # ONGLET 2 — DÉTAIL COMPLET DE TOUS LES RUNS
            # ══════════════════════════════════════════════════════════════
            rows_detail = []
            for r in resultats:
                row = {
                    "Sim"          : r["sim"],
                    "Statut"       : r["statut"],
                    "Marge (MAD)"  : round(r["marge"], 0) if r["marge"] else None,
                    "Δ Marge (MAD)": round(r["delta_marge"], 0) if r["delta_marge"] else None,
                    "Rang marge"   : None,   # rempli après
                    "Commandes acc": r["n_acceptees"],
                    "Taux svc %"   : round(r["taux_service"], 1) if r["taux_service"] else None,
                    "Nb refusées"  : len(r["refused"]),
                    "Commandes refusées": ", ".join(r["refused"]) if r["refused"] else "—",
                    "Nb violations plan": r["n_violations"],
                    "Temps (s)"    : round(r["wall_time"], 0),
                }
                for mach in MACHINES:
                    row[f"Facteur_{mach}"] = round(r["facteurs"].get(mach, 1.0), 4)
                rows_detail.append(row)

            df_detail = pd.DataFrame(rows_detail)
            # Rang marge (1 = meilleure marge)
            if "Marge (MAD)" in df_detail.columns:
                df_detail["Rang marge"] = df_detail["Marge (MAD)"].rank(ascending=False)
            df_detail.to_excel(writer, sheet_name="Détail_runs", index=False)

            # ══════════════════════════════════════════════════════════════
            # ONGLET 3 — CONFIGURATION DU RUN AVEC LA MARGE LA PLUS BASSE
            # ══════════════════════════════════════════════════════════════
            if runs_valides:
                run_min = min(runs_valides, key=lambda r: r["marge"])
                rows_min = [
                    ("── CONFIGURATION RUN MARGE MINIMALE ──", ""),
                    ("Numéro simulation",   run_min["sim"]),
                    ("Statut",             run_min["statut"]),
                    ("Marge (MAD)",        round(run_min["marge"], 0)),
                    ("Δ vs baseline (MAD)", round(run_min["delta_marge"], 0)),
                    ("Commandes acceptées", run_min["n_acceptees"]),
                    ("Commandes refusées",  ", ".join(run_min["refused"]) if run_min["refused"] else "—"),
                    ("Violations plan",     run_min["n_violations"]),
                    ("", ""),
                    ("── FACTEURS DE CADENCE ──", ""),
                ]
                for mach in MACHINES:
                    f = run_min["facteurs"].get(mach, 1.0)
                    ecart = (f - 1.0) * 100
                    rows_min.append((f"Facteur {mach}", f"{f:.4f}  ({ecart:+.1f}%)"))
                rows_min.append(("", ""))
                rows_min.append(("── VIOLATIONS DE CAPACITÉ ──", ""))
                if run_min["violations"]:
                    for (mach, fam, t), info in run_min["violations"].items():
                        rows_min.append((
                            f"{mach}/{fam}/S{t}",
                            f"Charge={info['charge']:.0f}T  Capacité={info['capacite']:.0f}T  "
                            f"Dépassement={info['depassement']:.0f}T"
                        ))
                else:
                    rows_min.append(("Aucune violation", "Plan baseline faisable"))
                rows_min.append(("", ""))
                rows_min.append(("── INTERPRÉTATION ──", ""))
                rows_min.append((
                    "Pourquoi cette marge est la plus basse ?",
                    "Ces facteurs de cadence ont le plus réduit la capacité disponible, "
                    "forçant le modèle à refuser davantage de commandes ou à sous-charger les lignes."
                ))
                pd.DataFrame(rows_min, columns=["Indicateur", "Valeur"]) \
                  .to_excel(writer, sheet_name="Config_marge_MIN", index=False)

            # ══════════════════════════════════════════════════════════════
            # ONGLET 4 — CONFIGURATION DU RUN AVEC LA MARGE LA PLUS HAUTE
            # ══════════════════════════════════════════════════════════════
            if runs_valides:
                run_max = max(runs_valides, key=lambda r: r["marge"])
                rows_max = [
                    ("── CONFIGURATION RUN MARGE MAXIMALE ──", ""),
                    ("Numéro simulation",   run_max["sim"]),
                    ("Statut",             run_max["statut"]),
                    ("Marge (MAD)",        round(run_max["marge"], 0)),
                    ("Δ vs baseline (MAD)", round(run_max["delta_marge"], 0)),
                    ("Commandes acceptées", run_max["n_acceptees"]),
                    ("Commandes refusées",  ", ".join(run_max["refused"]) if run_max["refused"] else "—"),
                    ("Violations plan",     run_max["n_violations"]),
                    ("", ""),
                    ("── FACTEURS DE CADENCE ──", ""),
                ]
                for mach in MACHINES:
                    f = run_max["facteurs"].get(mach, 1.0)
                    ecart = (f - 1.0) * 100
                    rows_max.append((f"Facteur {mach}", f"{f:.4f}  ({ecart:+.1f}%)"))
                rows_max.append(("", ""))
                rows_max.append(("── INTERPRÉTATION ──", ""))
                rows_max.append((
                    "Pourquoi cette marge est la plus haute ?",
                    "Des cadences légèrement supérieures sur les machines goulots "
                    "ont permis d'accepter plus de commandes ou de mieux charger les lignes."
                ))
                pd.DataFrame(rows_max, columns=["Indicateur", "Valeur"]) \
                  .to_excel(writer, sheet_name="Config_marge_MAX", index=False)

            # ══════════════════════════════════════════════════════════════
            # ONGLET 5 — IMPACT DES MACHINES SUR LA MARGE (corrélation)
            # ══════════════════════════════════════════════════════════════
            if runs_valides:
                rows_impact = []
                marges_mc = [r["marge"] for r in runs_valides]
                for mach in MACHINES:
                    facteurs_mach = [r["facteurs"].get(mach, 1.0) for r in runs_valides]
                    corr = float(np.corrcoef(facteurs_mach, marges_mc)[0, 1]) \
                           if len(facteurs_mach) >= 3 else 0.0

                    # Sensibilité : combien de MAD de marge pour +1% de cadence ?
                    if len(facteurs_mach) >= 3:
                        z = np.polyfit(facteurs_mach, marges_mc, 1)
                        sensibilite = z[0] * 0.01   # pente × 1% = MAD gagné par +1%
                    else:
                        sensibilite = 0.0

                    # Nombre de violations impliquant cette machine
                    nb_viol_mach = sum(
                        1 for r in resultats
                        for (m, f, t) in r["violations"] if m == mach
                    )

                    if abs(corr) >= 0.5:
                        niveau = "CRITIQUE"
                    elif abs(corr) >= 0.25:
                        niveau = "Modéré"
                    else:
                        niveau = "Faible"

                    rows_impact.append({
                        "Machine"                   : mach,
                        "Corrélation Pearson (r)"   : round(corr, 4),
                        "Niveau impact"             : niveau,
                        "Sensibilité (MAD/+1% cad.)": round(sensibilite, 0),
                        "Nb violations plan"        : nb_viol_mach,
                        "Fréquence violation (%)"   : round(100 * nb_viol_mach / len(resultats), 1),
                        "Interprétation"            : (
                            f"+1% de cadence {mach} → {sensibilite/1000:+.0f} kMAD de marge"
                            if sensibilite != 0 else "Impact non mesurable"
                        ),
                    })

                df_impact = pd.DataFrame(rows_impact)
                df_impact = df_impact.sort_values("Corrélation Pearson (r)",
                                                   key=abs, ascending=False)
                df_impact.to_excel(writer, sheet_name="Impact_machines", index=False)

            # ══════════════════════════════════════════════════════════════
            # ONGLET 6 — VIOLATIONS DÉTAILLÉES
            # ══════════════════════════════════════════════════════════════
            rows_viol = []
            for r in resultats:
                for (mach, fam, t), info in r["violations"].items():
                    rows_viol.append({
                        "Simulation"         : r["sim"],
                        "Marge ce run (MAD)" : round(r["marge"], 0) if r["marge"] else None,
                        "Machine"            : mach,
                        "Famille"            : fam,
                        "Semaine"            : t,
                        "Charge planifiée (T)": info["charge"],
                        "Capacité disponible (T)": info["capacite"],
                        "Dépassement (T)"    : info["depassement"],
                        "Dépassement (%)"    : round(100 * info["depassement"] / info["capacite"], 1)
                                               if info["capacite"] > 0 else None,
                        "Facteur cadence"    : info["facteur"],
                        "Réduction cadence (%)": round((1 - info["facteur"]) * 100, 1),
                    })
            if rows_viol:
                df_viol = pd.DataFrame(rows_viol)
                df_viol = df_viol.sort_values("Dépassement (T)", ascending=False)
                df_viol.to_excel(writer, sheet_name="Violations_detail", index=False)

            # ══════════════════════════════════════════════════════════════
            # ONGLET 7 — COMMANDES FRAGILES (profil complet)
            # ══════════════════════════════════════════════════════════════
            compteur_refus = {}
            for r in resultats:
                for i in r["refused"]:
                    compteur_refus[i] = compteur_refus.get(i, 0) + 1

            rows_cmdes = []
            for cmd_id, nb in sorted(compteur_refus.items(),
                                      key=lambda x: x[1], reverse=True):
                c = cmd_data.get(cmd_id, {})
                rows_cmdes.append({
                    "Commande"          : cmd_id,
                    "Nb refus MC"       : nb,
                    "Fréquence refus (%)": round(100 * nb / len(resultats), 1),
                    "Refusée au baseline": "OUI" if (refused_base is not None and cmd_id in refused_base) else "—",
                    "Famille"           : c.get("famille", "—"),
                    "Grade"             : c.get("grade", "—"),
                    "Épaisseur (mm)"    : c.get("epaisseur", "—"),
                    "Tonnage (T)"       : c.get("tonnage", "—"),
                    "Prix vente (MAD/T)": c.get("prix", "—"),
                    "Semaine livraison" : c.get("semaine_liv", "—"),
                    "Priorité"          : c.get("priorite", "—"),
                    "Interprétation"    : (
                        "Commande structurellement fragile : "
                        "sa marge nette est insuffisante dès que les capacités baissent légèrement."
                        if nb >= 0.5 * len(resultats) else
                        "Commande marginalement fragile : "
                        "acceptée dans la plupart des scénarios."
                    ),
                })
            if rows_cmdes:
                pd.DataFrame(rows_cmdes).to_excel(
                    writer, sheet_name="Commandes_fragiles", index=False)

            # ══════════════════════════════════════════════════════════════
            # ONGLET 8 — MACHINES CRITIQUES (fréquence violation)
            # ══════════════════════════════════════════════════════════════
            compteur_viol = {}
            depassement_moy = {}
            for r in resultats:
                for (mach, fam, t), info in r["violations"].items():
                    cle = f"{mach}/{fam}/S{t}"
                    compteur_viol[cle] = compteur_viol.get(cle, 0) + 1
                    if cle not in depassement_moy:
                        depassement_moy[cle] = []
                    depassement_moy[cle].append(info["depassement"])

            rows_crit = []
            for cle, nb in sorted(compteur_viol.items(),
                                   key=lambda x: x[1], reverse=True):
                parts = cle.split("/")
                rows_crit.append({
                    "Point plan (Machine/Famille/Semaine)": cle,
                    "Machine"               : parts[0] if len(parts) > 0 else "—",
                    "Famille"               : parts[1] if len(parts) > 1 else "—",
                    "Semaine"               : parts[2] if len(parts) > 2 else "—",
                    "Nb violations"         : nb,
                    "Fréquence (%)"         : round(100 * nb / len(resultats), 1),
                    "Dépassement moy (T)"   : round(np.mean(depassement_moy[cle]), 1),
                    "Dépassement max (T)"   : round(np.max(depassement_moy[cle]), 1),
                    "Niveau criticité"      : (
                        "CRITIQUE" if nb >= 0.5 * len(resultats) else
                        "Modéré"   if nb >= 0.25 * len(resultats) else "Faible"
                    ),
                    "Recommandation"        : (
                        "Réduire la charge planifiée sur ce point ou augmenter la cadence nominale."
                        if nb >= 0.5 * len(resultats) else
                        "Surveiller ce point en production réelle."
                    ),
                })
            if rows_crit:
                pd.DataFrame(rows_crit).to_excel(
                    writer, sheet_name="Machines_critiques", index=False)

            # ══════════════════════════════════════════════════════════════
            # ONGLET 9 — DISTRIBUTION COMPLÈTE (déciles)
            # ══════════════════════════════════════════════════════════════
            marges_v = [r["marge"] for r in runs_valides]
            if marges_v:
                percentiles_vals = [0, 5, 10, 15, 20, 25, 30, 40, 50,
                                    60, 70, 75, 80, 85, 90, 95, 100]
                rows_pct = []
                for p in percentiles_vals:
                    val = np.percentile(marges_v, p)
                    delta_p = val - ref_marge
                    rows_pct.append({
                        "Percentile"        : f"P{p}",
                        "Marge (MAD)"       : round(val, 0),
                        "Δ vs baseline (MAD)": round(delta_p, 0),
                        "Δ vs baseline (%)" : round(100 * delta_p / ref_marge, 2),
                        "Interprétation"    : (
                            f"Dans {100-p}% des scénarios, la marge dépasse {val/1e6:.3f} M MAD"
                            if p <= 50 else
                            f"Dans {p}% des scénarios, la marge est inférieure à {val/1e6:.3f} M MAD"
                        ),
                    })
                pd.DataFrame(rows_pct).to_excel(
                    writer, sheet_name="Distribution_percentiles", index=False)

        print(f"  ✅ {nom}  ({len(runs_valides)} runs valides, 9 onglets)")
        return nom

    except Exception as e:
        print(f"  ⚠️  Erreur export Excel : {e}")
        import traceback; traceback.print_exc()
        return None


# ============================================================
# SECTION 9 — GRAPHIQUES MATPLOTLIB (PNG pour rapport)
# ============================================================

"""def generer_graphiques(resultats, stats, ref_marge, timestamp):
    
    Génère 4 graphiques PNG haute résolution pour le rapport.

    G1 — Histogramme distribution des marges (baseline, P5, P10)
    G2 — Evolution run par run + delta marge
    G3 — Fréquence violations capacité par machine/famille/semaine
    G4 — Corrélation facteur cadence machine vs marge (7 sous-figures)
   
    marges_valides = [r["marge"]       for r in resultats if r["marge"] is not None]
    sims_valides   = [r["sim"]         for r in resultats if r["marge"] is not None]
    deltas_valides = [r["delta_marge"] for r in resultats if r["marge"] is not None]

    C_BLEU   = "#2c7bb6"
    C_ROUGE  = "#d7191c"
    C_VERT   = "#1a9641"
    C_ORANGE = "#ff7f00"
    C_GRID   = "#e8e8e8"
    fichiers = []

    # ── G1 : Histogramme distribution des marges ──────────────────────────
    fig, ax = plt.subplots(figsize=(10, 6))
    fig.patch.set_facecolor("white")
    n_bins = min(15, max(5, len(marges_valides) // 3))
    ax.hist(marges_valides, bins=n_bins, color=C_BLEU,
            alpha=0.75, edgecolor="white", linewidth=0.8, zorder=3)
    ax.axvline(ref_marge, color=C_VERT, linewidth=2.5, linestyle="--",
               label=f"Baseline : {ref_marge/1e6:.2f} M MAD", zorder=4)
    if stats["marge_p10"]:
        ax.axvline(stats["marge_p10"], color=C_ROUGE, linewidth=2.5, linestyle="--",
                   label=f"P10 : {stats['marge_p10']/1e6:.2f} M MAD", zorder=4)
        ax.axvspan(stats["marge_p10"], ref_marge, alpha=0.12,
                   color=C_ROUGE, label="Zone marge de sécurité")
    if stats["marge_p5"]:
        ax.axvline(stats["marge_p5"], color=C_ORANGE, linewidth=1.8, linestyle=":",
                   label=f"P5 : {stats['marge_p5']/1e6:.2f} M MAD", zorder=4)
    ax.set_xlabel("Marge re-optimisée (MAD)", fontsize=12)
    ax.set_ylabel("Nombre de simulations", fontsize=12)
    ax.set_title(
        f"Distribution des marges — Monte Carlo ±{INCERTITUDE*100:.0f}% cadences\n"
        f"({len(marges_valides)} simulations valides / {len(resultats)})",
        fontsize=13, fontweight="bold")
    ax.legend(fontsize=10, framealpha=0.9)
    ax.grid(axis="y", color=C_GRID, zorder=0)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x/1e6:.1f}M"))
    if stats["marge_securite_recommandee"]:
        ms  = stats["marge_securite_recommandee"]
        pct = 100 * ms / ref_marge
        ax.text(0.02, 0.97,
                f"Marge de sécurité recommandée :\n{ms/1e6:.2f} M MAD ({pct:.1f}%)",
                transform=ax.transAxes, fontsize=10, verticalalignment="top",
                bbox=dict(boxstyle="round,pad=0.4", facecolor="#fff3cd",
                          edgecolor="#ffc107", alpha=0.9))
    plt.tight_layout()
    f1 = f"B9_1_distribution_marges_{timestamp}.png"
    plt.savefig(f1, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    fichiers.append(f1)
    print(f"    G1 -> {f1}")

    # ── G2 : Evolution run par run ─────────────────────────────────────────
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    fig.patch.set_facecolor("white")
    couleurs_pts = [C_VERT if m >= ref_marge else C_ROUGE for m in marges_valides]
    ax1.scatter(sims_valides, [m/1e6 for m in marges_valides],
                c=couleurs_pts, s=40, zorder=4, alpha=0.85)
    ax1.plot(sims_valides, [m/1e6 for m in marges_valides],
             color=C_BLEU, linewidth=0.8, alpha=0.5, zorder=3)
    ax1.axhline(ref_marge/1e6, color=C_VERT, linewidth=2, linestyle="--",
                label=f"Baseline ({ref_marge/1e6:.2f}M)")
    if stats["marge_p10"]:
        ax1.axhline(stats["marge_p10"]/1e6, color=C_ROUGE, linewidth=1.5, linestyle="--",
                    label=f"P10 ({stats['marge_p10']/1e6:.2f}M)")
    ax1.set_ylabel("Marge (M MAD)", fontsize=11)
    ax1.set_title("Evolution de la marge par simulation Monte Carlo",
                  fontsize=13, fontweight="bold")
    ax1.legend(fontsize=9)
    ax1.grid(color=C_GRID)
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.1f}M"))
    couleurs_delta = [C_VERT if d >= 0 else C_ROUGE for d in deltas_valides]
    ax2.bar(sims_valides, [d/1e6 for d in deltas_valides],
            color=couleurs_delta, alpha=0.75, zorder=3)
    ax2.axhline(0, color="black", linewidth=1, zorder=4)
    ax2.set_xlabel("Numéro de simulation", fontsize=11)
    ax2.set_ylabel("Δ Marge vs baseline (M MAD)", fontsize=11)
    ax2.set_title("Ecart à la marge de référence", fontsize=11)
    ax2.grid(axis="y", color=C_GRID)
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:+.1f}M"))
    p_ok    = mpatches.Patch(color=C_VERT,  label="Au-dessus du baseline")
    p_alert = mpatches.Patch(color=C_ROUGE, label="En dessous du baseline")
    ax2.legend(handles=[p_ok, p_alert], fontsize=9)
    plt.tight_layout()
    f2 = f"B9_2_evolution_runs_{timestamp}.png"
    plt.savefig(f2, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    fichiers.append(f2)
    print(f"    G2 -> {f2}")

    # ── G3 : Fréquence violations ──────────────────────────────────────────
    if stats["machines_critiques"]:
        labels_v = [k for k, _ in stats["machines_critiques"]]
        freqs_v  = [100.0 * v / len(resultats) for _, v in stats["machines_critiques"]]
        fig, ax = plt.subplots(figsize=(10, 5))
        fig.patch.set_facecolor("white")
        coul_b = [C_ROUGE if f >= 50 else C_ORANGE if f >= 25 else C_BLEU for f in freqs_v]
        bars = ax.barh(labels_v[::-1], freqs_v[::-1],
                       color=coul_b[::-1], alpha=0.8, edgecolor="white")
        for bar, freq in zip(bars, freqs_v[::-1]):
            ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2,
                    f"{freq:.0f}%", va="center", fontsize=9)
        ax.axvline(50, color=C_ROUGE, linewidth=1.5, linestyle="--", alpha=0.7)
        ax.set_xlabel("Fréquence de violation (%)", fontsize=11)
        ax.set_title(
            "Points de fragilité du plan : fréquence de violation de capacité\n"
            "(plan baseline maintenu fixe, cadences perturbées)",
            fontsize=12, fontweight="bold")
        ax.set_xlim(0, max(freqs_v) * 1.15)
        ax.grid(axis="x", color=C_GRID)
        pr = mpatches.Patch(color=C_ROUGE,  label="Violation >= 50% des runs")
        po = mpatches.Patch(color=C_ORANGE, label="Violation 25-50%")
        pb = mpatches.Patch(color=C_BLEU,   label="Violation < 25%")
        ax.legend(handles=[pr, po, pb], fontsize=9, loc="lower right")
        plt.tight_layout()
        f3 = f"B9_3_violations_capacite_{timestamp}.png"
        plt.savefig(f3, dpi=150, bbox_inches="tight", facecolor="white")
        plt.close()
        fichiers.append(f3)
        print(f"    G3 -> {f3}")

    # ── G4 : Corrélation facteur machine vs marge (7 sous-figures) ────────
    runs_valides = [r for r in resultats if r["marge"] is not None]
    if runs_valides:
        fig = plt.figure(figsize=(14, 10))
        fig.patch.set_facecolor("white")
        fig.suptitle(
            "Corrélation : facteur de cadence par machine vs marge re-optimisée\n"
            "(chaque point = 1 simulation | r = corrélation de Pearson)",
            fontsize=13, fontweight="bold", y=0.98)
        gs = GridSpec(2, 4, figure=fig, hspace=0.45, wspace=0.35)
        for idx, mach in enumerate(MACHINES):
            ax = fig.add_subplot(gs[idx // 4, idx % 4])
            fx = [r["facteurs"].get(mach, 1.0)  for r in runs_valides]
            fy = [r["marge"] / 1e6               for r in runs_valides]
            corr = np.corrcoef(fx, fy)[0, 1] if len(fx) >= 3 else 0.0
            cc = C_ROUGE if abs(corr) >= 0.5 else C_ORANGE if abs(corr) >= 0.25 else C_BLEU
            ax.scatter(fx, fy, color=cc, s=25, alpha=0.7, zorder=3)
            if len(fx) >= 3:
                z = np.polyfit(fx, fy, 1)
                xl = np.linspace(min(fx), max(fx), 50)
                ax.plot(xl, np.poly1d(z)(xl), color="black",
                        linewidth=1.2, linestyle="--", alpha=0.6)
            ax.axhline(ref_marge/1e6, color=C_VERT, linewidth=0.8, linestyle=":", alpha=0.7)
            gras = "bold" if abs(corr) >= 0.4 else "normal"
            ax.set_title(f"{mach}  r={corr:+.2f}", fontsize=10, fontweight=gras)
            ax.set_xlabel("Facteur cadence", fontsize=8)
            if idx % 4 == 0:
                ax.set_ylabel("Marge (M MAD)", fontsize=8)
            ax.tick_params(labelsize=7)
            ax.grid(color=C_GRID, linewidth=0.5)
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.1f}M"))
        fig.add_subplot(gs[1, 3]).set_visible(False)
        plt.tight_layout()
        f4 = f"B9_4_correlations_machines_{timestamp}.png"
        plt.savefig(f4, dpi=150, bbox_inches="tight", facecolor="white")
        plt.close()
        fichiers.append(f4)
        print(f"    G4 -> {f4}")

    return fichiers
 """

# ============================================================
# SECTION 9 — MAIN
# ============================================================

# Variable globale pour partager data_ref entre les fonctions
data_ref = None

def main():
    global data_ref
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("=" * 70)
    print("  ANALYSE DE ROBUSTESSE — MONTE CARLO — MAGHREB STEEL (B9)")
    print(f"  {N_SIMULATIONS} simulations | ±{INCERTITUDE*100:.0f}% cadences | "
          f"B2={ACTIVER_B2} | B4={ACTIVER_B4}")
    print(f"  Lancée le : {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 70)

    # ── Chargement des données ───────────────────────────────────────────────
    print("\n[1] Chargement des données...")
    old = sys.stdout; sys.stdout = io.StringIO()
    data_ref = charger_donnees()
    sys.stdout = old
    print(f"    {len(data_ref['I'])} commandes | {len(data_ref['G'])} grades | "
          f"{len(data_ref['M'])} machines | {len(data_ref['T'])} semaines")

    # ── Run baseline ─────────────────────────────────────────────────────────
    print("\n[2] Résolution du baseline (cadences nominales)...")
    m_base, _, _ = construire_silencieux(data_ref)
    marge_base, n_acc_base, taux_base, refused_base, statut_base, t_base = \
        resoudre_silencieux(m_base, time_limit=3600)

    if marge_base is None:
        print("⛔ Baseline échoué. Vérifiez que highspy est installé.")
        return

    print(f"    Statut   : {statut_base}")
    print(f"    Marge    : {marge_base:,.0f} MAD")
    print(f"    Acceptées: {n_acc_base} / {len(data_ref['I'])}")
    print(f"    Refusées : {len(refused_base)} — {refused_base}")
    print(f"    Temps    : {t_base:.0f}s")

    # ── Extraction du plan baseline ──────────────────────────────────────────
    print("\n[3] Extraction du plan de production baseline...")
    plan_baseline = extraire_plan_baseline(m_base, data_ref)
    print(f"    {len(plan_baseline)} combinaisons (machine, famille, semaine) actives")

    del m_base
    gc.collect()

    # ── Monte Carlo ──────────────────────────────────────────────────────────
    print("\n[4] Simulation Monte Carlo...")
    debut_mc = time.time()
    resultats = lancer_monte_carlo(data_ref, None, plan_baseline, marge_base)
    duree_mc  = time.time() - debut_mc
    print(f"\n    Monte Carlo terminé en {duree_mc/60:.1f} minutes")

    # ── Statistiques ─────────────────────────────────────────────────────────
    print("\n[5] Calcul des statistiques de robustesse...")
    stats = calculer_statistiques(resultats, marge_base)

    # ── Affichage ────────────────────────────────────────────────────────────
    afficher_resultats(stats, marge_base)

    # ── Graphiques ───────────────────────────────────────────────────────────
    """print("[6] Génération des graphiques PNG...")
    fichiers_png = generer_graphiques(resultats, stats, marge_base, timestamp)
    """

    # ── Export Excel ─────────────────────────────────────────────────────────
    print("[7] Export Excel...")
    exporter_excel(resultats, stats, marge_base, timestamp, data_ref=data_ref, refused_base=refused_base)

    print("\n" + "=" * 70)
    print("  ANALYSE TERMINÉE")
    print(f"  Durée totale : {(time.time() - debut_mc)/60:.1f} minutes")
    """print(f"  Fichiers générés :")
    for f in fichiers_png:
        print(f"    {f}") 
    """
    print("=" * 70)


if __name__ == "__main__":
    main()