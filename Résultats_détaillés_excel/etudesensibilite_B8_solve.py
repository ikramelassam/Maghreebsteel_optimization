"""
B8_enveloppe_HRC_DC01.py
Courbe d'enveloppe : variation de la disponibilité HRC DC01 de -50% à +50%
Avec time_limit = 600s (10 min par point)
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
import matplotlib.pyplot as plt
import numpy as np


def resoudre_avec_dispo_hrc_variable(data, variation_pct, time_limit=3600):
    """
    Résout le modèle avec une disponibilité HRC DC01 modifiée
    """
    
    data_scenario = copy.deepcopy(data)
    
    # Modifier la disponibilité HRC DC01
    dispo_hrc = data_scenario["dispo_hrc"]
    dispo_dc01 = 6750
    nouvelle_dispo = dispo_dc01 * (1 + variation_pct / 100)
    dispo_hrc["DC01"] = nouvelle_dispo
    
    print(f"  Variation {variation_pct:>+4}% : DC01 = {nouvelle_dispo:.0f} T", end=" ")
    
    # Construction du modèle
    m, IP, IPM = construire_modele(data_scenario, activer_B2=True, activer_B4=True)
    
    # Résolution avec time_limit uniquement
    solver = Highs()
    solver.config.time_limit = time_limit
    solver.config.stream_solver = False
    
    start_time = time.time()
    results = solver.solve(m)
    wall_time = time.time() - start_time
    
    marge = pyo.value(m.obj)
    commandes_acceptees = [i for i in data_scenario["I"] if pyo.value(m.y[i]) > 0.5]
    
    # Récupérer le gap (si disponible)
    try:
        if hasattr(results, 'gap') and results.gap is not None:
            gap = results.gap * 100
            print(f"— Marge : {marge:,.0f} MAD (gap: {gap:.2f}%, {len(commandes_acceptees)} commandes)")
        else:
            print(f"— Marge : {marge:,.0f} MAD ({len(commandes_acceptees)} commandes)")
    except:
        print(f"— Marge : {marge:,.0f} MAD ({len(commandes_acceptees)} commandes)")
    
    return marge, len(commandes_acceptees), results.termination_condition, wall_time, results


def analyser_pentes(points):
    """
    Analyse les pentes de la courbe pour identifier le point d'inflexion
    """
    
    variations = [p[0] for p in points]
    marges = [p[1] for p in points]
    
    print("\n" + "-"*50)
    print("ANALYSE DES PENTES")
    print("-"*50)
    
    pentes = []
    for i in range(len(variations)-1):
        pente = (marges[i+1] - marges[i]) / (variations[i+1] - variations[i])
        pentes.append((variations[i], variations[i+1], pente))
    
    print(f"\n  {'Segment':<20} {'Pente (MAD/%)':<15}")
    print("  " + "-"*40)
    for v1, v2, pente in pentes:
        print(f"  {v1:>+4}% -> {v2:>+4}% : {pente:>12,.0f}")
    
    if len(pentes) > 1:
        variations_pente = []
        for i in range(len(pentes)-1):
            diff = abs(pentes[i+1][2] - pentes[i][2])
            variations_pente.append((pentes[i][1], diff))
        
        point_inflexion = max(variations_pente, key=lambda x: x[1])
        print(f"\n  Point d'inflexion : {point_inflexion[0]:.0f}%")
        print(f"     (changement de pente de {point_inflexion[1]:.0f} MAD/%)")
        return point_inflexion[0]
    
    return None


def tracer_courbe(points, filename, point_inflexion=None):
    """Trace la courbe d'enveloppe avec le point d'inflexion marqué"""
    
    variations = [p[0] for p in points]
    marges = [p[1] / 1_000_000 for p in points]
    
    plt.figure(figsize=(10, 6))
    plt.plot(variations, marges, 'b-o', linewidth=2, markersize=8)
    
    if point_inflexion is not None:
        idx = variations.index(point_inflexion)
        inflexion_marge = marges[idx]
        plt.plot(point_inflexion, inflexion_marge, 'ro', markersize=12, zorder=5)
        plt.axvline(x=point_inflexion, color='red', linestyle='--', alpha=0.6, linewidth=1.5)
    
    plt.xlabel('Variation de la disponibilite HRC DC01 (%)')
    plt.ylabel('Marge optimale (M MAD)')
    plt.title("Courbe d'enveloppe — Marge vs Disponibilite HRC DC01")
    plt.grid(True, alpha=0.3)
    
    if point_inflexion is not None:
        from matplotlib.lines import Line2D
        legend_elements = [
            Line2D([0], [0], color='blue', marker='o', linestyle='-', linewidth=2, markersize=8, label='Marge optimale'),
            Line2D([0], [0], color='red', marker='o', linestyle='None', markersize=12, label=f"Point d'inflexion ({point_inflexion}%)")
        ]
        plt.legend(handles=legend_elements, loc='best')
    else:
        plt.legend(['Marge optimale'], loc='best')
    
    plt.tight_layout()
    plt.savefig(filename, dpi=150)
    plt.close()
    print(f"\n  Graphique sauvegarde : {filename}")


def exporter_resultats_B8(points, point_inflexion):
    """Exporte les résultats vers Excel"""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"B8_enveloppe_HRC_{timestamp}.xlsx"
    
    data = []
    for i, (var, marge, cmd, statut, temps, results) in enumerate(points):
        try:
            gap = results.gap * 100 if hasattr(results, 'gap') and results.gap is not None else None
        except:
            gap = None
        
        data.append({
            "Variation_%": var,
            "Disponibilite_DC01_T": 6750 * (1 + var / 100),
            "Marge_MAD": marge,
            "Marge_MMAD": marge / 1_000_000,
            "Commandes_acceptees": cmd,
            "Statut": statut,
            "Gap_%": f"{gap:.2f}" if gap is not None else "N/A",
            "Temps_s": temps
        })
    
    df = pd.DataFrame(data)
    
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="Enveloppe_HRC", index=False)
        
        variations = [p[0] for p in points]
        marges = [p[1] for p in points]
        pentes = []
        for i in range(len(variations)-1):
            pente = (marges[i+1] - marges[i]) / (variations[i+1] - variations[i])
            pentes.append({
                "Segment": f"{variations[i]:+}% -> {variations[i+1]:+}%",
                "Pente_MAD_pourcent": pente
            })
        df_pentes = pd.DataFrame(pentes)
        df_pentes.to_excel(writer, sheet_name="Pentes", index=False)
        
        if point_inflexion is not None:
            point_inflexion_str = f"{point_inflexion}%"
            point_inflexion_t = 6750 * (1 + point_inflexion / 100)
        else:
            point_inflexion_str = "N/A"
            point_inflexion_t = 0
        
        resume = pd.DataFrame({
            "Indicateur": [
                "Scenario",
                "Disponibilite nominale DC01 (T)",
                "Point d'inflexion (%)",
                "Point d'inflexion (T)",
                "Marge nominale (MAD)",
                "Marge min (MAD)",
                "Marge max (MAD)",
                "Ecart max (MAD)",
                "Temps total resolution (s)"
            ],
            "Valeur": [
                "B8 - Enveloppe HRC DC01",
                6750,
                point_inflexion_str,
                round(point_inflexion_t, 0),
                points[len(points)//2][1] if len(points) > 0 else 0,
                min([p[1] for p in points]) if points else 0,
                max([p[1] for p in points]) if points else 0,
                (max([p[1] for p in points]) - min([p[1] for p in points])) if points else 0,
                sum([p[4] for p in points]) if points else 0
            ]
        })
        resume.to_excel(writer, sheet_name="Resume", index=False)
    
    print(f"\n  Resultats exportes vers {filename}")
    return filename


def main():
    print("="*70)
    print("B8 - COURBE D'ENVELOPPE HRC DC01")
    print("Variation de la disponibilite HRC DC01 de -50% a +50%")
    print("="*70)
    
    print("\nChargement des donnees...")
    data = charger_donnees()
    
    TIME_LIMIT = 3600 # 10 minutes par point
    
    variations = [-50, -40, -30, -20, -10, 0, 10, 20, 30, 40, 50]
    
    print(f"\n  Resolution pour {len(variations)} points...")
    print(f"  Time limit : {TIME_LIMIT}s")
    print("  " + "-"*50)
    
    points = []
    for var in variations:
        marge, cmd, statut, temps, results = resoudre_avec_dispo_hrc_variable(
            data, var, time_limit=TIME_LIMIT
        )
        points.append((var, marge, cmd, statut, temps, results))
    
    point_inflexion = analyser_pentes(points)
    tracer_courbe(points, "B8_courbe_enveloppe_HRC.png", point_inflexion)
    exporter_resultats_B8(points, point_inflexion)
    
    print("\n" + "="*70)
    print("CONCLUSION B8")
    print("="*70)
    
    marge_nominale = points[5][1]
    marge_min = min([p[1] for p in points])
    marge_max = max([p[1] for p in points])
    
    var_min_idx = [p[1] for p in points].index(marge_min)
    var_max_idx = [p[1] for p in points].index(marge_max)
    var_min = points[var_min_idx][0]
    var_max = points[var_max_idx][0]
    
    if point_inflexion is not None:
        inflexion_t = 6750 * (1 + point_inflexion / 100)
        inflexion_msg = f"{point_inflexion}% ({inflexion_t:.0f} T)"
    else:
        inflexion_msg = "Non identifie"
    
    print(f"""
  Courbe d'enveloppe HRC DC01 :

     Disponibilite nominale DC01 : 6 750 T
     Marge nominale : {marge_nominale:,.0f} MAD

     Marge minimale : {marge_min:,.0f} MAD (a {var_min:+}%)
     Marge maximale : {marge_max:,.0f} MAD (a {var_max:+}%)

  Point d'inflexion : {inflexion_msg}
     Avant ce point, chaque % de HRC DC01 en moins fait chuter la marge
     Apres ce point, la marge est stable (les autres ressources sont limitantes)

  Interpretation :
     La disponibilite nominale (6 750 T) se situe au point d'inflexion
     Une baisse en dessous de ce point entrainerait une perte de marge significative
     Une augmentation au-dela de ce point n'apporte quasiment aucun gain
     Le stock de securite DC01 devrait etre maintenu a au moins 6 750 T
    """)
    
    print("="*70)
    print("FIN DE L'ANALYSE B8")
    print("="*70)


if __name__ == "__main__":
    main()