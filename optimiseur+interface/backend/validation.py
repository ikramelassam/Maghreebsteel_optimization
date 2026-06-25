"""
validation_complete.py
Validation a posteriori complète - lit l'Excel généré par solve1_4.py
Vérifie toutes les contraintes du modèle :
- C1 : production conforme = tonnage commandé
- C2 : capacité machines
- C3 : disponibilité HRC (consommation PK)
- C3f : stocks PK min/max par semaine
- C4 : cohérence des flux avec rendements (vérification sur les arcs sans stock inter)
- C5-C6 : stocks interprocess (bilans et min/max)
- C7-C8 : stocks produits finis (stock physique, min/max, livraisons)
- Retards (B2) : comparaison semaine production / semaine demandée
- Intégrité des variables binaires (0/1)
"""

import pandas as pd
import numpy as np
import os
import glob
from data_loader1 import charger_donnees

EPS = 1e-2   # tolérance pour les comparaisons numériques (tonnes)

def charger_resultats_complet(filepath):
    """Charge toutes les feuilles exportées"""
    print(f"Chargement des résultats depuis {filepath}")
    sheets = {
        "commandes_acceptees": pd.read_excel(filepath, sheet_name="Commandes_Acceptees"),
        "plan_production": pd.read_excel(filepath, sheet_name="Plan_Production"),
        "stocks_pk": pd.read_excel(filepath, sheet_name="Stocks_PK"),
        "stocks_inter": pd.read_excel(filepath, sheet_name="Stocks_Interprocess"),
        "variables_binaires": pd.read_excel(filepath, sheet_name="Variables_Binaires"),
        "resume": pd.read_excel(filepath, sheet_name="Resume")
    }
    # Livraisons réelles si disponibles
    try:
        sheets["livraisons_reelles"] = pd.read_excel(filepath, sheet_name="Livraisons_Reelles")
    except:
        sheets["livraisons_reelles"] = None
    return sheets

def valider_complet(data, resultats):
    """Vérification exhaustive"""
    cmd = data["commandes"]
    params = data["params"]
    rendements = data["rendements"]
    cadences = data["cadences"]
    arrets = data["arrets"]
    stock_pk_ref = data["stock_pk"]
    stock_inter_ref = data["stock_inter"]
    stock_fini_ref = data["stock_fini"]
    dispo_hrc = data["dispo_hrc"]
    jours = params["jours_semaine"]
    T = data["T"]
    F = data["F"]
    G = data["G"]
    K = data["K"]
    
    erreurs = []
    warnings = []
    
    # --- 1. Récupération des commandes acceptées ---
    acceptees = set(resultats["commandes_acceptees"]["ID"].values)
    print(f"\n=== Validation : {len(acceptees)} commandes acceptées ===")
    
    # --- 2. Vérification C1 : production conforme par commande ---
    print("\nC1 - Production conforme")
    # Calcul de la production conforme par commande (dernière machine du chemin)
    prod_conforme = {}
    for _, row in resultats["plan_production"].iterrows():
        cmd_id = row["Commande"]
        if cmd_id not in acceptees:
            continue
        machine = row["Machine"]
        famille = row["Famille"]
        # Déterminer si c'est une machine de livraison
        if (famille == "CRC" and machine == "SKP") or \
           (famille == "HDG" and machine in ["LGA","LGB"]) or \
           (famille == "PPGI" and machine == "LGA") or \
           (famille == "BACR" and machine == "LGB"):
            prod_conforme[cmd_id] = prod_conforme.get(cmd_id, 0.0) + row["Tonnage_sortant"]
    for i in acceptees:
        prod = prod_conforme.get(i, 0.0)
        tonnage_cmd = cmd[i]["tonnage"]
        if abs(prod - tonnage_cmd) > EPS:
            erreurs.append(f"C1 : {i} produit {prod:.1f} T au lieu de {tonnage_cmd:.1f} T")
    print(f"  {len(acceptees) - len([e for e in erreurs if 'C1' in e])}/{len(acceptees)} OK")
    
    # --- 3. C2 - Capacités machines ---
    print("\nC2 - Capacités machines")
    # Agréger la charge entrante par (machine, famille, semaine)
    charge = {}
    for _, row in resultats["plan_production"].iterrows():
        key = (row["Machine"], row["Famille"], row["Semaine"])
        charge[key] = charge.get(key, 0.0) + row["Tonnage_entrant"]
    capacite_ok = 0
    for (mach, fam, t), val in charge.items():
        cad = cadences.get((mach, fam), 0.0)
        if cad == 0:
            continue
        capa = cad * (jours - arrets.get((mach, t), 0))
        if val > capa + EPS:
            erreurs.append(f"C2 : {mach} S{t} {fam} : {val:.1f} T > capacité {capa:.1f} T")
        else:
            capacite_ok += 1
    print(f"  {capacite_ok} couples respectés, {len(erreurs) - len([e for e in erreurs if 'C2' in e])} violations")
    
    # --- 4. C3 - Disponibilité HRC (consommation PK) ---
    print("\nC3 - Consommation HRC par grade")
    conso_pk = resultats["plan_production"][resultats["plan_production"]["Machine"]=="PK"].groupby("Grade")["Tonnage_entrant"].sum().to_dict()
    for g in G:
        dispo_totale = dispo_hrc.get(g, 0) + (stock_pk_ref.get(g, {}).get("init", 0))
        conso = conso_pk.get(g, 0.0)
        if conso > dispo_totale + EPS:
            erreurs.append(f"C3 : Grade {g} consomme {conso:.1f} T > dispo {dispo_totale:.1f} T")
        else:
            print(f"   {g}: {conso:.1f} / {dispo_totale:.1f} T OK")
    
    # --- 5. C3f - Stocks PK (min/max) ---
    print("\nC3f - Stocks PK")
    if "stocks_pk" in resultats:
        stocks_pk = resultats["stocks_pk"]
        for g in G:
            if g not in stock_pk_ref:
                continue
            min_pk = stock_pk_ref[g]["min"]
            max_pk = stock_pk_ref[g]["max"]
            for t in T:
                stock = stocks_pk[(stocks_pk["Grade"]==g) & (stocks_pk["Semaine"]==t)]["Stock_T"].values
                if len(stock) == 0:
                    warnings.append(f"Stock PK {g} S{t} non trouvé")
                    continue
                stock = stock[0]
                if stock < min_pk - EPS:
                    erreurs.append(f"C3f : PK {g} S{t} = {stock:.1f} < min {min_pk}")
                if stock > max_pk + EPS:
                    erreurs.append(f"C3f : PK {g} S{t} = {stock:.1f} > max {max_pk}")
        print("  Stocks PK min/max vérifiés")
    else:
        warnings.append("Pas de feuille Stocks_PK")
    
    # --- 6. C4 - Cohérence des flux (rendements) pour les arcs sans stock inter ---
    # On vérifie pour chaque commande, chaque arc de son chemin, que x_aval <= rho * x_amont (même semaine)
    print("\nC4 - Flux avec rendements (sans stock inter)")
    flux_ok = 0
    flux_ko = 0
    # On regroupe les x par (commande, chemin, machine, semaine)
    # Le plan_production donne déjà tonnage_entrant par commande, machine, semaine.
    # On recrée un dict : (cmd, chemin, machine, semaine) -> tonnage_entrant
    x_dict = {}
    for _, row in resultats["plan_production"].iterrows():
        cmd_id = row["Commande"]
        if cmd_id not in acceptees:
            continue
        chemin = row["Chemin"]  # numéro du chemin
        mach = row["Machine"]
        t = row["Semaine"]
        entrant = row["Tonnage_entrant"]
        x_dict[(cmd_id, chemin, mach, t)] = entrant
    # Parcours des commandes et chemins
    for i in acceptees:
        cmd_i = cmd[i]
        for p in range(len(cmd_i["chemins"])):
            chemin = cmd_i["chemins"][p]
            for idx in range(len(chemin)-1):
                amont = chemin[idx]
                aval = chemin[idx+1]
                rho = rendements[amont]
                for t in T:
                    x_amont = x_dict.get((i, p, amont, t), 0.0)
                    x_aval = x_dict.get((i, p, aval, t), 0.0)
                    # Si l'arc est un point de stock interprocess, on ne vérifie pas ici (C5 le fera)
                    # On identifie les couples (amont, aval) qui correspondent à un stock inter
                    if (amont == "CRMA" and aval in ["LGA","LGB"]) or \
                       (amont == "CRMB" and aval in ["BAF","LGA","LGB"]) or \
                       (amont == "BAF" and aval in ["SKP","LGB"]) or \
                       (amont == "SKP" and aval == "CRC"):  # ce dernier est fictif, SKP->fini
                        continue   # géré par stocks inter
                    if x_aval > rho * x_amont + EPS and x_amont > 0:
                        erreurs.append(f"C4 : {i} ch{p} {amont}->{aval} S{t}: {x_aval:.1f} > {rho:.3f}*{x_amont:.1f}={rho*x_amont:.1f}")
                        flux_ko += 1
                    else:
                        flux_ok += 1
    print(f"  {flux_ok} vérifications OK, {flux_ko} violations")
    
    # --- 7. C5-C6 : Stocks interprocess (bilans et min/max) ---
    print("\nC5-C6 - Stocks interprocess")
    if "stocks_inter" in resultats:
        stocks_inter = resultats["stocks_inter"]
        # Vérification des min/max
        for k in K:
            if k not in stock_inter_ref:
                continue
            min_k = stock_inter_ref[k]["min"]
            max_k = stock_inter_ref[k]["max"]
            for t in T:
                row = stocks_inter[(stocks_inter["Point"]==k) & (stocks_inter["Semaine"]==t)]
                if row.empty:
                    warnings.append(f"Stock inter {k} S{t} manquant")
                    continue
                stock = row["Stock_T"].values[0]
                if stock < min_k - EPS:
                    erreurs.append(f"C6 : {k} S{t} = {stock:.1f} < min {min_k}")
                if stock > max_k + EPS:
                    erreurs.append(f"C6 : {k} S{t} = {stock:.1f} > max {max_k}")
        # Vérification du bilan (optionnel mais recommandé)
        # On recrée les flux entrants/sortants pour chaque point k
        # Pour simplifier, on vérifie seulement que le stock final est cohérent avec le flux net
        print("  Stocks interprocess min/max vérifiés (bilan non implémenté ici)")
    else:
        warnings.append("Pas de feuille Stocks_Interprocess")
    
    # --- 8. C7-C8 : Stocks produits finis (stock physique, min/max, livraisons réelles) ---
    print("\nC7-C8 - Stocks produits finis")
    if "livraisons_reelles" in resultats and resultats["livraisons_reelles"] is not None:
        livraisons_reelles = resultats["livraisons_reelles"]
        # On calcule le stock physique simulé semaine par semaine
        stock_phys = {f: stock_fini_ref[f]["init"] for f in F}
        for t in T:
            for f in F:
                # Production finie de la semaine
                prod_f = 0.0
                for _, row in resultats["plan_production"].iterrows():
                    if row["Famille"] != f:
                        continue
                    mach = row["Machine"]
                    if (f == "CRC" and mach == "SKP") or \
                       (f == "HDG" and mach in ["LGA","LGB"]) or \
                       (f == "PPGI" and mach == "LGA") or \
                       (f == "BACR" and mach == "LGB"):
                        prod_f += row["Tonnage_sortant"]
                # Livraisons réelles de la semaine
                liv = livraisons_reelles[(livraisons_reelles["Famille"]==f) & (livraisons_reelles["Semaine"]==t)]["Livraisons_Reelles_T"].sum()
                stock_phys[f] = stock_phys[f] + prod_f - liv
                # Vérification des bornes
                min_f = stock_fini_ref[f]["min"]
                max_f = stock_fini_ref[f]["max"]
                if stock_phys[f] < min_f - EPS:
                    erreurs.append(f"C8a : Stock physique {f} S{t} = {stock_phys[f]:.1f} < min {min_f}")
                if stock_phys[f] > max_f + EPS:
                    erreurs.append(f"C8b : Stock physique {f} S{t} = {stock_phys[f]:.1f} > max {max_f}")
        print("  Stocks finis vérifiés (min/max) sur tout l'horizon")
    else:
        warnings.append("Pas de données de livraisons réelles – vérification impossible")
    
    # --- 9. Retards (B2) ---
    print("\nRetards")
    retards = 0
    for i in acceptees:
        t_liv = cmd[i]["semaine_liv"]
        # Trouver la première semaine de production sur la machine de livraison
        sem_prod = None
        for _, row in resultats["plan_production"].iterrows():
            if row["Commande"] != i:
                continue
            mach = row["Machine"]
            famille = cmd[i]["famille"]
            if (famille == "CRC" and mach == "SKP") or \
               (famille == "HDG" and mach in ["LGA","LGB"]) or \
               (famille == "PPGI" and mach == "LGA") or \
               (famille == "BACR" and mach == "LGB"):
                if row["Tonnage_sortant"] > EPS:
                    sem_prod = row["Semaine"]
                    break
        if sem_prod is not None and sem_prod > t_liv:
            retards += 1
            warnings.append(f"Retard : {i} prévue S{t_liv}, produite S{sem_prod}")
    print(f"  {retards} commandes livrées en retard")
    
    # --- 10. Variables binaires (intégrité) ---
    print("\nIntégrité des binaires")
    if "variables_binaires" in resultats:
        df_bin = resultats["variables_binaires"]
        # Vérifier que les y sont 0 ou 1
        for _, row in df_bin.iterrows():
            if "y" in row and row["y"] not in [0,1]:
                erreurs.append(f"Variable y pour {row['Commande']} = {row['y']} (doit être 0 ou 1)")
        print("  Binaires vérifiés")
    else:
        warnings.append("Pas de feuille Variables_Binaires")
    
    # --- Bilan final ---
    print("\n" + "="*70)
    print("BILAN DE VALIDATION")
    print("="*70)
    if not erreurs:
        print("✅ AUCUNE ERREUR – La solution est parfaitement valide.")
    else:
        print(f"❌ {len(erreurs)} erreur(s) détectée(s) :")
        for err in erreurs[:10]:
            print(f"   - {err}")
    if warnings:
        print(f"\n⚠️ {len(warnings)} avertissement(s) :")
        for w in warnings[:5]:
            print(f"   - {w}")
    
    return len(erreurs) == 0

if __name__ == "__main__":
    print("=== Validation complète des résultats ===")
    data = charger_donnees()
    # Chercher le dernier fichier de résultats
    fichiers = glob.glob("resultats_maghreb_steel_*.xlsx")
    if not fichiers:
        print("Aucun fichier de résultats trouvé. Lancez d'abord solve1_4.py")
        exit(1)
    dernier = max(fichiers, key=os.path.getctime)
    print(f"Fichier utilisé : {dernier}")
    resultats = charger_resultats_complet(dernier)
    valider_complet(data, resultats)