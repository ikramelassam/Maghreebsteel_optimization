# data_loader1.py
"""
data_loader.py
Lecture du fichier Excel Maghreb Steel et creation des structures de donnees.
Maintenant avec support d'un chemin de fichier personnalisé.
"""

import pandas as pd
import numpy as np

DEFAULT_EXCEL_PATH = r"C:\Users\benabdellouahad\Downloads\trycode2\Donnees_MaghrebSteel.xlsx"
FAMILLES_EXCLUES = {"Quarto", "HRC DEC"}

# ============================================================
# 1. CHEMINS VALIDES PAR FAMILLE ET EPAISSEUR
# ============================================================

def generer_chemins(famille, epaisseur):
    """Retourne la liste des chemins valides (tuples de machines)."""
    if famille == "CRC":
        return [("PK", "CRMB", "BAF", "SKP")]

    elif famille == "HDG":
        if epaisseur <= 0.6:
            return [("PK", "CRMA", "LGA"), ("PK", "CRMB", "LGA")]
        else:
            return [("PK", "CRMA", "LGB"), ("PK", "CRMB", "LGB")]

    elif famille == "PPGI":
        return [("PK", "CRMA", "LGA"), ("PK", "CRMB", "LGA")]

    elif famille == "BACR":
        if epaisseur <= 0.6:
            return [
                ("PK", "CRMB", "BAF", "LGB"),
                ("PK", "CRMA", "LGA"),
                ("PK", "CRMB", "LGA"),
            ]
        else:
            return [
                ("PK", "CRMB", "BAF", "LGB"),
                ("PK", "CRMA", "LGB"),
                ("PK", "CRMB", "LGB"),
            ]
    return []


# ============================================================
# 2. COMMANDES
# ============================================================

def lire_commandes(excel_path=DEFAULT_EXCEL_PATH):
    df = pd.read_excel(excel_path, sheet_name="Commandes", header=2)
    commandes = {}
    for _, row in df.iterrows():
        famille = row["Famille"]
        if famille in FAMILLES_EXCLUES:
            continue
        i = row["ID"]
        epaisseur = row["Épaisseur (mm)"]
        commandes[i] = {
            "client":      row["Client"],
            "famille":     famille,
            "grade":       row["Grade"],
            "epaisseur":   epaisseur,
            "largeur":     int(row["Largeur (mm)"]),
            "tonnage":     float(row["Tonnage (T)"]),
            "prix":        float(row["Prix vente (MAD/T)"]),
            "semaine_liv": int(row["Semaine livraison"]),
            "priorite":    row["Priorité"],
            "chemins":     generer_chemins(famille, epaisseur),
        }
    print(f"[OK] {len(commandes)} commandes chargees")
    return commandes


# ============================================================
# 3. CADENCES
# ============================================================

def lire_cadences(excel_path=DEFAULT_EXCEL_PATH):
    df = pd.read_excel(excel_path, sheet_name="Cadences", header=2)
    machines = ["PK", "CRMA", "CRMB", "BAF", "SKP", "LGA", "LGB"]
    familles = ["CRC", "HDG", "PPGI", "BACR"]
    cadences = {}
    for _, row in df.iterrows():
        ligne = str(row.iloc[0]).strip()
        if ligne not in machines:
            continue
        for f in familles:
            val = row.get(f, "—")
            cadences[(ligne, f)] = float(val) if (val != "—" and not pd.isna(val)) else 0.0
    print(f"[OK] Cadences chargees")
    return cadences


# ============================================================
# 4. RENDEMENTS
# ============================================================

def lire_rendements(excel_path=DEFAULT_EXCEL_PATH):
    df = pd.read_excel(excel_path, sheet_name="Rendements", header=2)
    machines = ["PK", "CRMA", "CRMB", "BAF", "SKP", "LGA", "LGB"]
    rendements = {}; alpha_chute = {}; alpha_decl = {}; alpha_nc = {}
    for _, row in df.iterrows():
        m = str(row["Process"]).strip()
        if m not in machines:
            continue
        rendements[m]  = float(row["Rendement (%)"])
        alpha_chute[m] = float(row["Chute (%)"])
        alpha_decl[m]  = float(row["Déclassé (%)"])
        alpha_nc[m]    = float(row["Non-conforme (%)"])
    print(f"[OK] Rendements charges pour {len(rendements)} machines")
    return rendements, alpha_chute, alpha_decl, alpha_nc


# ============================================================
# 5. COUTS VARIABLES
# ============================================================

def lire_couts(excel_path=DEFAULT_EXCEL_PATH):
    df = pd.read_excel(excel_path, sheet_name="Couts_Variables", header=2)
    intervals = [
        ("<0.3",    0.0,  0.3),
        ("0.3-0.4", 0.3,  0.4),
        ("0.4-0.5", 0.4,  0.5),
        ("0.5-0.7", 0.5,  0.7),
        ("0.7-1.0", 0.7,  1.0),
        ("1.0-1.5", 1.0,  1.5),
        (">1.5",    1.5,  999),
    ]

    def get_cout(machine, famille, epaisseur):
        """
        machine: PK, CRMA, CRMB, BAF, SKP, LGA, LGB
        famille: CRC, HDG, PPGI, BACR (utilise pour LGA/LGB qui ont des lignes separees)
        """
        if machine in ("LGA", "LGB"):
            process = f"{machine}-{famille}"
        else:
            process = machine

        row = df[df.iloc[:, 0].astype(str).str.strip() == process]
        if row.empty:
            return 0.0
        row = row.iloc[0]
        for col, lo, hi in intervals:
            if lo <= epaisseur < hi:
                return float(row[col])
        return float(row[">1.5"])

    print(f"[OK] Couts variables charges")
    return get_cout


# ============================================================
# 6. PRIX HRC ET DISPONIBILITE
# ============================================================

def lire_prix_hrc(excel_path=DEFAULT_EXCEL_PATH):
    df = pd.read_excel(excel_path, sheet_name="Prix_HRC", header=2)
    grades = ["DC01", "DD13", "DX51", "DX52", "S320"]

    # Prix par (grade, largeur) — colonnes sont des entiers
    prix_hrc = {}
    for _, row in df.iterrows():
        grade = str(row.iloc[0]).strip()
        if grade not in grades:
            continue
        for col in df.columns[1:]:
            val = row[col]
            if not pd.isna(val):
                prix_hrc[(grade, int(col))] = float(val)

    # Disponibilite HRC
    dispo_hrc = {}
    in_dispo = False
    for _, row in df.iterrows():
        label = str(row.iloc[0]).strip()
        if "Disponibilit" in label:
            in_dispo = True
            continue
        if in_dispo and label in grades:
            dispo_hrc[label] = float(row.iloc[1])

    print(f"[OK] Prix HRC: {len(prix_hrc)} entrees")
    print(f"[OK] Dispo HRC: {dispo_hrc}")
    return prix_hrc, dispo_hrc


# ============================================================
# 7. ARRETS PLANIFIES
# ============================================================

def lire_arrets(excel_path=DEFAULT_EXCEL_PATH):
    df = pd.read_excel(excel_path, sheet_name="Arrets_Planifies", header=2)
    machines = ["PK", "CRMA", "CRMB", "BAF", "SKP", "LGA", "LGB"]
    arrets = {}
    for _, row in df.iterrows():
        ligne = str(row.iloc[0]).strip()
        if ligne not in machines:
            continue
        for t in range(1, 5):
            col = f"Semaine {t}"
            val = row.get(col, 0)
            arrets[(ligne, t)] = float(val) if not pd.isna(val) else 0.0
    print(f"[OK] Arrets charges")
    return arrets


# ============================================================
# 8. STOCKS INITIAUX
# ============================================================

def lire_stocks(excel_path=DEFAULT_EXCEL_PATH):
    df = pd.read_excel(excel_path, sheet_name="Stocks_Initiaux", header=2)
    grades      = ["DC01", "DD13", "DX51", "DX52", "S320"]
    interprocess = ["FH-CRMA", "FH-CRMB", "BAF-out", "SKP-out"]
    familles    = ["CRC", "HDG", "PPGI", "BACR"]

    stock_pk    = {}
    stock_inter = {}
    stock_fini  = {}

    section = "pk"  # la feuille commence par les stocks PK
    for _, row in df.iterrows():
        c0 = str(row.iloc[0]).strip()
        c1 = row.iloc[1]
        c2 = row.iloc[2]
        c3 = row.iloc[3]

        # Detection section
        if "interprocess" in c0.lower() or "Full Hard" in c0:
            section = "inter"
            continue
        elif "produits finis" in c0.lower():
            section = "fini"
            continue
        elif c0 in ("Grade", "Point de stockage", "Famille", "nan"):
            continue  # ligne d'en-tete

        if section == "pk" and c0 in grades:
            stock_pk[c0] = {"init": float(c1), "min": float(c2), "max": float(c3)}

        elif section == "inter":
            for k in interprocess:
                if k in c0:
                    stock_inter[k] = {"init": float(c1), "min": float(c2), "max": float(c3)}

        elif section == "fini" and c0 in familles:
            stock_fini[c0] = {"init": float(c1), "min": float(c2), "max": float(c3)}

    print(f"[OK] Stocks PK: {list(stock_pk.keys())}")
    print(f"[OK] Stocks interprocess: {list(stock_inter.keys())}")
    print(f"[OK] Stocks produits finis: {list(stock_fini.keys())}")
    return stock_pk, stock_inter, stock_fini


# ============================================================
# 9. PARAMETRES
# ============================================================

def lire_parametres(excel_path=DEFAULT_EXCEL_PATH):
    df = pd.read_excel(excel_path, sheet_name="Parametres", header=2)
    raw = {}
    for _, row in df.iterrows():
        nom = str(row.iloc[0]).strip()
        val = row.iloc[1]
        if not pd.isna(val):
            raw[nom] = float(val)

    p = {
        "horizon":          int(raw.get("Horizon (semaines)", 4)),
        "jours_semaine":    int(raw.get("Jours ouvrés / semaine", 7)),
        "prix_chute":       raw.get("Prix de valorisation des chutes", 1800),
        "coef_decl":        raw.get("Coefficient déclassé/conforme", 0.5),
        "coef_nc":          raw.get("Coefficient non-conforme/conforme", 0.2),
        "prix_zinc":        raw.get("Prix zinc", 18000),
        "conso_zinc_hdg":   raw.get("Consommation zinc HDG", 0.025),
        "conso_zinc_ppgi":  raw.get("Consommation zinc PPGI", 0.025),
        "prix_peinture":    raw.get("Prix peinture (PPGI)", 12000),
        "conso_peinture":   raw.get("Consommation peinture PPGI", 0.01),
        "pen_haute":        raw.get("Pénalité retard commande Haute", 500),
        "pen_normale":      raw.get("Pénalité retard commande Normale", 200),
        "pen_basse":        raw.get("Pénalité retard commande Basse", 0),
        "cout_stock_inter": raw.get("Coût stockage interprocess", 25),
        "cout_stock_fini":  raw.get("Coût stockage produit fini", 40),
    }
    print(f"[OK] Parametres charges")
    return p


# ============================================================
# 10. FONCTION PRINCIPALE
# ============================================================

def charger_donnees_depuis(excel_path):
    print("=" * 50)
    print("CHARGEMENT DES DONNEES MAGHREB STEEL")
    print(f"Fichier: {excel_path}")
    print("=" * 50)

    data = {}
    data["commandes"]                                    = lire_commandes(excel_path)
    data["cadences"]                                     = lire_cadences(excel_path)
    data["rendements"], data["alpha_chute"], \
    data["alpha_decl"], data["alpha_nc"]                 = lire_rendements(excel_path)
    data["get_cout"]                                     = lire_couts(excel_path)
    data["prix_hrc"], data["dispo_hrc"]                  = lire_prix_hrc(excel_path)
    data["arrets"]                                       = lire_arrets(excel_path)
    data["stock_pk"], data["stock_inter"], \
    data["stock_fini"]                                   = lire_stocks(excel_path)
    data["params"]                                       = lire_parametres(excel_path)

    # Ensembles globaux
    data["I"] = list(data["commandes"].keys())
    data["T"] = list(range(1, data["params"]["horizon"] + 1))
    data["M"] = ["PK", "CRMA", "CRMB", "BAF", "SKP", "LGA", "LGB"]
    data["G"] = ["DC01", "DD13", "DX51", "DX52", "S320"]
    data["F"] = ["CRC", "HDG", "PPGI", "BACR"]
    data["K"] = ["FH-CRMA", "FH-CRMB", "BAF-out", "SKP-out"]
    data["R"] = [0, 1, 2, 3]

    print("=" * 50)
    print(f"RESUME: {len(data['I'])} commandes, {len(data['T'])} semaines")
    print("=" * 50)
    return data


def charger_donnees():
    """Charge les données depuis le chemin par défaut."""
    return charger_donnees_depuis(DEFAULT_EXCEL_PATH)


if __name__ == "__main__":
    data = charger_donnees()
    print("\nExemple CMD-001:", data["commandes"]["CMD-001"])
    print("Prix HRC (DX51, 1250):", data["prix_hrc"].get(("DX51", 1250)))
    print("Stock PK DC01:", data["stock_pk"].get("DC01"))
    print("Cout PK e=0.3:", data["get_cout"]("PK","HDG",0.3)); print("Cout LGA-PPGI e=0.3:", data["get_cout"]("LGA","PPGI",0.3))