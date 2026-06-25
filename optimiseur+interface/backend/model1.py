"""
model1.py
Construction du modele Pyomo Maghreb Steel - RIGUEUR MAXIMALE
Avec separation explicite entre stock physique et dette de livraison

FLUX MATIERE RIGOUREUX :
    achatHRC[g,t] --> hrcStock[g,t] --> v[g,t] --> [PK, rdt=0.985] --> u[g,t] --> stockPK[g,t] --> CRMA/CRMB

STOCKS PRODUITS FINIS (RIGUEUR MAXIMALE) :
    - StockPhysique[f,t] : tonnes réelles dans l'entrepôt (ne peut jamais être négatif)
    - Dette[f,t] : tonnes promises mais non encore livrées
    - LivraisonsReelles[f,t] : tonnes réellement expédiées (décision du modèle)
    
    Le stock physique respecte les min/max de sécurité à CHAQUE semaine.
    Les retards sont possibles via la dette.
"""

import pyomo.environ as pyo
from data_loader1 import charger_donnees


# ============================================================
# DEFINITION DES POINTS INTERPROCESS
# ============================================================
INTERPROCESS = {
    "FH-CRMA": {"amont": "CRMA", "aval": ["LGA", "LGB"]},
    "FH-CRMB": {"amont": "CRMB", "aval": ["BAF", "LGA", "LGB"]},
    "BAF-out": {"amont": "BAF",  "aval": ["SKP", "LGB"]},
    "SKP-out": {"amont": "SKP",  "aval": []},
}


def construire_modele(data, activer_B2=True, activer_B4=True):
    """
    Construit le modele Pyomo complet avec rigueur maximale.
    """

    m = pyo.ConcreteModel()

    I = data["I"]
    T = data["T"]
    M = data["M"]
    G = data["G"]
    F = data["F"]
    K = data["K"]
    R = data["R"]
    cmd = data["commandes"]
    params = data["params"]
    
    rendements = data["rendements"]
    alpha_chute = data["alpha_chute"]
    alpha_decl = data["alpha_decl"]
    alpha_nc = data["alpha_nc"]
    get_cout = data["get_cout"]
    prix_hrc = data["prix_hrc"]
    
    dispo_hrc = data["dispo_hrc"]
    stock_pk_init = data["stock_pk"]
    stock_fini = data["stock_fini"]
    
    # Stock HRC BRUT initial par grade (0 car tout est déjà décapé dans stockPK)
    stock_hrc_brut_init = {g: 0 for g in G}
    
    # Rendement du décapage (PK)
    rendement_PK = rendements.get("PK", 0.985)
    
    BIG_M = 10000.0
    EPS = 0.001

    # ------------------------------------------------------
    # ENSEMBLES DERIVES
    # ------------------------------------------------------
    IP = [(i, p) for i in I for p in range(len(cmd[i]["chemins"]))]
    IPM = [(i, p, mach) for (i, p) in IP for mach in cmd[i]["chemins"][p]]

    m.I = pyo.Set(initialize=I)
    m.T = pyo.Set(initialize=T)
    m.M = pyo.Set(initialize=M)
    m.G = pyo.Set(initialize=G)
    m.F = pyo.Set(initialize=F)
    m.K = pyo.Set(initialize=K)
    m.R = pyo.Set(initialize=R)
    m.IP = pyo.Set(initialize=IP, dimen=2)
    m.IPM = pyo.Set(initialize=IPM, dimen=3)

    def last_machine(i, p):
        return cmd[i]["chemins"][p][-1]

    # ------------------------------------------------------
    # VARIABLES DE DECISION
    # ------------------------------------------------------
    def x_index():
        return [(i, p, mach, t) for (i, p, mach) in IPM for t in T]
    m.x = pyo.Var(x_index(), domain=pyo.NonNegativeReals)

    m.y = pyo.Var(m.I, domain=pyo.Binary)

    m.Iinter = pyo.Var(K, [0] + T, domain=pyo.NonNegativeReals)

    # Stock HRC DÉCAPÉ (tampon entre PK et CRMA/CRMB)
    m.stockPK = pyo.Var(G, [0] + T, domain=pyo.NonNegativeReals)
    
    # Stock HRC BRUT (tampon avant décapage)
    m.hrcStock = pyo.Var(G, [0] + T, domain=pyo.NonNegativeReals)

    # ============================================================
    # STOCKS PRODUITS FINIS - RIGUEUR MAXIMALE
    # ============================================================
    # Stock physique réel (tonnes dans l'entrepôt)
    m.StockPhysique = pyo.Var(F, [0] + T, domain=pyo.NonNegativeReals)
    
    # Dette de livraison (tonnes promises mais non encore livrées)
    m.Dette = pyo.Var(F, [0] + T, domain=pyo.NonNegativeReals)
    
    # Livraisons réellement effectuées chaque semaine
    m.LivraisonsReelles = pyo.Var(F, T, domain=pyo.NonNegativeReals)

    # Achat HRC brut
    m.achatHRC = pyo.Var(G, T, domain=pyo.NonNegativeReals)

    # HRC brut envoyé au décapage (PK)
    m.v = pyo.Var(G, T, domain=pyo.NonNegativeReals)

    # HRC décapé sortant de PK
    m.u = pyo.Var(G, T, domain=pyo.NonNegativeReals)

    if activer_B2:
        m.z = pyo.Var(m.I, m.R, domain=pyo.Binary)

    if activer_B4:
        m.w = pyo.Var(m.M, m.F, m.T, domain=pyo.Binary)

    print(f"[OK] Modele cree : {len(m.x)} x, {len(m.y)} y, "
          f"{len(m.achatHRC)} achat, {len(m.v)} v, {len(m.u)} u, "
          f"{len(m.StockPhysique)} StockPhysique, {len(m.Dette)} Dette, "
          f"{len(m.LivraisonsReelles)} LivraisonsReelles"
          + (f", {len(m.z)} z" if activer_B2 else "")
          + (f", {len(m.w)} w" if activer_B4 else ""))

    # ------------------------------------------------------
    # FONCTION OBJECTIF (CORRIGEE - plus de pyo.value())
    # ------------------------------------------------------
    def obj_rule(m):
        R_vente = 0.0
        R_pertes = 0.0
        C_HRC = 0.0
        C_transfo = 0.0
        C_zinc = 0.0
        C_peinture = 0.0
        C_stock_fini = 0.0
        C_penalites_retard = 0.0
        
        for (i, p) in IP:
            last_mach = last_machine(i, p)
            rho_last = rendements[last_mach]
            
            for t in T:
                x_entrant_last = m.x[i, p, last_mach, t]
                x_sortant_last = rho_last * x_entrant_last
                
                R_vente += cmd[i]["prix"] * x_sortant_last
                
                if cmd[i]["famille"] in ("HDG", "PPGI"):
                    C_zinc += params["prix_zinc"] * params["conso_zinc_hdg"] * x_sortant_last
                
                if cmd[i]["famille"] == "PPGI":
                    C_peinture += params["prix_peinture"] * params["conso_peinture"] * x_sortant_last
            
            for mach in cmd[i]["chemins"][p]:
                for t in T:
                    x_entrant = m.x[i, p, mach, t]
                    
                    R_pertes += (
                        params["prix_chute"] * alpha_chute[mach]
                        + params["coef_decl"] * cmd[i]["prix"] * alpha_decl[mach]
                        + params["coef_nc"] * cmd[i]["prix"] * alpha_nc[mach]
                    ) * x_entrant
                    
                    C_transfo += get_cout(mach, cmd[i]["famille"], cmd[i]["epaisseur"]) * x_entrant
        
        # Coût d'achat HRC
        C_achat_HRC = sum(prix_hrc.get((g, 1100), 6000) * m.achatHRC[g, t] for g in G for t in T)
        
        # Coût de stockage (sur stock physique)
        C_stock_fini = sum(params["cout_stock_fini"] * m.StockPhysique[f, t] for f in F for t in T)
        
        # Coût de stockage interprocess
        C_stock_inter = sum(params["cout_stock_inter"] * m.Iinter[k, t] for k in K for t in T)
        
        # Pénalités de retard (B2) - calcul directement sur m.z
        if activer_B2:
            for i in I:
                if cmd[i]["priorite"] == "Haute":
                    pen = params["pen_haute"]
                elif cmd[i]["priorite"] == "Normale":
                    pen = params["pen_normale"]
                else:
                    pen = params["pen_basse"]
                for r in R:
                    C_penalites_retard += pen * r * m.z[i, r] * cmd[i]["tonnage"]
        
        return (R_vente + R_pertes - C_HRC - C_transfo - C_zinc 
                - C_achat_HRC - C_stock_fini - C_stock_inter - C_penalites_retard)

    m.obj = pyo.Objective(rule=obj_rule, sense=pyo.maximize)
    print("[OK] Fonction objectif construite")

    # ------------------------------------------------------
    # C1 -- DEMANDE
    # ------------------------------------------------------
    def c1_demande_rule(m, i):
        total_production_conforme = 0.0
        for p in range(len(cmd[i]["chemins"])):
            last_mach = cmd[i]["chemins"][p][-1]
            rho_last = rendements[last_mach]
            for t in T:
                total_production_conforme += rho_last * m.x[i, p, last_mach, t]
        return total_production_conforme == m.y[i] * cmd[i]["tonnage"]
    m.c1_demande = pyo.Constraint(m.I, rule=c1_demande_rule)

    # ------------------------------------------------------
    # C2 -- CAPACITE MACHINE
    # ------------------------------------------------------
    cadences = data["cadences"]
    arrets = data["arrets"]

    def c2_capacite_famille_rule(m, mach, fam, t):
        expr = sum(m.x[i, p, mach, t] for (i, p, mm) in IPM if mm == mach and cmd[i]["famille"] == fam)
        cad = cadences.get((mach, fam), 0.0)
        if cad == 0.0:
            if isinstance(expr, (int, float)) and expr == 0:
                return pyo.Constraint.Feasible
            return expr == 0
        jours = data["params"]["jours_semaine"] - arrets.get((mach, t), 0.0)
        return expr <= cad * jours

    m.c2_capacite = pyo.Constraint(m.M, m.F, m.T, rule=c2_capacite_famille_rule)

    # ------------------------------------------------------
    # C3 -- GESTION HRC RIGOUREUSE
    # ------------------------------------------------------
    
    def c3a_limite_achat_rule(m, g):
        return sum(m.achatHRC[g, t] for t in T) <= dispo_hrc.get(g, 0)
    m.c3a_limite_achat = pyo.Constraint(m.G, rule=c3a_limite_achat_rule)

    for g in G:
        m.hrcStock[g, 0].fix(stock_hrc_brut_init.get(g, 0))
    
    def c3b_bilan_hrc_brut(m, g, t):
        if t == min(T):
            stock_brut_prec = stock_hrc_brut_init.get(g, 0)
        else:
            stock_brut_prec = m.hrcStock[g, t - 1]
        return m.hrcStock[g, t] == stock_brut_prec + m.achatHRC[g, t] - m.v[g, t]
    m.c3b_bilan_hrc_brut = pyo.Constraint(m.G, m.T, rule=c3b_bilan_hrc_brut)
    
# Correction : ce qui entre dans PK (v) est égal à la somme des x sur PK
    def c3d_lien_v_x(m, g, t):
        somme_x_pk = sum(m.x[i, p, "PK", t] for (i, p) in IP if cmd[i]["grade"] == g)
        return m.v[g, t] == somme_x_pk
    m.c3d_lien_v_x = pyo.Constraint(m.G, m.T, rule=c3d_lien_v_x)

    # Le lien entre v et u reste correct : u = rendement * v
    def c3c_lien_v_u(m, g, t):
        return m.u[g, t] == rendement_PK * m.v[g, t]
    m.c3c_lien_v_u = pyo.Constraint(m.G, m.T, rule=c3c_lien_v_u)
    
    def c3e_bilan_pk(m, g, t):
        if t == min(T):
            stock_decape_prec = stock_pk_init[g]["init"] if g in stock_pk_init else 0
        else:
            stock_decape_prec = m.stockPK[g, t - 1]
        
        conso_par_cr = sum(
            m.x[i, p, mach, t]
            for (i, p) in IP 
            for mach in ["CRMA", "CRMB"]
            if cmd[i]["grade"] == g and mach in cmd[i]["chemins"][p]
        )
        
        return m.stockPK[g, t] == stock_decape_prec + m.u[g, t] - conso_par_cr
    m.c3e_bilan_pk = pyo.Constraint(m.G, m.T, rule=c3e_bilan_pk)
    
    def c3f_min_pk(m, g, t):
        if g in stock_pk_init:
            return m.stockPK[g, t] >= stock_pk_init[g]["min"]
        return pyo.Constraint.Feasible
    
    def c3f_max_pk(m, g, t):
        if g in stock_pk_init:
            return m.stockPK[g, t] <= stock_pk_init[g]["max"]
        return pyo.Constraint.Feasible
    
    m.c3f_min_pk = pyo.Constraint(m.G, m.T, rule=c3f_min_pk)
    m.c3f_max_pk = pyo.Constraint(m.G, m.T, rule=c3f_max_pk)
    
    def c3g_limite_consommation_totale(m, g):
        conso_totale = sum(m.u[g, t] for t in T)
        cap_decapage = rendement_PK * dispo_hrc.get(g, 0)
        stock_decape_init = stock_pk_init[g]["init"] if g in stock_pk_init else 0
        return conso_totale <= cap_decapage + stock_decape_init
    m.c3g_limite_consommation_totale = pyo.Constraint(m.G, rule=c3g_limite_consommation_totale)
    
    def c3h_limite_v_par_stock(m, g, t):
        if t == min(T):
            stock_brut_prec = stock_hrc_brut_init.get(g, 0)
        else:
            stock_brut_prec = m.hrcStock[g, t - 1]
        return m.v[g, t] <= stock_brut_prec + m.achatHRC[g, t]
    m.c3h_limite_v_par_stock = pyo.Constraint(m.G, m.T, rule=c3h_limite_v_par_stock)
    
    for g in G:
        if g in stock_pk_init:
            m.stockPK[g, 0].fix(stock_pk_init[g]["init"])
        else:
            m.stockPK[g, 0].fix(0)

    print("[OK] Contraintes C1, C2, C3 (HRC rigoureux) construites")
    print(f"     rendement_PK = {rendement_PK}")

    # ------------------------------------------------------
    # C4 -- COHERENCE ENTRE MACHINES
    # ------------------------------------------------------
    PAIR_TO_K = {}
    for k, info in INTERPROCESS.items():
        amont = info["amont"]
        for aval in info["aval"]:
            PAIR_TO_K[(amont, aval)] = k

    PAIRS = []
    PAIRS_PK_CR = []
    for (i, p) in IP:
        chemin = cmd[i]["chemins"][p]
        for idx in range(len(chemin) - 1):
            m_amont = chemin[idx]
            m_aval = chemin[idx + 1]
            if m_amont == "PK" and m_aval in ["CRMA", "CRMB"]:
                PAIRS_PK_CR.append((i, p, m_aval))
                continue
            k = PAIR_TO_K.get((m_amont, m_aval))
            PAIRS.append((i, p, m_amont, m_aval, k))

    def c4_coherence_rule(m, i, p, m_amont, m_aval, k, t):
        rho = rendements[m_amont]

        if k is not None:
            return m.x[i, p, m_aval, t] <= rho * m.x[i, p, m_amont, t] + m.Iinter[k, t - 1]
        else:
            return m.x[i, p, m_aval, t] == rho * m.x[i, p, m_amont, t]

    m.c4_coherence = pyo.Constraint(
        [(i, p, ma, mb, k, t) for (i, p, ma, mb, k) in PAIRS for t in T],
        rule=c4_coherence_rule
    )

    # ------------------------------------------------------
    # C4bis -- LIAISON PK -> CRMA/CRMB SUR L'HORIZON COMPLET
    # (permet au stock PK de servir de vrai tampon inter-semaines)
    # ------------------------------------------------------
    m.PAIRS_PK_CR = pyo.Set(initialize=PAIRS_PK_CR, dimen=3)

    def c4bis_pk_cr_horizon_rule(m, i, p, mach):
        rho_pk = rendements["PK"]
        total_aval = sum(m.x[i, p, mach, t] for t in T)
        total_pk = sum(m.x[i, p, "PK", t] for t in T)
        return total_aval <= rho_pk * total_pk + EPS

    m.c4bis_pk_cr_horizon = pyo.Constraint(
        m.PAIRS_PK_CR,
        rule=c4bis_pk_cr_horizon_rule
    )
    # ------------------------------------------------------
    # C5-C6 -- STOCKS INTERPROCESS
    # ------------------------------------------------------
    stock_inter_data = data["stock_inter"]
    
    def c5_bilan_inter(m, k, t):
        info = INTERPROCESS[k]
        m_amont = info["amont"]
        avals = info["aval"]

        entrees = 0.0
        for (i, p) in IP:
            chemin = cmd[i]["chemins"][p]
            if m_amont in chemin:
                idx = chemin.index(m_amont)
                if idx + 1 < len(chemin) and chemin[idx + 1] in avals:
                    entrees += rendements[m_amont] * m.x[i, p, m_amont, t]
        
        sorties = 0.0
        for (i, p) in IP:
            for mach in avals:
                if mach in cmd[i]["chemins"][p]:
                    chemin = cmd[i]["chemins"][p]
                    idx = chemin.index(mach)
                    if idx > 0 and chemin[idx - 1] == m_amont:
                        sorties += m.x[i, p, mach, t]
        
        return m.Iinter[k, t] == m.Iinter[k, t - 1] + entrees - sorties

    m.c5_bilan_inter = pyo.Constraint(m.K, m.T, rule=c5_bilan_inter)

    for k in K:
        if k in stock_inter_data:
            m.Iinter[k, 0].fix(stock_inter_data[k]["init"])
        else:
            m.Iinter[k, 0].fix(0)

    def c6_min_inter(m, k, t):
        if k in stock_inter_data:
            return m.Iinter[k, t] >= stock_inter_data[k]["min"]
        return pyo.Constraint.Feasible
    
    def c6_max_inter(m, k, t):
        if k in stock_inter_data:
            return m.Iinter[k, t] <= stock_inter_data[k]["max"]
        return pyo.Constraint.Feasible
    
    m.c6_min_inter = pyo.Constraint(m.K, m.T, rule=c6_min_inter)
    m.c6_max_inter = pyo.Constraint(m.K, m.T, rule=c6_max_inter)

    print("[OK] Contraintes C4, C5, C6 (interprocess) construites")

    # ------------------------------------------------------
    # C7-C8 -- STOCKS PRODUITS FINIS (RIGUEUR MAXIMALE)
    # ============================================================
    
    # C7a: Bilan du stock physique
    def c7a_bilan_stock_physique(m, f, t):
        if t == min(T):
            stock_prec = stock_fini[f]["init"]
        else:
            stock_prec = m.StockPhysique[f, t-1]
        
        production_conforme = sum(
            rendements[cmd[i]["chemins"][p][-1]] * m.x[i, p, cmd[i]["chemins"][p][-1], t]
            for (i, p) in IP if cmd[i]["famille"] == f
        )
        
        return m.StockPhysique[f, t] == stock_prec + production_conforme - m.LivraisonsReelles[f, t]
    
    m.c7a_bilan_stock_physique = pyo.Constraint(m.F, m.T, rule=c7a_bilan_stock_physique)
    
    # C7b: Évolution de la dette
    def c7b_evolution_dette(m, f, t):
        if t == min(T):
            dette_prec = 0
        else:
            dette_prec = m.Dette[f, t-1]
        
        # Nouvelles promesses = commandes avec semaine_liv = t (independamment de y)
        nouvelles_promesses = sum(
            cmd[i]["tonnage"]
            for i in data["I"] 
            if cmd[i]["famille"] == f and cmd[i]["semaine_liv"] == t
        )
        
        return m.Dette[f, t] == dette_prec + nouvelles_promesses - m.LivraisonsReelles[f, t]
    
    m.c7b_evolution_dette = pyo.Constraint(m.F, m.T, rule=c7b_evolution_dette)
    
    # C7c: On ne peut pas livrer plus que la dette existante
    def c7c_livraison_limitee_par_dette(m, f, t):
        if t == min(T):
            dette_prec = 0
        else:
            dette_prec = m.Dette[f, t-1]
        
        nouvelles_promesses = sum(
            cmd[i]["tonnage"]
            for i in data["I"] 
            if cmd[i]["famille"] == f and cmd[i]["semaine_liv"] == t
        )
        
        return m.LivraisonsReelles[f, t] <= dette_prec + nouvelles_promesses
    
    m.c7c_livraison_limitee_par_dette = pyo.Constraint(m.F, m.T, rule=c7c_livraison_limitee_par_dette)
    
    # C8a: Stock physique minimum (à chaque semaine !)
    def c8a_min_stock_physique(m, f, t):
        return m.StockPhysique[f, t] >= stock_fini[f]["min"]
    
    m.c8a_min_stock_physique = pyo.Constraint(m.F, m.T, rule=c8a_min_stock_physique)
    
    # C8b: Stock physique maximum (capacité entrepôt)
    def c8b_max_stock_physique(m, f, t):
        return m.StockPhysique[f, t] <= stock_fini[f]["max"]
    
    m.c8b_max_stock_physique = pyo.Constraint(m.F, m.T, rule=c8b_max_stock_physique)
    
    # C8c: On ne peut pas livrer plus que ce qu'on a en stock physique
    def c8c_livraison_par_stock_disponible(m, f, t):
        if t == min(T):
            stock_prec = stock_fini[f]["init"]
        else:
            stock_prec = m.StockPhysique[f, t-1]
        
        production_conforme = sum(
            rendements[cmd[i]["chemins"][p][-1]] * m.x[i, p, cmd[i]["chemins"][p][-1], t]
            for (i, p) in IP if cmd[i]["famille"] == f
        )
        
        return m.LivraisonsReelles[f, t] <= stock_prec + production_conforme
    
    m.c8c_livraison_par_stock_disponible = pyo.Constraint(m.F, m.T, rule=c8c_livraison_par_stock_disponible)

    # Initialisation des stocks (t=0)
    for f in F:
        m.StockPhysique[f, 0].fix(stock_fini[f]["init"])
        m.Dette[f, 0].fix(0)

    print("[OK] Contraintes C7-C8 (stocks PF rigueur maximale) construites")
    print("     Stock physique min/max vérifiés à CHAQUE semaine")
    print("     Dette et livraisons réelles séparées")

    # ------------------------------------------------------
    # C11/C14 -- RETARDS (B2)
    # ------------------------------------------------------
    if activer_B2:
        def c11_retard_rule(m, i, p, mach, t):
            t_liv = cmd[i]["semaine_liv"]
            if t <= t_liv:
                return pyo.Constraint.Feasible
            r_min = t - t_liv
            if r_min > max(R):
                return m.x[i, p, mach, t] == 0
            allowed = sum(m.z[i, r] for r in R if r >= r_min)
            return m.x[i, p, mach, t] <= cmd[i]["tonnage"] * allowed

        m.c11_retard = pyo.Constraint(
            [(i, p, mach, t) for (i, p, mach) in IPM for t in T],
            rule=c11_retard_rule
        )

        def c14_unicite_rule(m, i):
            return sum(m.z[i, r] for r in R) == m.y[i]
        m.c14_unicite = pyo.Constraint(m.I, rule=c14_unicite_rule)

    else:
        def c11_base_rule(m, i, p, mach, t):
            if t > cmd[i]["semaine_liv"]:
                return m.x[i, p, mach, t] == 0
            return pyo.Constraint.Feasible

        m.c11_base = pyo.Constraint(
            [(i, p, mach, t) for (i, p, mach) in IPM for t in T],
            rule=c11_base_rule
        )

    # ------------------------------------------------------
    # C12 -- LIEN PRODUCTION-ACCEPTATION
    # ------------------------------------------------------
    def c12_lien_rule(m, i, p, mach, t):
        return m.x[i, p, mach, t] <= m.y[i] * BIG_M
    
    m.c12_lien = pyo.Constraint(
        [(i, p, mach, t) for (i, p, mach) in IPM for t in T],
        rule=c12_lien_rule
    )

    print("[OK] Contraintes C11/C14, C12 construites")

    # ------------------------------------------------------
    # C16-C18 -- CAMPAGNES (B4)
    # ------------------------------------------------------
    if activer_B4:
        T_camp_min = 100.0
        
        def c16_dedication_rule(m, mach, t):
            return sum(m.w[mach, f, t] for f in F) <= 1
        m.c16_dedication = pyo.Constraint(m.M, m.T, rule=c16_dedication_rule)

        def c17_activation_rule(m, mach, f, t):
            expr = sum(m.x[i, p, mach, t] for (i, p, mm) in IPM if mm == mach and cmd[i]["famille"] == f)
            if isinstance(expr, (int, float)) and expr == 0:
                return pyo.Constraint.Feasible
            return expr <= BIG_M * m.w[mach, f, t]
        m.c17_activation = pyo.Constraint(m.M, m.F, m.T, rule=c17_activation_rule)

        def c18_min_campagne_rule(m, mach, f, t):
            expr = sum(m.x[i, p, mach, t] for (i, p, mm) in IPM if mm == mach and cmd[i]["famille"] == f)
            if isinstance(expr, (int, float)) and expr == 0:
                return pyo.Constraint.Feasible
            return expr >= T_camp_min * m.w[mach, f, t]
        m.c18_min_campagne = pyo.Constraint(m.M, m.F, m.T, rule=c18_min_campagne_rule)

        print("[OK] Contraintes C16-C18 (campagnes B4) construites")

    print(f"\n[RESUME] Modele rigueur maximale construit avec succes.")
    print(f"  - {len(IP)} chemins valides")
    print(f"  - {len(IPM)} associations (i,p,machine)")
    print(f"  - {len(G)} grades avec flux HRC rigoureux")
    print(f"  - Stock physique min/max vérifiés à CHAQUE semaine")
    print(f"  - Dette de livraison séparée du stock physique")

    return m, IP, IPM


def pen_priorite(priorite, params):
    if priorite == "Haute":
        return params["pen_haute"]
    elif priorite == "Normale":
        return params["pen_normale"]
    else:
        return params["pen_basse"]


if __name__ == "__main__":
    data = charger_donnees()
    m, IP, IPM = construire_modele(data, activer_B2=True, activer_B4=True)
    print(f"\nNombre de (i,p) valides : {len(IP)}")
    print(f"Nombre de (i,p,machine) : {len(IPM)}")
    
    print("\nExemple de chemins pour CMD-001 (HDG):")
    cmd = data["commandes"]
    for p in range(len(cmd["CMD-001"]["chemins"])):
        print(f"  Chemin {p}: {cmd['CMD-001']['chemins'][p]}")