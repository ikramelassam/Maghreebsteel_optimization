# Interface React – Maghreb Steel Optimization Dashboard

## Objectif
Concevoir une interface web professionnelle pour un outil d’aide à la décision en planification de production, destiné aux responsables de production et aux équipes Supply Chain. L’interface doit permettre de visualiser les résultats d’optimisation, de paramétrer des scénarios et d’explorer les données de production.

## Structure générale
- **Barre latérale gauche** fixe, avec logo et menu de navigation :
  - Tableau de bord
  - Commandes
  - Plan de marche
  - Capacités
  - Séries (Stocks)
  - Résultats
  - Scénarios
- **Zone principale** : contenu dynamique selon la page sélectionnée.
- **En‑tête** : titre de la page, sélecteur de scénario, bouton « Lancer l’optimisation », notifications, avatar utilisateur.

## Couleurs et charte graphique
- Palette principale : bleu profond (#1E3A5F) pour les titres et la barre latérale, bleu ciel (#2E86AB) pour les accents, vert (#27AE60) pour les indicateurs positifs, orange (#F39C12) pour les alertes, rouge (#E74C3C) pour les critiques.
- Fond : blanc (#FFFFFF) et gris clair (#F8F9FA).
- Typographie : sans‑serif moderne (ex. Inter ou Roboto).
- Icônes : utiliser une bibliothèque comme Feather Icons ou Font Awesome.

## Pages et composants

### 1. Tableau de bord (page principale)
- **En‑tête** : titre « Tableau de bord » + date de l’horizon.
- **Ligne de KPI** (4 cartes) :
  - Marge totale (MAD)
  - Taux de service (%)
  - Commandes honorées / total
  - Taux d’utilisation moyen (%)
  Chaque carte contient un icône, la valeur en grand, un sous‑titre et un indicateur de variation (vs scénario précédent).
- **Graphique « Plan de marche global »** : barres empilées par semaine, avec des couleurs différentes pour chaque famille (CRC, HDG, PPGI, BACR). Axe des X : Semaine 1 à 4. Axe des Y : Tonnage produit fini.
- **Graphique « Répartition de la marge par famille »** : graphique en anneau (donut) avec les pourcentages et valeurs en MAD.
- **Graphique « Statut des commandes »** : barres horizontales ou anneau pour les statuts (honoré à l’échéance, en avance, en retard, refusé) – en tonnage.
- **Tableau « Utilisation des lignes »** : colonnes : Ligne, Capacité disponible (T), Semaine 1 à 4 (avec valeur numérique et barre de progression colorée). Les cellules dont l’utilisation > 90% sont surlignées en orange/rouge.
- **Liste « Contraintes bloquantes »** : tableau avec colonnes Contrainte, CM (shadow price), Client, Produit. Classement par CM décroissant.
- **Liste « Commandes refusées »** : tableau avec ID, Client, Produit, Tonnage, Raison (avec lien vers détail).
- **Pied de page** : bouton « Voir toutes les commandes refusées » et « Voir toutes les contraintes ».

### 2. Page Commandes
- **Filtres** : Famille, Grade, Priorité, Semaine livraison, Statut (acceptée/refusée/retard).
- **Tableau** : toutes les colonnes du fichier d’entrée + statut, semaine de production réelle, retard éventuel.
- **Actions** : possibilité de forcer l’acceptation/refus (toggle) et de relancer l’optimisation.

### 3. Page Plan de marche
- **Vue par machine** : sélecteur de machine (PK, CRMA, CRMB, BAF, SKP, LGA, LGB).
- **Graphique Gantt** ou **calendrier** montrant pour chaque semaine les tonnes produites par famille.
- **Tableau des flux** détaillé par commande, chemin, machine et semaine.

### 4. Page Capacités
- **Tableaux des cadences** et **arrêts planifiés** modifiables (champs de saisie).
- **Bouton « Mettre à jour les capacités »** pour recharger les données et lancer l’optimisation.

### 5. Page Stocks
- **Graphiques linéaires** pour chaque catégorie (PK, interprocess, finis) montrant l’évolution sur l’horizon (t=0 à 4).
- **Tableaux récapitulatifs** avec min/max et statut de respect.

### 6. Page Résultats
- **Onglets** : Production, Commandes, Marges, Utilisation.
- **Tableaux exportables** (bouton Excel, PDF).
- **Graphiques supplémentaires** : Pareto des marges par commande, répartition par client.

### 7. Page Scénarios
- **Liste des scénarios** (nom, date, marge, taux service, statut).
- **Bouton « Nouveau scénario »** : dupliquer le scénario actuel, modifier les paramètres, relancer.
- **Comparateur** : sélectionner deux scénarios pour afficher leurs KPI et graphiques côte à côte.

## Interactivité et comportement
- **Chargement des données** : via téléchargement d’un fichier Excel ou sélection d’un fichier prédéfini.
- **Lancement de l’optimisation** : appeler une API REST (backend Python/Flask ou FastAPI) qui exécute le modèle Pyomo. Afficher une barre de progression et des logs.
- **Temps réel** : possibilité d’annuler une optimisation en cours.
- **Notifications** : toast pour confirmer les actions (sauvegarde, lancement, export).
- **Responsive** : l’interface doit s’adapter aux tablettes mais pas nécessairement aux mobiles (usage métier).

## Livrables attendus
- Maquettes Figma ou design exportable en HTML/CSS (avec composants React).
- Guidelines pour l’intégration (polices, espacements, ombres, animations douces).
- Fichier de design avec les états (normal, hover, focus, chargement).

## Contraintes techniques
- Le frontend sera développé en React (ou Next.js) avec une bibliothèque UI comme Material-UI ou Ant Design, ou bien Tailwind CSS.
- Les graphiques seront réalisés avec Chart.js ou Recharts.
- Les tableaux avec React‑Table ou AG Grid.
- Les icônes proviendront de Font Awesome ou Lucide.

---

**Note** : Le design doit refléter un outil professionnel, moderne, épuré et orienté données. Les couleurs et la disposition générale doivent s’inspirer de l’image fournie (dashboard avec cartes, barres latérales, graphiques).