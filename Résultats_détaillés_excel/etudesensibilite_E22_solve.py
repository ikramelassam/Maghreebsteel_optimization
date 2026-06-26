"""
E22_commande_urgente.py
Scénario E22 : Commande urgente HDG DC01 300T S1
Impact sur la marge et coût d'opportunité
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


def ajouter_commande_urgente(data):
    """
    Ajoute la commande urgente dans les données
    """
    
    data_scenario = copy.deepcopy(data)
    
    nouvelle_commande = {
        "CMD-URG": {
            "client": "Client_Urgent",
            "famille": "HDG",
            "grade": "DC01",
            "epaisseur": 0.5,
            "largeur": 1140,
            "tonnage": 300,
            "prix": 11500,
            "semaine_liv": 1,
            "priorite": "Haute",
            "chemins": [("PK", "CRMA", "LGA"), ("PK", "CRMB", "LGA")]
        }
    }
    
    data_scenario["commandes"].update(nouvelle_commande)
    data_scenario["I"].append("CMD-URG")
    
    print(f"\n  🔔 Commande urgente ajoutée :")
    print(f"     ID : CMD-URG")
    print(f"     Famille : HDG")
    print(f"     Grade : DC01")
    print(f"     Tonnage : 300 T")
    print(f"     Prix : 11 500 MAD/T")
    print(f"     Livraison : Semaine 1")
    
    return data_scenario


def resoudre_modele_avec_commande(data, time_limit=3600):
    """Résout le modèle avec la commande urgente"""
    
    # Construction du modèle
    print("  Construction du modèle...")
    m, IP, IPM = construire_modele(data, activer_B2=True, activer_B4=True)
    
    # Résolution
    print("  Résolution en cours...")
    solver = Highs()
    solver.config.time_limit = time_limit
    solver.config.stream_solver = False
    
    start_time = time.time()
    results = solver.solve(m)
    wall_time = time.time() - start_time
    
    marge = pyo.value(m.obj)
    commandes_acceptees = [i for i in data["I"] if pyo.value(m.y[i]) > 0.5]
    
    termination_condition = str(results.termination_condition)
    
    print(f"    Marge : {marge:,.0f} MAD")
    print(f"    Commandes acceptées : {len(commandes_acceptees)} / {len(data['I'])}")
    print(f"    Statut : {termination_condition}")
    print(f"    Temps : {wall_time:.1f} s")
    
    return m, marge, commandes_acceptees, termination_condition, wall_time


def analyser_impact_commande_urgente(m_sans, m_avec, data_sans, data_avec):
    """
    Analyse l'impact de la commande urgente
    """
    
    # Commandes acceptées dans chaque scénario
    accept_sans = [i for i in data_sans["I"] if pyo.value(m_sans.y[i]) > 0.5]
    accept_avec = [i for i in data_avec["I"] if pyo.value(m_avec.y[i]) > 0.5]
    
    # Commandes refusées en plus
    refusees_en_plus = set(accept_sans) - set(accept_avec)
    
    # Nouvelles commandes acceptées
    nouvelles_acceptees = set(accept_avec) - set(accept_sans)
    
    # Vérifier si la commande urgente est acceptée
    commande_urgente_acceptee = "CMD-URG" in accept_avec
    
    # Calcul du CA brut sacrifié
    # = CA brut sacrifié sur les commandes refusées (prix × tonnage, pas une marge)
    ca_sacrifie = 0
    cmd = data_sans["commandes"]
    for i in refusees_en_plus:
        ca_sacrifie += cmd[i]["prix"] * cmd[i]["tonnage"]
    
    return {
        "commande_urgente_acceptee": commande_urgente_acceptee,
        "refusees_en_plus": refusees_en_plus,
        "nouvelles_acceptees": nouvelles_acceptees,
        "ca_sacrifie": ca_sacrifie,
        "gain_net_marge": 0,
        "cout_opportunite_strict": 0
    }


def exporter_resultats_E22(m_sans, m_avec, data_sans, data_avec, 
                          marge_sans, marge_avec,
                          impact, statut_sans, statut_avec,
                          wall_time_sans, wall_time_avec):
    """Exporte les résultats vers Excel"""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"E22_commande_urgente_{timestamp}.xlsx"
    
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        
        # Résumé
        gain_marge = marge_avec - marge_sans
        
        resume = {
            "Indicateur": [
                "Scénario",
                "Statut cas de base",
                "Statut cas avec commande",
                "Marge sans commande (MAD)",
                "Marge avec commande (MAD)",
                "Gain de marge (MAD)",
                "Gain de marge (%)",
                "Commandes acceptées (sans)",
                "Commandes acceptées (avec)",
                "Commande urgente acceptée ?",
                "Commandes refusées en plus",
                "CA sacrifié sur commandes refusées (MAD)",
                "Coût d'opportunité strict (MAD) = gain net si on avait refusé"
            ],
            "Valeur": [
                "Commande urgente HDG DC01 300T S1",
                statut_sans,
                statut_avec,
                f"{marge_sans:,.0f}",
                f"{marge_avec:,.0f}",
                f"{gain_marge:,.0f}",
                f"{gain_marge/marge_sans*100:.2f}%",
                len([i for i in data_sans["I"] if pyo.value(m_sans.y[i]) > 0.5]),
                len([i for i in data_avec["I"] if pyo.value(m_avec.y[i]) > 0.5]),
                "Oui" if impact["commande_urgente_acceptee"] else "Non",
                len(impact["refusees_en_plus"]),
                f"{impact['ca_sacrifie']:,.0f}",
                f"{impact['cout_opportunite_strict']:,.0f}"
            ]
        }
        df_resume = pd.DataFrame(resume)
        df_resume.to_excel(writer, sheet_name="Resume", index=False)
        
        # Commandes refusées en plus
        if impact["refusees_en_plus"]:
            cmd = data_sans["commandes"]
            refusees_data = []
            for i in impact["refusees_en_plus"]:
                refusees_data.append({
                    "Commande": i,
                    "Famille": cmd[i]["famille"],
                    "Grade": cmd[i]["grade"],
                    "Tonnage": cmd[i]["tonnage"],
                    "Prix_vente": cmd[i]["prix"],
                    "CA_perdu_MAD": cmd[i]["prix"] * cmd[i]["tonnage"]
                })
            df_refusees = pd.DataFrame(refusees_data)
            df_refusees.to_excel(writer, sheet_name="Commandes_Refusees", index=False)
    
    print(f"\n  ✅ Résultats exportés vers {filename}")
    return filename


def main():
    print("="*70)
    print("SCÉNARIO E22 - COMMANDE URGENTE ENTRANTE")
    print("HDG DC01 300T, livraison S1, prix 11 500 MAD/T")
    print("="*70)
    
    # Chargement des données
    print("\nChargement des données...")
    data = charger_donnees()
    data_original = copy.deepcopy(data)
    
    # ============================================================
    # RÉSOLUTION SANS COMMANDE URGENTE (référence)
    # ============================================================
    print("\n" + "-"*50)
    print("RÉSOLUTION DE RÉFÉRENCE (sans commande urgente)")
    print("-"*50)
    
    m_sans, marge_sans, cmd_sans, statut_sans, time_sans = resoudre_modele_avec_commande(
        data_original,
        time_limit=3600
    )
    
    # ============================================================
    # RÉSOLUTION AVEC COMMANDE URGENTE
    # ============================================================
    print("\n" + "-"*50)
    print("RÉSOLUTION AVEC COMMANDE URGENTE")
    print("-"*50)
    
    data_avec = ajouter_commande_urgente(data)
    m_avec, marge_avec, cmd_avec, statut_avec, time_avec = resoudre_modele_avec_commande(
        data_avec,
        time_limit=3600
    )
    
    # ============================================================
    # ANALYSE
    # ============================================================
    print("\n" + "-"*50)
    print("ANALYSE DE L'IMPACT")
    print("-"*50)
    
    impact = analyser_impact_commande_urgente(m_sans, m_avec, data_original, data_avec)
    
    # Remplir les champs laissés à 0
    impact['gain_net_marge'] = marge_avec - marge_sans
    impact['cout_opportunite_strict'] = marge_avec - marge_sans
    
    # Avertissement si le cas de base n'a pas convergé
    if statut_sans != "optimal":
        print("\n  ⚠️ ATTENTION : Le cas de base n'a pas convergé à l'optimal !")
        print(f"     Statut : {statut_sans}")
        print("     La comparaison économique peut être biaisée.")
        print("     Relancer avec time_limit plus élevé recommandé.")
    
    print(f"\n  Commande urgente acceptée : {'✅ OUI' if impact['commande_urgente_acceptee'] else '❌ NON'}")
    print(f"  Commandes refusées en plus : {len(impact['refusees_en_plus'])}")
    for i in impact["refusees_en_plus"]:
        print(f"    - {i}")
    print(f"\n  CA sacrifié : {impact['ca_sacrifie']:,.0f} MAD")
    print(f"  Gain net de marge : {impact['gain_net_marge']:,.0f} MAD")
    print(f"  Coût d'opportunité strict : {impact['cout_opportunite_strict']:,.0f} MAD")
    
    # ============================================================
    # EXPORT
    # ============================================================
    print("\n" + "-"*50)
    print("EXPORT DES RÉSULTATS")
    print("-"*50)
    
    filename = exporter_resultats_E22(
        m_sans, m_avec, data_original, data_avec,
        marge_sans, marge_avec,
        impact, statut_sans, statut_avec,
        time_sans, time_avec
    )
    
    # ============================================================
    # CONCLUSION
    # ============================================================
    print("\n" + "="*70)
    print("CONCLUSION E22")
    print("="*70)
    
    gain_marge = marge_avec - marge_sans
    ca_sacrifie = impact['ca_sacrifie']  # valeur positive
    ca_sacrifie_affichage = -ca_sacrifie  # affichage négatif
    ca_direct = 300 * 11500
    ca_nouvelles = ca_sacrifie - ca_direct + gain_marge
    commandes_refusees = ", ".join(sorted(impact['refusees_en_plus']))
    
    print(f"""
📌 Une commande urgente de 300T HDG DC01 (11 500 MAD/T) :

   • {'✅ Acceptée' if impact['commande_urgente_acceptee'] else '❌ Refusée'}
   • Gain net de marge : {gain_marge:+,.0f} MAD ({gain_marge/marge_sans*100:+.2f}%)
   • Coût d'opportunité strict : {impact['cout_opportunite_strict']:,.0f} MAD
     (= valeur perdue si on avait refusé la commande)

📊 Décomposition du gain net :
   • CA sacrifié sur commandes refusées : {ca_sacrifie_affichage:+,.0f} MAD
     ({commandes_refusees})
   • CA direct commande urgente : {ca_direct:+,.0f} MAD
     (300T × 11 500 MAD/T)
   • CA sur nouvelles commandes acceptées : {ca_nouvelles:+,.0f} MAD
   • Gain net de marge : {gain_marge:+,.0f} MAD

💡 Recommandation :
   • {'✅ Accepter la commande : elle est rentable' if gain_marge > 0 else '❌ Refuser la commande : pas assez rentable'}
   • Le coût d'opportunité du refus serait de {impact['cout_opportunite_strict']:,.0f} MAD
    """)
    
    print("="*70)
    print("FIN DE L'ANALYSE E22")
    print("="*70)


if __name__ == "__main__":
    main()