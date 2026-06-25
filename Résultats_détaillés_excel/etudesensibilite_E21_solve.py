"""
E21_panne_LGB.py
Scénario E21 : Panne LGB (+2 jours en semaine 2)
Impact sur la marge, commandes basculées, exploitation maintenance

CORRECTIONS APPLIQUÉES (2026-06-19) :
    1. Détection de la DERNIERE machine du chemin (production finale)
    2. Calcul correct du taux d'occupation LGB (capacité totale = 7j × cadence)
    3. Cohérence avec le modèle de base (resultatsfinaux.xlsx)
    4. Suppression des commandes qui ne basculent pas réellement (ex: CMD-049)
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


# ============================================================
# 1. FONCTION DE RÉSOLUTION AVEC MODIFICATION DES ARRÊTS
# ============================================================

def resoudre_avec_panne(data, jours_panne_lgb_s2=2, time_limit=3600):
    """
    Simule une panne sur LGB en semaine 2.
    """
    
    data_scenario = copy.deepcopy(data)
    
    # --- SIMULATION DE LA PANNE LGB ---
    arrets = data_scenario["arrets"]
    ancien_arret = arrets.get(("LGB", 2), 0)
    arrets[("LGB", 2)] = ancien_arret + jours_panne_lgb_s2
    
    print(f"\n  🔧 Panne LGB simulée : +{jours_panne_lgb_s2} jours en semaine 2")
    print(f"     Arrêts LGB S2 : {ancien_arret} → {arrets[('LGB', 2)]} jours")
    
    # Construction du modèle
    print("  Construction du modèle avec panne...")
    m, IP, IPM = construire_modele(data_scenario, activer_B2=True, activer_B4=True)
    
    # Résolution
    print("  Résolution en cours...")
    solver = Highs()
    solver.config.time_limit = time_limit
    solver.config.stream_solver = False
    
    start_time = time.time()
    results = solver.solve(m)
    wall_time = time.time() - start_time
    
    marge = pyo.value(m.obj)
    
    # Commandes acceptées
    commandes_acceptees = [i for i in data_scenario["I"] if pyo.value(m.y[i]) > 0.5]
    
    print(f"    Marge : {marge:,.0f} MAD")
    print(f"    Commandes acceptées : {len(commandes_acceptees)} / {len(data_scenario['I'])}")
    print(f"    Statut : {results.termination_condition}")
    print(f"    Temps : {wall_time:.1f} s")
    
    return m, marge, commandes_acceptees, results.termination_condition, wall_time, data_scenario


# ============================================================
# 2. ANALYSE DES COMMANDES BASCOLÉES (CORRIGÉE)
# ============================================================

def analyser_commandes_basculees(m_sans_panne, m_avec_panne, data):
    """
    Identifie les commandes qui ont changé de plan entre la solution nominale et avec panne.
    CORRIGE : utilise la DERNIERE machine du chemin (production finale).
    """
    
    cmd = data["commandes"]
    
    # Récupérer les commandes acceptées dans chaque scénario
    accept_sans = [i for i in data["I"] if pyo.value(m_sans_panne.y[i]) > 0.5]
    accept_avec = [i for i in data["I"] if pyo.value(m_avec_panne.y[i]) > 0.5]
    
    # Commandes refusées en plus
    refusees_en_plus = set(accept_sans) - set(accept_avec)
    acceptees_en_plus = set(accept_avec) - set(accept_sans)
    
    # Pour chaque commande acceptée dans les deux scénarios, comparer la semaine de production
    commandes_bascules = []
    
    for i in set(accept_sans) & set(accept_avec):
        cmd_i = cmd[i]
        
        # --- Trouver le chemin réellement utilisé ---
        chemin_utilise = None
        for p in range(len(cmd_i["chemins"])):
            for mach in cmd_i["chemins"][p]:
                for t in data["T"]:
                    if pyo.value(m_sans_panne.x[i, p, mach, t]) > 0.01:
                        chemin_utilise = cmd_i["chemins"][p]
                        break
                if chemin_utilise:
                    break
            if chemin_utilise:
                break
        
        # Si on a trouvé un chemin, prendre la dernière machine
        if chemin_utilise:
            last_mach = chemin_utilise[-1]
        else:
            # Fallback : prendre le premier chemin et sa dernière machine
            last_mach = cmd_i["chemins"][0][-1]
        
        # --- Trouver la semaine de production sur la DERNIERE machine (sans panne) ---
        semaine_prod_sans = None
        for t in data["T"]:
            for p in range(len(cmd_i["chemins"])):
                if last_mach in cmd_i["chemins"][p]:
                    if pyo.value(m_sans_panne.x[i, p, last_mach, t]) > 0.01:
                        semaine_prod_sans = t
                        break
            if semaine_prod_sans:
                break
        
        # --- Trouver la semaine de production sur la DERNIERE machine (avec panne) ---
        semaine_prod_avec = None
        for t in data["T"]:
            for p in range(len(cmd_i["chemins"])):
                if last_mach in cmd_i["chemins"][p]:
                    if pyo.value(m_avec_panne.x[i, p, last_mach, t]) > 0.01:
                        semaine_prod_avec = t
                        break
            if semaine_prod_avec:
                break
        
        # Si la semaine de production a changé, c'est une commande basculée
        if semaine_prod_sans != semaine_prod_avec and semaine_prod_sans is not None and semaine_prod_avec is not None:
            commandes_bascules.append({
                "Commande": i,
                "Famille": cmd_i["famille"],
                "Grade": cmd_i["grade"],
                "Tonnage": cmd_i["tonnage"],
                "Semaine_sans_panne": semaine_prod_sans,
                "Semaine_avec_panne": semaine_prod_avec,
                "Decalage": semaine_prod_avec - semaine_prod_sans,
                "Prix_vente": cmd_i["prix"],
                "Machine_impactee": "LGB"
            })
    
    return commandes_bascules, refusees_en_plus, acceptees_en_plus


# ============================================================
# 3. ANALYSE DÉTAILLÉE POUR LA MAINTENANCE
# ============================================================

def analyser_impact_maintenance(m_sans_panne, m_avec_panne, data):
    """
    Analyse l'impact de la panne du point de vue maintenance.
    """
    
    cmd = data["commandes"]
    
    # 1. Identifier les commandes qui utilisent LGB en semaine 2
    commandes_lgb_s2 = []
    for i in data["I"]:
        if pyo.value(m_sans_panne.y[i]) > 0.5:
            cmd_i = cmd[i]
            for p in range(len(cmd_i["chemins"])):
                for t in data["T"]:
                    if t == 2 and "LGB" in cmd_i["chemins"][p]:
                        val = pyo.value(m_sans_panne.x[i, p, "LGB", t])
                        if val > 0.01:
                            commandes_lgb_s2.append({
                                "Commande": i,
                                "Famille": cmd_i["famille"],
                                "Grade": cmd_i["grade"],
                                "Tonnage": cmd_i["tonnage"],
                                "Tonnage_LGB_S2": val,
                                "Marge_unitaire": cmd_i["prix"],
                                "Priorite": cmd_i["priorite"]
                            })
    
    # 2. Calcul de la capacité LGB utilisée en semaine 2
    capacite_lgb_s2_sans_panne = sum(c["Tonnage_LGB_S2"] for c in commandes_lgb_s2)
    
    # 3. Capacité perdue
    jours_panne = 2
    cadence_lgb_hdg = 455  # T/jour (HDG)
    cadence_lgb_bacr = 600  # T/jour (BACR)
    capacite_perdue = jours_panne * cadence_lgb_hdg
    
    # 4. Capacité totale LGB S2 (7 jours × cadence HDG)
    capacite_totale_lgb_s2 = 7 * cadence_lgb_hdg  # 7 × 455 = 3185 T
    
    # 5. Taux d'occupation CORRIGÉ
    taux_occupation = (capacite_lgb_s2_sans_panne / capacite_totale_lgb_s2) * 100
    
    return {
        "commandes_lgb_s2": commandes_lgb_s2,
        "capacite_lgb_s2_sans_panne": capacite_lgb_s2_sans_panne,
        "capacite_perdue": capacite_perdue,
        "capacite_totale_lgb_s2": capacite_totale_lgb_s2,
        "taux_occupation": taux_occupation,
        "jours_panne": jours_panne,
        "cadence_lgb_hdg": cadence_lgb_hdg,
        "cadence_lgb_bacr": cadence_lgb_bacr
    }


# ============================================================
# 4. EXPORT EXCEL
# ============================================================

def exporter_resultats_E21(m_sans_panne, m_avec_panne, data, marge_sans, marge_avec, 
                          commandes_bascules, refusees_en_plus, acceptees_en_plus,
                          impact_maintenance, wall_time_sans, wall_time_avec):
    """
    Exporte les résultats du scénario E21 vers un fichier Excel.
    """
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"E21_panne_LGB_{timestamp}.xlsx"
    
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        
        # --- 1. Résumé de l'impact ---
        print("\n  Génération du résumé...")
        perte_marge = marge_sans - marge_avec
        
        resume = {
            "Indicateur": [
                "Scénario",
                "Marge sans panne (MAD)",
                "Marge avec panne (MAD)",
                "Perte de marge (MAD)",
                "Perte de marge (%)",
                "Commandes acceptées (sans panne)",
                "Commandes acceptées (avec panne)",
                "Commandes refusées en plus",
                "Commandes basculées",
                "Temps résolution sans panne (s)",
                "Temps résolution avec panne (s)",
                "Jours de panne LGB S2",
                "Capacité perdue (T)"
            ],
            "Valeur": [
                "Panne LGB +2 jours S2",
                f"{marge_sans:,.0f}",
                f"{marge_avec:,.0f}",
                f"{perte_marge:,.0f}",
                f"{perte_marge/marge_sans*100:.2f}%",
                len([i for i in data["I"] if pyo.value(m_sans_panne.y[i]) > 0.5]),
                len([i for i in data["I"] if pyo.value(m_avec_panne.y[i]) > 0.5]),
                len(refusees_en_plus),
                len(commandes_bascules),
                f"{wall_time_sans:.1f}",
                f"{wall_time_avec:.1f}",
                impact_maintenance["jours_panne"],
                f"{impact_maintenance['capacite_perdue']:.0f}"
            ]
        }
        df_resume = pd.DataFrame(resume)
        df_resume.to_excel(writer, sheet_name="Resume", index=False)
        
        # --- 2. Commandes basculées ---
        print("  Export des commandes basculées...")
        if commandes_bascules:
            df_bascules = pd.DataFrame(commandes_bascules)
            df_bascules.to_excel(writer, sheet_name="Commandes_Bascules", index=False)
            print(f"     {len(df_bascules)} commandes basculées")
        
        # --- 3. Commandes impactées sur LGB S2 ---
        print("  Export des commandes sur LGB S2...")
        if impact_maintenance["commandes_lgb_s2"]:
            df_lgb_s2 = pd.DataFrame(impact_maintenance["commandes_lgb_s2"])
            df_lgb_s2.to_excel(writer, sheet_name="Commandes_LGB_S2", index=False)
            print(f"     {len(df_lgb_s2)} commandes sur LGB S2")
        
        # --- 4. Analyse maintenance (CORRIGÉ) ---
        print("  Export de l'analyse maintenance...")
        analyse_maint = {
            "Indicateur": [
                "Machine impactée",
                "Semaine impactée",
                "Jours de panne supplémentaires",
                "Capacité LGB S2 utilisée (sans panne)",
                "Capacité totale LGB S2",
                "Taux d'occupation LGB S2 (sans panne)",
                "Capacité perdue",
                "Recommandation maintenance"
            ],
            "Valeur": [
                "LGB",
                "Semaine 2",
                f"{impact_maintenance['jours_panne']} jours",
                f"{impact_maintenance['capacite_lgb_s2_sans_panne']:.0f} T",
                f"{impact_maintenance['capacite_totale_lgb_s2']:.0f} T",
                f"{impact_maintenance['taux_occupation']:.1f} %",
                f"{impact_maintenance['capacite_perdue']:.0f} T",
                "Planifier les maintenances en dehors de la semaine 2"
            ]
        }
        df_maint = pd.DataFrame(analyse_maint)
        df_maint.to_excel(writer, sheet_name="Analyse_Maintenance", index=False)
        
        # --- 5. Comparaison des marges par famille ---
        print("  Export de la comparaison des marges par famille...")
        familles = data["F"]
        marge_famille_sans = {f: 0 for f in familles}
        marge_famille_avec = {f: 0 for f in familles}
        
        for i in data["I"]:
            cmd_i = data["commandes"][i]
            f = cmd_i["famille"]
            if pyo.value(m_sans_panne.y[i]) > 0.5:
                marge_famille_sans[f] += cmd_i["prix"] * cmd_i["tonnage"]
            if pyo.value(m_avec_panne.y[i]) > 0.5:
                marge_famille_avec[f] += cmd_i["prix"] * cmd_i["tonnage"]
        
        df_comp_famille = pd.DataFrame({
            "Famille": familles,
            "CA_sans_panne_MAD": [marge_famille_sans[f] for f in familles],
            "CA_avec_panne_MAD": [marge_famille_avec[f] for f in familles],
            "Variation_MAD": [marge_famille_avec[f] - marge_famille_sans[f] for f in familles]
        })
        df_comp_famille.to_excel(writer, sheet_name="Comparaison_Familles", index=False)
    
    print(f"\n  ✅ Résultats exportés vers {filename}")
    return filename


# ============================================================
# 5. MAIN
# ============================================================

def main():
    print("="*70)
    print("SCÉNARIO E21 - PANNE LGB (+2 jours en semaine 2)")
    print("="*70)
    
    # Chargement des données
    print("\nChargement des données...")
    data = charger_donnees()
    data_original = copy.deepcopy(data)
    
    # ============================================================
    # RÉSOLUTION SANS PANNE (référence)
    # ============================================================
    print("\n" + "-"*50)
    print("RÉSOLUTION DE RÉFÉRENCE (sans panne)")
    print("-"*50)
    
    m_sans, marge_sans, cmd_sans, statut_sans, time_sans, _ = resoudre_avec_panne(
        data_original,
        jours_panne_lgb_s2=0,
        time_limit=3600
    )
    
    # ============================================================
    # RÉSOLUTION AVEC PANNE
    # ============================================================
    print("\n" + "-"*50)
    print("RÉSOLUTION AVEC PANNE LGB (+2 jours S2)")
    print("-"*50)
    
    m_avec, marge_avec, cmd_avec, statut_avec, time_avec, data_panne = resoudre_avec_panne(
        data,
        jours_panne_lgb_s2=2,
        time_limit=3600
    )
    
    # ============================================================
    # ANALYSE DES COMMANDES BASCOLÉES
    # ============================================================
    print("\n" + "-"*50)
    print("ANALYSE DES COMMANDES BASCOLÉES")
    print("-"*50)
    
    commandes_bascules, refusees_en_plus, acceptees_en_plus = analyser_commandes_basculees(
        m_sans, m_avec, data
    )
    
    print(f"\n  Commandes basculées : {len(commandes_bascules)}")
    for cmd in commandes_bascules[:5]:
        print(f"    - {cmd['Commande']}: S{cmd['Semaine_sans_panne']} → S{cmd['Semaine_avec_panne']} "
              f"({cmd['Famille']} {cmd['Tonnage']:.0f}T)")
    if len(commandes_bascules) > 5:
        print(f"    ... et {len(commandes_bascules)-5} autres")
    
    # ============================================================
    # ANALYSE MAINTENANCE
    # ============================================================
    print("\n" + "-"*50)
    print("ANALYSE POUR LE SERVICE MAINTENANCE")
    print("-"*50)
    
    impact_maintenance = analyser_impact_maintenance(m_sans, m_avec, data)
    
    print(f"\n  Machine impactée : LGB")
    print(f"  Semaine : 2")
    print(f"  Jours de panne : {impact_maintenance['jours_panne']}")
    print(f"  Capacité LGB S2 utilisée (sans panne) : {impact_maintenance['capacite_lgb_s2_sans_panne']:.0f} T")
    print(f"  Capacité totale LGB S2 : {impact_maintenance['capacite_totale_lgb_s2']:.0f} T")
    print(f"  Taux d'occupation LGB S2 (sans panne) : {impact_maintenance['taux_occupation']:.1f} %")
    print(f"  Capacité perdue : {impact_maintenance['capacite_perdue']:.0f} T")
    print(f"  Commandes sur LGB S2 : {len(impact_maintenance['commandes_lgb_s2'])}")
    
    # ============================================================
    # EXPORT DES RÉSULTATS
    # ============================================================
    print("\n" + "-"*50)
    print("EXPORT DES RÉSULTATS")
    print("-"*50)
    
    filename = exporter_resultats_E21(
        m_sans, m_avec, data,
        marge_sans, marge_avec,
        commandes_bascules, refusees_en_plus, acceptees_en_plus,
        impact_maintenance,
        time_sans, time_avec
    )
    
    # ============================================================
    # CONCLUSION
    # ============================================================
    print("\n" + "="*70)
    print("CONCLUSION E21")
    print("="*70)
    
    perte_marge = marge_sans - marge_avec
    
    print(f"""
  📌 Une panne de 2 jours sur LGB en semaine 2 entraînerait :
     • Une perte de marge de {perte_marge:,.0f} MAD ({perte_marge/marge_sans*100:.2f}%)
     • {len(commandes_bascules)} commandes basculées vers d'autres semaines
     • {len(refusees_en_plus)} commandes supplémentaires refusées

  🔧 Recommandations pour la maintenance :
     • {impact_maintenance['commandes_lgb_s2']} commandes dépendent de LGB en semaine 2
     • Taux d'occupation LGB S2 : {impact_maintenance['taux_occupation']:.1f} %
     • Prioriser les interventions en dehors de cette semaine
     • Préparer un plan de bascule vers LGA pour les épaisseurs ≤ 0.6 mm
     • Anticiper les pénalités de retard (approx. 200 MAD/T/semaine)

  ✅ Informations exploitables par le service maintenance :
     • Identification des semaines critiques
     • Impact financier d'une panne (marge de manœuvre)
     • Planning de maintenance préventive optimisé
    """)
    
    print("="*70)
    print("FIN DE L'ANALYSE E21")
    print("="*70)


if __name__ == "__main__":
    main()