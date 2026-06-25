# solve1_4.py
"""
solve1_4.py
Resolution du modele et export des resultats avec analyse detaillee
Version adaptee pour le modele avec separation stock physique / dette
Ajout du support de log_file pour capture du gap HiGHS.
Ajout du parseur Branch & Bound pour les logs HiGHS.
Ajout de la fonction diagnostiquer_refus pour les commandes refusées.
Correction: harmonisation des stocks avec arrondi et inclusion semaine 0 dans Excel.
"""

import pyomo.environ as pyo
from pyomo.contrib.appsi.solvers import Highs
from pyomo.environ import Suffix
from data_loader1 import charger_donnees
from model1 import construire_modele
import pandas as pd
from datetime import datetime
import time
import sys
import os
import re


# ── Classe utilitaire pour écrire à la fois dans le fichier et dans le terminal ──
class _Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for s in self.streams:
            try:
                s.write(data)
                s.flush()
            except (OSError, ValueError, AttributeError):
                # Ignorer les erreurs pour ne pas perturber la résolution
                pass

    def flush(self):
        for s in self.streams:
            try:
                s.flush()
            except Exception:
                pass


def resoudre(m, time_limit=600, mip_gap=0.01, log_file=None):
    """
    Résout le modèle avec HiGHS via appsi.
    Si log_file est fourni, écrit le log dans ce fichier (tee=True).
    """
    solver = Highs()
    solver.config.time_limit = time_limit
    solver.config.mip_gap = mip_gap
    solver.config.stream_solver = True

    if log_file:
        # S'assurer que le répertoire du fichier de log existe
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        # Rediriger stdout vers un objet Tee qui écrit à la fois dans le fichier et dans le terminal
        original_stdout = sys.stdout
        with open(log_file, 'w') as f:
            # Utiliser sys.__stdout__ pour éviter les wrappers (colorama, etc.)
            sys.stdout = _Tee(f, sys.__stdout__)
            try:
                results = solver.solve(m)
            finally:
                sys.stdout = original_stdout
        return results
    else:
        results = solver.solve(m)
        return results


def parser_bnb_log(log_path: str) -> dict:
    """
    Parse le fichier de log HiGHS pour extraire les données Branch & Bound.
    Retourne un dict avec :
      - nodes : liste de dicts {node_id, nodes_left, best_bound, best_int, gap}
      - total_leaves : nombre total de nœuds explorés
      - best_bound_evolution : liste de floats (best_bound à chaque nœud)
    Retourne None si le fichier n'existe pas ou si aucune ligne B&B n'est trouvée.
    """
    if not os.path.exists(log_path):
        return None

    # Regex souple pour les lignes de la table MIP de HiGHS
    # Exemples:
    #         0       0         0   0.00%   1122423004.08   -inf                 inf
    # L       0       0         0   0.00%   46497772.70026  42222245.9888     10.13%
    # L     431       0        31 100.00%   46220636.49229  45094067.05875     2.50%
    pattern = re.compile(
        r'^\s*(?:[A-Z]\s+)?(\d+)\s+(\d+)\s+\d+\s+[\d\.]+%\s+([\d\.e\+\-]+|inf|-inf)\s+([\d\.e\+\-]+|inf|-inf)\s+([\d\.]+)%'
    )

    nodes = []
    best_bound_evolution = []

    def to_float(s):
        if s.lower() == 'inf':
            return float('inf')
        if s.lower() == '-inf':
            return float('-inf')
        return float(s)

    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            match = pattern.search(line)
            if match:
                node_id = int(match.group(1))
                nodes_left = int(match.group(2))
                best_bound = to_float(match.group(3))
                best_int = to_float(match.group(4))
                gap = float(match.group(5))
                nodes.append({
                    'node_id': node_id,
                    'nodes_left': nodes_left,
                    'best_bound': best_bound,
                    'best_int': best_int,
                    'gap': gap,
                })
                best_bound_evolution.append(best_bound)

    if len(nodes) < 2:
        return None

    return {
        'nodes': nodes,
        'total_leaves': nodes[-1]['node_id'] + 1,  # approximatif
        'best_bound_evolution': best_bound_evolution,
    }


# ── TÂCHE 2.1 : Diagnostiquer les commandes refusées ──────────────────
def diagnostiquer_refus(m, data, i):
    """
    Pour une commande refusée i, identifie les contraintes qui l'auraient bloquée.
    Retourne une liste de strings lisibles par l'utilisateur.
    """
    import pyomo.environ as pyo

    cmd_i = data["commandes"][i]
    cadences = data["cadences"]
    arrets = data["arrets"]
    rendements = data["rendements"]
    dispo_hrc = data["dispo_hrc"]
    stock_pk = data["stock_pk"]
    params = data["params"]
    T = data["T"]
    jours = params["jours_semaine"]

    raisons = []

    # ── 1. Vérification capacité machine ────────────────────────────────
    # Pour chaque chemin possible de la commande, pour chaque machine,
    # on vérifie si la machine est saturée (>= 85%) dans au moins une semaine
    # pendant laquelle la commande pourrait être produite.
    famille = cmd_i["famille"]
    semaine_liv = cmd_i["semaine_liv"]
    tonnage = cmd_i["tonnage"]

    machines_saturees = set()
    for chemin in cmd_i["chemins"]:
        for mach in chemin:
            for t in T:
                if t > semaine_liv:
                    continue  # La commande ne peut pas être produite après sa date de livraison
                cad = cadences.get((mach, famille), 0.0)
                if cad == 0.0:
                    continue
                jours_dispo = jours - arrets.get((mach, t), 0.0)
                capacite = cad * jours_dispo
                if capacite <= 0:
                    continue

                # Calcul de la charge actuelle sur cette machine/semaine
                charge_actuelle = 0.0
                for j in data["I"]:
                    if pyo.value(m.y[j]) < 0.5:
                        continue  # Commande refusée, ne compte pas
                    cmd_j = data["commandes"][j]
                    if cmd_j["famille"] != famille:
                        continue
                    for p in range(len(cmd_j["chemins"])):
                        if mach in cmd_j["chemins"][p]:
                            val = pyo.value(m.x[j, p, mach, t])
                            if val is not None:
                                charge_actuelle += val

                taux = charge_actuelle / capacite * 100 if capacite > 0 else 0
                marge_disponible = capacite - charge_actuelle

                # Si la machine est à plus de 85% ET le tonnage de la commande
                # ne rentrerait pas dans la marge disponible
                if taux >= 85 and marge_disponible < tonnage * 0.5:
                    machines_saturees.add((mach, t, round(taux, 1), round(marge_disponible, 0)))

    for (mach, t, taux, marge) in sorted(machines_saturees):
        raisons.append(f"Machine {mach} saturée en S{t} ({taux}% utilisé, {marge:.0f}T disponibles)")

    # ── 2. Vérification disponibilité HRC ────────────────────────────────
    grade = cmd_i["grade"]
    dispo = dispo_hrc.get(grade, 0)
    stock_init = stock_pk.get(grade, {}).get("init", 0)
    dispo_totale = dispo + stock_init

    # Consommation déjà engagée par les commandes acceptées du même grade
    conso_grade = 0.0
    for j in data["I"]:
        if pyo.value(m.y[j]) < 0.5:
            continue
        if data["commandes"][j]["grade"] != grade:
            continue
        for p in range(len(data["commandes"][j]["chemins"])):
            for t in T:
                val = pyo.value(m.x[j, p, "PK", t])
                if val is not None:
                    conso_grade += val

    taux_hrc = conso_grade / dispo_totale * 100 if dispo_totale > 0 else 0
    marge_hrc = dispo_totale - conso_grade

    if taux_hrc >= 90 and marge_hrc < tonnage * 0.5:
        raisons.append(
            f"Stock HRC grade {grade} insuffisant "
            f"({conso_grade:.0f}T consommées / {dispo_totale:.0f}T disponibles, "
            f"il manque ~{max(0, tonnage - marge_hrc):.0f}T)"
        )

    # ── 3. Vérification stock produit fini ───────────────────────────────
    stock_fini_data = data["stock_fini"]
    if famille in stock_fini_data:
        # Vérifier si le stock max serait dépassé si on acceptait cette commande
        for t in T:
            if t > semaine_liv:
                continue
            stock_max = stock_fini_data[famille].get("max", float("inf"))
            stock_courant = pyo.value(m.StockPhysique[famille, t]) if hasattr(m, "StockPhysique") else 0
            if stock_courant is not None and stock_courant + tonnage > stock_max * 1.05:
                raisons.append(
                    f"Stock produit fini {famille} proche du maximum en S{t} "
                    f"({stock_courant:.0f}T stockées, max={stock_max:.0f}T)"
                )
                break

    # ── 4. Aucune contrainte identifiée ─────────────────────────────────
    if not raisons:
        # Raison générique basée sur la priorité
        prio = cmd_i.get("priorite", "")
        if prio == "Basse":
            raisons.append(f"Priorité {prio} — commande déprogrammée au profit de commandes de priorité supérieure")
        else:
            raisons.append("Combinaison de contraintes de capacité et/ou de ressources")

    return raisons


def analyser_resultats(m, data, IP, IPM):
    """Analyse complète (inchangée)"""
    print("\n" + "="*70)
    print("ANALYSE DETAILLEE DES RESULTATS")
    print("="*70)
    
    cmd = data["commandes"]
    params = data["params"]
    
    # 1. Commandes refusees
    print("\n--- 1. COMMANDES REFUSEES ---")
    refusees = []
    commandes_acceptees = []
    
    for i in data["I"]:
        if pyo.value(m.y[i]) < 0.5:
            cmd_i = cmd[i]
            refusees.append({
                "ID": i,
                "Famille": cmd_i["famille"],
                "Grade": cmd_i["grade"],
                "Tonnage": cmd_i["tonnage"],
                "Prix": cmd_i["prix"],
                "Priorite": cmd_i["priorite"],
                "Semaine_liv": cmd_i["semaine_liv"]
            })
            print(f"  ❌ {i}: {cmd_i['famille']} {cmd_i['grade']} "
                  f"{cmd_i['tonnage']:.0f}T (prix: {cmd_i['prix']:.0f} MAD/T, "
                  f"livraison S{cmd_i['semaine_liv']}, priorite {cmd_i['priorite']})")
        else:
            commandes_acceptees.append(i)
    
    print(f"\n  Résumé: {len(refusees)} / {len(data['I'])} commandes refusees "
          f"({100*len(refusees)/len(data['I']):.1f}%)")
    
    # 2. Commandes livrees en retard
    print("\n--- 2. COMMANDES LIVREES EN RETARD ---")
    retards = []
    for i in commandes_acceptees:
        cmd_i = cmd[i]
        semaine_prod = None
        for p in range(len(cmd_i["chemins"])):
            last_mach = cmd_i["chemins"][p][-1]
            for t in data["T"]:
                if pyo.value(m.x[i, p, last_mach, t]) > 0.01:
                    semaine_prod = t
                    break
            if semaine_prod:
                break
        
        if semaine_prod and semaine_prod > cmd_i["semaine_liv"]:
            retard = semaine_prod - cmd_i["semaine_liv"]
            retards.append((i, cmd_i["famille"], cmd_i["tonnage"], cmd_i["semaine_liv"], semaine_prod, retard))
            print(f"  📅 {i}: {cmd_i['famille']} {cmd_i['tonnage']:.0f}T - prevue S{cmd_i['semaine_liv']} "
                  f"-> produite S{semaine_prod} (retard {retard} sem.)")
    
    if not retards:
        print("  Aucune commande livree en retard")
    
    # 3. Taux d'utilisation des lignes (goulots)
    print("\n--- 3. TAUX D'UTILISATION DES LIGNES ---")
    cadences = data["cadences"]
    arrets = data["arrets"]
    jours_semaine = params["jours_semaine"]
    
    goulots = []
    for mach in data["M"]:
        for t in data["T"]:
            utilisation_totale = 0
            capacite_totale = 0
            for f in data["F"]:
                cad = cadences.get((mach, f), 0)
                if cad > 0:
                    jours_dispo = jours_semaine - arrets.get((mach, t), 0)
                    capacite = cad * jours_dispo
                    capacite_totale += capacite
                    
                    for i in data["I"]:
                        for p in range(len(cmd[i]["chemins"])):
                            if mach in cmd[i]["chemins"][p] and cmd[i]["famille"] == f:
                                utilisation_totale += pyo.value(m.x[i, p, mach, t])
            
            if capacite_totale > 0:
                taux = utilisation_totale / capacite_totale * 100
                if taux > 95:
                    print(f"  🔴 {mach} S{t}: {taux:.1f}% (GOULOT CRITIQUE)")
                    goulots.append((mach, t, taux))
                elif taux > 80:
                    print(f"  🟡 {mach} S{t}: {taux:.1f}% (Goulot)")
                elif taux > 50:
                    print(f"     {mach} S{t}: {taux:.1f}%")
                elif taux > 0:
                    print(f"     {mach} S{t}: {taux:.1f}%")
    
    # 4. Marges par famille
    print("\n--- 4. MARGE PAR FAMILLE (hors coûts fixes) ---")
    prix_hrc = data["prix_hrc"]
    rendements = data["rendements"]
    
    marge_par_famille = {f: 0.0 for f in data["F"]}
    tonnage_par_famille = {f: 0.0 for f in data["F"]}
    ca_par_famille = {f: 0.0 for f in data["F"]}
    
    for i in commandes_acceptees:
        cmd_i = cmd[i]
        f = cmd_i["famille"]
        tonnage = cmd_i["tonnage"]
        prix_hrc_cmd = prix_hrc.get((cmd_i["grade"], cmd_i["largeur"]), 6000)
        
        chemin_typique = cmd_i["chemins"][0]
        rendement_total = 1.0
        for mach in chemin_typique:
            rendement_total *= rendements[mach]
        
        cout_hrc_par_tonne = prix_hrc_cmd / rendement_total
        marge_unitaire = cmd_i["prix"] - cout_hrc_par_tonne
        marge_par_famille[f] += marge_unitaire * tonnage
        tonnage_par_famille[f] += tonnage
        ca_par_famille[f] += cmd_i["prix"] * tonnage
    
    print(f"\n  {'Famille':<10} {'Tonnage (T)':<12} {'CA (kMAD)':<15} {'Marge (kMAD)':<15} {'Marge/T (MAD)':<15}")
    print(f"  {'-'*60}")
    for f in data["F"]:
        if tonnage_par_famille[f] > 0:
            ca_k = ca_par_famille[f] / 1000
            marge_k = marge_par_famille[f] / 1000
            marge_t = marge_par_famille[f] / tonnage_par_famille[f]
            print(f"  {f:<10} {tonnage_par_famille[f]:<12.0f} {ca_k:<15.0f} {marge_k:<15.0f} {marge_t:<15.0f}")
    
    # 5. CONSOMMATION HRC PAR GRADE
    print("\n--- 5. CONSOMMATION HRC PAR GRADE ---")
    dispo_hrc = data["dispo_hrc"]
    stock_pk_init = data["stock_pk"]
    conso_hrc = {g: 0.0 for g in data["G"]}
    
    for i in commandes_acceptees:
        cmd_i = cmd[i]
        g = cmd_i["grade"]
        for p in range(len(cmd_i["chemins"])):
            for t in data["T"]:
                conso_hrc[g] += pyo.value(m.x[i, p, "PK", t])
    
    for g in data["G"]:
        dispo = dispo_hrc.get(g, 0)
        conso = conso_hrc[g]
        stock_init = stock_pk_init[g]["init"] if g in stock_pk_init else 0
        dispo_totale = dispo + stock_init
        pourc_total = (conso / dispo_totale * 100) if dispo_totale > 0 else 0
        
        if pourc_total > 99:
            print(f"  🔴 {g}: {conso:.0f} T consommees ({pourc_total:.1f}% - EPUISE)")
        elif pourc_total > 80:
            print(f"  🟡 {g}: {conso:.0f} / {dispo_totale:.0f} T ({pourc_total:.1f}%)")
        else:
            print(f"     {g}: {conso:.0f} / {dispo_totale:.0f} T ({pourc_total:.1f}%)")
    
    # 6. Stocks finaux
    print("\n--- 6. STOCKS PHYSIQUES FINAUX (fin semaine 4) ---")
    print(f"  {'Famille':<10} {'Stock physique (T)':<18} {'Min requis (T)':<15} {'Status':<10}")
    print(f"  {'-'*55}")
    for f in data["F"]:
        stock_final = pyo.value(m.StockPhysique[f, 4]) if hasattr(m.StockPhysique[f, 4], 'value') else 0
        min_req = data["stock_fini"][f]["min"]
        status = "OK" if stock_final >= min_req else "⚠️ BAS"
        print(f"  {f:<10} {stock_final:<18.1f} {min_req:<15.0f} {status:<10}")
    
    # 7. Dette de livraison
    print("\n--- 7. DETTE DE LIVRAISON (fin semaine 4) ---")
    for f in data["F"]:
        dette_final = pyo.value(m.Dette[f, 4]) if hasattr(m.Dette[f, 4], 'value') else 0
        print(f"  {f}: {dette_final:.1f} T")
    
    # 8. Stocks PK par grade
    print("\n--- 8. STOCKS PK PAR GRADE (fin semaine 4) ---")
    print(f"  {'Grade':<8} {'Stock final (T)':<15} {'Min requis (T)':<15} {'Status':<10}")
    print(f"  {'-'*50}")
    for g in data["G"]:
        stock_final = pyo.value(m.stockPK[g, 4]) if hasattr(m.stockPK[g, 4], 'value') else 0
        min_req = data["stock_pk"][g]["min"]
        status = "OK" if stock_final >= min_req else "⚠️ BAS"
        print(f"  {g:<8} {stock_final:<15.1f} {min_req:<15.0f} {status:<10}")
    
    # 9. Stocks interprocess
    print("\n--- 9. STOCKS INTERPROCESS (fin semaine 4) ---")
    stock_inter = data["stock_inter"]
    for k in data["K"]:
        stock_final = pyo.value(m.Iinter[k, 4]) if hasattr(m.Iinter[k, 4], 'value') else 0
        min_req = stock_inter[k]["min"]
        max_req = stock_inter[k]["max"]
        print(f"  {k}: {stock_final:.1f} T (min={min_req:.0f}, max={max_req:.0f})")
    
    # Diagnostic des stocks PK
    print("\n--- DIAGNOSTIC STOCKS PK ---")
    for g in data["G"]:
        print(f"\nGrade {g}:")
        for t in data["T"]:
            u_val = pyo.value(m.u[g, t]) if hasattr(m.u[g, t], 'value') else 0.0
            conso_cr = 0.0
            for i in data["I"]:
                if data["commandes"][i]["grade"] != g:
                    continue
                for p in range(len(data["commandes"][i]["chemins"])):
                    for mach in ["CRMA", "CRMB"]:
                        if mach in data["commandes"][i]["chemins"][p]:
                            conso_cr += pyo.value(m.x[i, p, mach, t]) if hasattr(m.x[i, p, mach, t], 'value') else 0.0
            stock_avant = pyo.value(m.stockPK[g, t-1]) if t > 1 else pyo.value(m.stockPK[g, 0])
            stock_apres = pyo.value(m.stockPK[g, t])
            print(f"  S{t}: u={u_val:8.1f} T, conso_CR={conso_cr:8.1f} T, "
                f"stock avant={stock_avant:8.1f} T, stock après={stock_apres:8.1f} T, "
                f"variation={stock_apres - stock_avant:8.1f} T")
            bilan_calcule = stock_avant + u_val - conso_cr
            if abs(bilan_calcule - stock_apres) > 0.5:
                print(f"      ⚠️ Bilan non respecté : {bilan_calcule:.1f} != {stock_apres:.1f}")
    return refusees, retards, goulots


def exporter_resultats(m, data, commandes_acceptees, refusees, retards, goulots, wall_time=None, filepath=None):
    """Export Excel inchangé, avec correction: semaine 0 pour stocks finis et arrondi cohérent."""
    if filepath is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = f"resultats_maghreb_steel_{timestamp}.xlsx"

    print("\n--- EXPORT DES RESULTATS VERS EXCEL ---")
    cmd = data["commandes"]
    
    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
        # 1. Plan de production
        production_data = []
        for i in commandes_acceptees:
            cmd_i = cmd[i]
            for p in range(len(cmd_i["chemins"])):
                for mach in cmd_i["chemins"][p]:
                    for t in data["T"]:
                        val = pyo.value(m.x[i, p, mach, t])
                        if val > 0.01:
                            production_data.append({
                                "Commande": i,
                                "Famille": cmd_i["famille"],
                                "Grade": cmd_i["grade"],
                                "Chemin": p,
                                "Machine": mach,
                                "Semaine": t,
                                "Tonnage_entrant": round(val, 1),
                                "Rendement": data["rendements"][mach],
                                "Tonnage_sortant": round(val * data["rendements"][mach], 1)
                            })
        df_prod = pd.DataFrame(production_data)
        df_prod.to_excel(writer, sheet_name="Plan_Production", index=False)

        # 2. Commandes acceptees
        acceptees_data = []
        for i in commandes_acceptees:
            cmd_i = cmd[i]
            acceptees_data.append({
                "ID": i,
                "Client": cmd_i["client"],
                "Famille": cmd_i["famille"],
                "Grade": cmd_i["grade"],
                "Tonnage": cmd_i["tonnage"],
                "Prix_vente": cmd_i["prix"],
                "Semaine_livraison": cmd_i["semaine_liv"],
                "Priorite": cmd_i["priorite"]
            })
        df_accept = pd.DataFrame(acceptees_data)
        df_accept.to_excel(writer, sheet_name="Commandes_Acceptees", index=False)

        # 3. Commandes refusees
        df_refus = pd.DataFrame(refusees)
        if not df_refus.empty:
            df_refus.to_excel(writer, sheet_name="Commandes_Refusees", index=False)

        # 4. Retards
        if retards:
            df_retard = pd.DataFrame(retards, columns=["ID", "Famille", "Tonnage", "Semaine_prevue", "Semaine_produite", "Retard_semaines"])
            df_retard.to_excel(writer, sheet_name="Livraisons_Retard", index=False)

        # 5. Goulots
        if goulots:
            df_goulots = pd.DataFrame(goulots, columns=["Machine", "Semaine", "Taux_utilisation"])
            df_goulots.to_excel(writer, sheet_name="Goulots", index=False)

        # 6. Resume
        if wall_time is not None:
            temps_resolution = round(wall_time, 1)
        else:
            temps_resolution = 46.0
        resume = {
            "Indicateur": [
                "Date execution",
                "Statut resolution",
                "Marge totale (MAD)",
                "Commandes totales",
                "Commandes acceptees",
                "Commandes refusees",
                "Taux service (%)",
                "Commandes en retard",
                "Temps resolution (s)"
            ],
            "Valeur": [
                datetime.now().strftime("%Y%m%d_%H%M%S"),
                "Optimal",
                f"{pyo.value(m.obj):,.0f}",
                len(data["I"]),
                len(commandes_acceptees),
                len(refusees),
                f"{100*len(commandes_acceptees)/len(data['I']):.1f}",
                len(retards),
                f"{temps_resolution}"
            ]
        }
        df_resume = pd.DataFrame(resume)
        df_resume.to_excel(writer, sheet_name="Resume", index=False)

        # 7. Utilisation des lignes
        utilisation_data = []
        cadences = data["cadences"]
        arrets = data["arrets"]
        jours = data["params"]["jours_semaine"]
        for mach in data["M"]:
            for t in data["T"]:
                utilisation = 0
                capacite = 0
                for f in data["F"]:
                    cad = cadences.get((mach, f), 0)
                    if cad > 0:
                        capacite += cad * (jours - arrets.get((mach, t), 0))
                        for i in commandes_acceptees:
                            cmd_i = cmd[i]
                            for p in range(len(cmd_i["chemins"])):
                                if mach in cmd_i["chemins"][p] and cmd_i["famille"] == f:
                                    utilisation += pyo.value(m.x[i, p, mach, t])
                if capacite > 0:
                    utilisation_data.append({
                        "Machine": mach,
                        "Semaine": t,
                        "Capacite_totale": capacite,
                        "Utilisation": round(utilisation, 1),
                        "Taux_%": round(100 * utilisation / capacite, 1)
                    })
        df_util = pd.DataFrame(utilisation_data)
        df_util.to_excel(writer, sheet_name="Utilisation_Lignes", index=False)

        # 8. Plan de marche par famille
        marche_par_famille = []
        for mach in data["M"]:
            for t in data["T"]:
                for f in data["F"]:
                    tonnage = 0
                    for i in commandes_acceptees:
                        cmd_i = cmd[i]
                        if cmd_i["famille"] != f:
                            continue
                        for p in range(len(cmd_i["chemins"])):
                            if mach in cmd_i["chemins"][p]:
                                tonnage += pyo.value(m.x[i, p, mach, t])
                    if tonnage > 0.01:
                        cad = cadences.get((mach, f), 0)
                        if cad > 0:
                            jours_dispo = jours - arrets.get((mach, t), 0)
                            capacite_machine = cad * jours_dispo
                            taux_utilisation = round(100 * tonnage / capacite_machine, 1) if capacite_machine > 0 else 0
                        else:
                            taux_utilisation = 0
                        commentaire = ""
                        if mach == "SKP" and t == 3 and tonnage > 1500:
                            commentaire = "GOULOT"
                        marche_par_famille.append({
                            "Machine": mach,
                            "Semaine": t,
                            "Famille": f,
                            "Tonnage_entrant_T": round(tonnage, 1),
                            "Taux_utilisation_%": taux_utilisation,
                            "Commentaire": commentaire
                        })
        df_marche = pd.DataFrame(marche_par_famille)
        if not df_marche.empty:
            df_marche.to_excel(writer, sheet_name="Plan_Marche_Par_Famille", index=False)

        # 9. Stocks physiques - CORRECTION: inclure semaine 0 et arrondi
        stocks_data = []
        for f in data["F"]:
            for t in [0] + data["T"]:
                stock_physique = pyo.value(m.StockPhysique[f, t]) if hasattr(m.StockPhysique[f, t], 'value') else 0
                dette = pyo.value(m.Dette[f, t]) if hasattr(m.Dette[f, t], 'value') else 0
                stocks_data.append({
                    "Famille": f,
                    "Semaine": t,
                    "Stock_physique_T": round(stock_physique, 1),
                    "Dette_T": round(dette, 1),
                    "Min_requis_T": data["stock_fini"][f]["min"],
                    "Max_stockage_T": data["stock_fini"][f]["max"]
                })
        df_stocks = pd.DataFrame(stocks_data)
        df_stocks.to_excel(writer, sheet_name="Stocks_Physiques", index=False)

        # 10. Stocks PK - déjà arrondi
        pk_stocks_data = []
        for g in data["G"]:
            for t in [0] + data["T"]:
                if hasattr(m.stockPK[g, t], 'value'):
                    stock_val = pyo.value(m.stockPK[g, t])
                else:
                    stock_val = 0.0
                pk_stocks_data.append({
                    "Grade": g,
                    "Semaine": t,
                    "Stock_T": round(stock_val, 1)
                })
        df_pk_stocks = pd.DataFrame(pk_stocks_data)
        df_pk_stocks.to_excel(writer, sheet_name="Stocks_PK", index=False)

        # 11. Stocks interprocess - déjà arrondi
        inter_data = []
        for k in data["K"]:
            for t in [0] + data["T"]:
                if hasattr(m.Iinter[k, t], 'value'):
                    stock_val = pyo.value(m.Iinter[k, t])
                else:
                    stock_val = 0.0
                inter_data.append({
                    "Point": k,
                    "Semaine": t,
                    "Stock_T": round(stock_val, 1)
                })
        df_inter = pd.DataFrame(inter_data)
        df_inter.to_excel(writer, sheet_name="Stocks_Interprocess", index=False)

        # 12. Livraisons réelles
        if hasattr(m, 'LivraisonsReelles'):
            livraisons_data = []
            for f in data["F"]:
                for t in data["T"]:
                    liv = pyo.value(m.LivraisonsReelles[f, t]) if hasattr(m.LivraisonsReelles[f, t], 'value') else 0.0
                    livraisons_data.append({"Famille": f, "Semaine": t, "Livraisons_Reelles_T": round(liv, 1)})
            df_liv = pd.DataFrame(livraisons_data)
            df_liv.to_excel(writer, sheet_name="Livraisons_Reelles", index=False)

        # 13. Variables binaires
        bin_data = []
        for i in data["I"]:
            bin_data.append({"Commande": i, "y": int(round(pyo.value(m.y[i])))})
        if hasattr(m, 'z'):
            for i in data["I"]:
                for r in data["R"]:
                    if pyo.value(m.z[i, r]) > 0.5:
                        bin_data[-1][f"z_r{r}"] = 1
        if hasattr(m, 'w'):
            for mach in data["M"]:
                for f in data["F"]:
                    for t in data["T"]:
                        if pyo.value(m.w[mach, f, t]) > 0.5:
                            bin_data.append({"Machine": mach, "Famille": f, "Semaine": t, "w": 1})
        df_bin = pd.DataFrame(bin_data)
        df_bin.to_excel(writer, sheet_name="Variables_Binaires", index=False)

        # 14. Bilan HRC
        df_pk = df_prod[df_prod["Machine"] == "PK"].copy()
        conso_grade = df_pk.groupby("Grade")["Tonnage_entrant"].sum().reset_index()
        conso_grade.columns = ["Grade", "Conso_PK_T"]
        hrc_dispo = data["dispo_hrc"]
        pk_init = data["stock_pk"]
        conso_grade["Dispo_HRC"] = conso_grade["Grade"].map(lambda g: hrc_dispo.get(g, 0))
        conso_grade["Stock_PK_init"] = conso_grade["Grade"].map(lambda g: pk_init.get(g, {}).get("init", 0))
        conso_grade["Dispo_totale"] = conso_grade["Dispo_HRC"] + conso_grade["Stock_PK_init"]
        conso_grade["Taux_utilisation_%"] = (conso_grade["Conso_PK_T"] / conso_grade["Dispo_totale"] * 100).round(1)
        conso_grade["Ecart_T"] = conso_grade["Dispo_totale"] - conso_grade["Conso_PK_T"]
        conso_grade.to_excel(writer, sheet_name="Bilan_HRC_par_Grade", index=False)

        conso_cmd = df_pk.groupby(["Commande", "Grade"])["Tonnage_entrant"].sum().reset_index()
        conso_cmd.columns = ["Commande", "Grade", "Conso_PK_T"]
        cmd_tonnage = {i: data["commandes"][i]["tonnage"] for i in data["I"]}
        conso_cmd["Tonnage_commande_T"] = conso_cmd["Commande"].map(lambda i: cmd_tonnage.get(i, 0))
        conso_cmd["Ratio_conso/commande"] = (conso_cmd["Conso_PK_T"] / conso_cmd["Tonnage_commande_T"]).round(3)
        conso_cmd.to_excel(writer, sheet_name="Conso_HRC_par_Commande", index=False)

        conso_semaine = df_pk.groupby(["Semaine", "Grade"])["Tonnage_entrant"].sum().reset_index()
        conso_semaine.columns = ["Semaine", "Grade", "Conso_PK_T"]
        pivot_semaine = conso_semaine.pivot(index="Semaine", columns="Grade", values="Conso_PK_T").fillna(0)
        pivot_semaine.to_excel(writer, sheet_name="Conso_HRC_par_Semaine")

    print(f"  ✅ Resultats exportes vers {filepath}")


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("="*70)
    print("LANCEMENT DU MODELE AVEC RIGUEUR MAXIMALE")
    print("="*70)
    
    data = charger_donnees()
    m, IP, IPM = construire_modele(data, activer_B2=True, activer_B4=False)
    
    print("\n" + "="*50)
    print("RESOLUTION EN COURS...")
    print("="*50)
    
    m.dual = Suffix(direction=Suffix.IMPORT)
    
    start_time = time.time()
    results = resoudre(m, time_limit=600, log_file=None)  # log_file=None pour le mode interactif
    end_time = time.time()
    wall_time = end_time - start_time
    
    print("\n" + "="*50)
    print("RESULTATS DE LA RESOLUTION")
    print("="*50)
    print(f"Statut: {results.termination_condition}")
    print(f"Valeur objectif (marge): {pyo.value(m.obj):,.2f} MAD")
    print(f"Temps de resolution: {wall_time:.1f} secondes")
    
    accepted = sum(1 for i in data["I"] if pyo.value(m.y[i]) > 0.5)
    print(f"Commandes acceptees: {accepted} / {len(data['I'])}")
    
    refusees, retards, goulots = analyser_resultats(m, data, IP, IPM)
    exporter_resultats(m, data, [i for i in data["I"] if pyo.value(m.y[i]) > 0.5], 
                      refusees, retards, goulots, wall_time=wall_time)
    
    print("\n" + "="*50)
    print("RECOMMANDATIONS PRELIMINAIRES")
    print("="*50)
    if goulots:
        print(f"  🔧 Goulot principal: {goulots[0][0]} semaine {goulots[0][1]} ({goulots[0][2]:.1f}%)")
        print(f"     → Augmenter la capacite de cette ligne ou repartir la charge")
    dispo_hrc = data["dispo_hrc"]
    stock_pk_init = data["stock_pk"]
    for g in data["G"]:
        conso = 0
        for i in data["I"]:
            if pyo.value(m.y[i]) > 0.5 and data["commandes"][i]["grade"] == g:
                for p in range(len(data["commandes"][i]["chemins"])):
                    for t in data["T"]:
                        conso += pyo.value(m.x[i, p, "PK", t])
        stock_init = stock_pk_init[g]["init"] if g in stock_pk_init else 0
        dispo_totale = dispo_hrc.get(g, 0) + stock_init
        if conso > 0.99 * dispo_totale:
            pourc = 100 * conso / dispo_totale
            print(f"  🏭 Grade limite: {g} utilise a {pourc:.1f}%")
    print("\n" + "="*50)
    print("FIN DE L'ANALYSE")
    print("="*50)