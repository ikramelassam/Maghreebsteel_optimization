"""
etude_sensibilite_E20_corrige_v2.py
Étude de sensibilité - Scénario E20 : HRC plus cher (+10%)
Extraction des shadow prices par fixation des binaires sur le modèle résolu
"""

import pyomo.environ as pyo
from pyomo.contrib.appsi.solvers import Highs
from pyomo.environ import Suffix
from data_loader1 import charger_donnees
from model1 import construire_modele
import pandas as pd
import time
import copy
from datetime import datetime


def resoudre_modele_avec_duaux(data, modifier_parametres=None, time_limit=700):
    """
    Résout le MILP, puis fixe les binaires sur le MÊME modèle et relance en LP.
    """
    
    data_scenario = copy.deepcopy(data)
    if modifier_parametres:
        modifier_parametres(data_scenario)
    
    print("  Construction du modèle...")
    m, IP, IPM = construire_modele(data_scenario, activer_B2=True, activer_B4=True)
    
    # --- Résolution MILP ---
    print("  Résolution MILP...")
    solver = Highs()
    solver.config.time_limit = time_limit
    solver.config.stream_solver = False
    
    start_time = time.time()
    results = solver.solve(m)
    wall_time = time.time() - start_time
    
    if results.termination_condition != "optimal":
        print(f"    ⚠️ Pas de solution optimale : {results.termination_condition}")
        marge = pyo.value(m.obj) if pyo.value(m.obj) else 0
        return m, marge, {}, [], results.termination_condition, wall_time
    
    marge_milp = pyo.value(m.obj)
    print(f"    Statut MILP : {results.termination_condition}")
    print(f"    Marge MILP : {marge_milp:,.0f} MAD")
    
    # --- Fixer les binaires sur le MÊME modèle ---
    print("  Fixation des binaires sur le modèle résolu...")
    
    # Compter combien de binaires sont fixées
    nb_fixees = 0
    
    # Fixer y
    for i in data_scenario["I"]:
        val = pyo.value(m.y[i])
        if val is not None:
            m.y[i].fix(round(val))
            nb_fixees += 1
    
    # Fixer z (si B2 actif)
    if hasattr(m, 'z'):
        for i in data_scenario["I"]:
            for r in data_scenario["R"]:
                val = pyo.value(m.z[i, r])
                if val is not None:
                    m.z[i, r].fix(round(val))
                    nb_fixees += 1
    
    # Fixer w (si B4 actif)
    if hasattr(m, 'w'):
        for mach in data_scenario["M"]:
            for f in data_scenario["F"]:
                for t in data_scenario["T"]:
                    val = pyo.value(m.w[mach, f, t])
                    if val is not None:
                        m.w[mach, f, t].fix(round(val))
                        nb_fixees += 1
    
    print(f"    {nb_fixees} variables binaires fixées")
    
    # --- Activer les suffixes pour les duals ---
    m.dual = Suffix(direction=Suffix.IMPORT)
    
    # --- Résolution LP (binaires fixées) ---
    print("  Résolution LP (binaires fixées)...")
    solver_lp = Highs()
    solver_lp.config.time_limit = 120
    solver_lp.config.stream_solver = False
    results_lp = solver_lp.solve(m)
    
    marge_lp = pyo.value(m.obj)
    print(f"    Marge LP : {marge_lp:,.0f} MAD")
    print(f"    Statut LP : {results_lp.termination_condition}")
    
    # Vérification de cohérence
    if abs(marge_milp - marge_lp) > 1000:
        print(f"    ⚠️ Écart important : {marge_milp:.0f} -> {marge_lp:.0f} MAD")
        print(f"    → Vérifier que les binaires sont bien fixées")
    else:
        print(f"    ✅ Objectif conservé : {marge_lp:,.0f} MAD")
    
    # --- Extraire les shadow prices ---
    shadow_prices = {}
    for g in data_scenario["G"]:
        try:
            if hasattr(m, 'c3a_limite_achat'):
                shadow_prices[g] = pyo.value(m.dual[m.c3a_limite_achat[g]])
            else:
                shadow_prices[g] = 0
        except (KeyError, AttributeError):
            shadow_prices[g] = 0
    
    print(f"    Shadow prices : {shadow_prices}")
    
    # Extraire les commandes acceptées
    commandes_acceptees = []
    for i in data_scenario["I"]:
        val = pyo.value(m.y[i])
        if val is not None and val > 0.5:
            commandes_acceptees.append(i)
    
    print(f"    Commandes acceptées : {len(commandes_acceptees)} / {len(data_scenario['I'])}")
    
    return m, marge_lp, shadow_prices, commandes_acceptees, results.termination_condition, wall_time


def scenario_hrc_plus_cher(data):
    """E20 : Augmentation de 10% du prix HRC"""
    prix_hrc = data["prix_hrc"]
    nouveaux_prix = {}
    for (grade, largeur), prix in prix_hrc.items():
        nouveaux_prix[(grade, largeur)] = prix * 1.10
    data["prix_hrc"] = nouveaux_prix


def extraire_consommations_hrc(m, data):
    """Extrait les consommations HRC par grade"""
    consommations = {}
    for g in data["G"]:
        conso = 0
        for i in data["I"]:
            if data["commandes"][i]["grade"] == g and pyo.value(m.y[i]) > 0.5:
                for p in range(len(data["commandes"][i]["chemins"])):
                    for t in data["T"]:
                        val = pyo.value(m.x[i, p, "PK", t])
                        if val:
                            conso += val
        consommations[g] = conso
    return consommations


def main():
    print("="*70)
    print("ÉTUDE DE SENSIBILITÉ - SCÉNARIO E20")
    print("HRC plus cher : augmentation de 10% du prix")
    print("="*70)
    
    print("\nChargement des données...")
    data = charger_donnees()
    
    # ============================================================
    # RÉSOLUTION DE BASE
    # ============================================================
    print("\n" + "-"*50)
    print("RÉSOLUTION DE BASE (prix HRC nominaux)")
    print("-"*50)
    
    m_base, marge_base, shadow_prices_base, cmd_base, statut_base, time_base = resoudre_modele_avec_duaux(
        data, 
        modifier_parametres=None, 
        time_limit=700
    )
    
    print(f"\n  ✅ Résolution terminée")
    print(f"     Marge de base : {marge_base:,.0f} MAD")
    print(f"     Statut : {statut_base}")
    print(f"     Commandes acceptées : {len(cmd_base)} / {len(data['I'])}")
    print(f"     Temps : {time_base:.1f} s")
    
    conso_base = extraire_consommations_hrc(m_base, data)
    
    # Afficher les shadow prices
    print("\n  Shadow prices (C3a - disponibilité HRC) :")
    print(f"  {'Grade':<10} {'Shadow price (MAD/T)':<20} {'Consommation (T)':<15} {'Valeur marginale (MAD)':<20}")
    print("  " + "-"*65)
    
    total_valeur_marginale = 0
    for g in data["G"]:
        sp = shadow_prices_base.get(g, 0)
        conso = conso_base.get(g, 0)
        val_marg = sp * conso
        total_valeur_marginale += val_marg
        print(f"  {g:<10} {sp:>18.0f} {conso:>15.0f} {val_marg:>20,.0f}")
    
    print("  " + "-"*65)
    print(f"  Total valeur marginale : {total_valeur_marginale:,.0f} MAD")
    
    estimation_perte = 0.10 * total_valeur_marginale
    print(f"\n  📊 Estimation (shadow prices) : perte de {estimation_perte:,.0f} MAD")
    print(f"     Marge estimée après HRC+10% : {marge_base - estimation_perte:,.0f} MAD")
    
    # ============================================================
    # RÉSOLUTION AVEC HRC +10%
    # ============================================================
    print("\n" + "-"*50)
    print("RÉSOLUTION AVEC HRC +10%")
    print("-"*50)
    
    m_hrc, marge_hrc, shadow_prices_hrc, cmd_hrc, statut_hrc, time_hrc = resoudre_modele_avec_duaux(
        data,
        modifier_parametres=scenario_hrc_plus_cher,
        time_limit=700
    )
    
    print(f"\n  ✅ Résolution terminée")
    print(f"     Marge avec HRC+10% : {marge_hrc:,.0f} MAD")
    print(f"     Statut : {statut_hrc}")
    print(f"     Commandes acceptées : {len(cmd_hrc)} / {len(data['I'])}")
    print(f"     Temps : {time_hrc:.1f} s")
    
    # ============================================================
    # COMPARAISON
    # ============================================================
    print("\n" + "-"*50)
    print("COMPARAISON DES RÉSULTATS")
    print("-"*50)
    
    perte_reelle = marge_base - marge_hrc
    perte_estimee = estimation_perte
    
    print(f"\n  {'Indicateur':<30} {'Valeur':<20}")
    print("  " + "-"*50)
    print(f"  Marge de base              : {marge_base:>15,.0f} MAD")
    print(f"  Marge HRC+10%              : {marge_hrc:>15,.0f} MAD")
    print(f"  Perte réelle               : {perte_reelle:>15,.0f} MAD")
    print(f"  Perte estimée (shadow)     : {perte_estimee:>15,.0f} MAD")
    
    if perte_estimee > 0:
        ecart = abs(perte_reelle - perte_estimee)
        ecart_pct = (ecart / perte_reelle * 100) if perte_reelle != 0 else 0
        print(f"  Écart estimation/réel      : {ecart:>15,.0f} MAD ({ecart_pct:.1f}%)")
        qualite = "✅ EXCELLENTE" if ecart_pct < 5 else "🟡 BONNE" if ecart_pct < 10 else "⚠️ MOYENNE"
    else:
        print(f"  ⚠️ Shadow prices nuls - estimation impossible")
        qualite = "❌ Shadow prices nuls"
    
    print(f"\n  Qualité de l'estimation : {qualite}")
    
    # ============================================================
    # EXPORT EXCEL
    # ============================================================
    print("\n" + "-"*50)
    print("EXPORT DES RÉSULTATS")
    print("-"*50)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"E20_HRC_plus_cher_{timestamp}.xlsx"
    
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        
        df_resume = pd.DataFrame({
            "Indicateur": [
                "Marge de base (MAD)",
                "Marge HRC+10% (MAD)",
                "Perte réelle (MAD)",
                "Perte estimée par shadow prices (MAD)",
                "Commandes acceptées (base)",
                "Commandes acceptées (HRC+10%)",
                "Qualité estimation"
            ],
            "Valeur": [
                f"{marge_base:,.0f}",
                f"{marge_hrc:,.0f}",
                f"{perte_reelle:,.0f}",
                f"{perte_estimee:,.0f}" if perte_estimee > 0 else "N/A",
                len(cmd_base),
                len(cmd_hrc),
                qualite
            ]
        })
        df_resume.to_excel(writer, sheet_name="Resume", index=False)
        
        df_shadow = pd.DataFrame({
            "Grade": list(shadow_prices_base.keys()),
            "Shadow_price_MAD_T": list(shadow_prices_base.values()),
            "Consommation_T": [conso_base.get(g, 0) for g in shadow_prices_base.keys()]
        })
        df_shadow.to_excel(writer, sheet_name="Shadow_Prices", index=False)
    
    print(f"  ✅ Résultats exportés vers {filename}")
    
    # ============================================================
    # CONCLUSION
    # ============================================================
    print("\n" + "="*70)
    print("CONCLUSION E20")
    print("="*70)
    
    grades_sensibles = [g for g, sp in shadow_prices_base.items() if sp > 0]
    if grades_sensibles:
        recommandation = f"Les grades {', '.join(grades_sensibles)} sont les plus sensibles"
    else:
        recommandation = "⚠️ Shadow prices non disponibles"
    
    print(f"""
  📌 Une augmentation de 10% du prix HRC entraînerait :
     • Une perte de marge de {perte_reelle:,.0f} MAD ({perte_reelle/marge_base*100:.1f}%)
     • Un taux de service qui passerait de {len(cmd_base)/len(data['I'])*100:.1f}% à {len(cmd_hrc)/len(data['I'])*100:.1f}%

  💡 Estimation par shadow prices : {perte_estimee:,.0f} MAD
     {qualite}

  🔧 Recommandation : 
     • {recommandation}
     • Prioriser la sécurisation des approvisionnements sur ces grades
    """)
    
    print("="*70)
    print("FIN DE L'ÉTUDE E20")
    print("="*70)


if __name__ == "__main__":
    main()