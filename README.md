# MaCave — Gestion collaborative d'une cave à vin

Application web multi-utilisateurs permettant à des amateurs de vin de gérer leur
cave, de suivre leurs bouteilles et de partager leurs appréciations. Projet réalisé
dans le cadre du module **ETRS711 — Conception et programmation orientée objet**
(Master Informatique).

Chaque utilisateur dispose d'une cave privée composée d'étagères. Plusieurs
exemplaires d'un même vin peuvent être stockés dans une ou plusieurs étagères. Lors
d'une dégustation, une bouteille peut être archivée et associée à une note et à un
commentaire visibles par la communauté.

---

## Fonctionnalités

- **Comptes & sécurité** : inscription, connexion, modification du profil ; mots de
  passe hachés (jamais en clair) ; contrôle d'accès côté serveur, y compris sur accès
  direct à une URL.
- **Caves & étagères** : création, renommage, modification de capacité et suppression
  d'étagères, avec taux d'occupation.
- **Catalogue partagé** : création de références de vin (domaine, cuvée, type,
  millésime, région, description, photo) avec déduplication automatique.
- **Stock** : ajout de plusieurs exemplaires identiques, déplacement entre étagères,
  retrait définitif ou archivage après dégustation.
- **Évaluations communautaires** : note (0–20) et commentaire à l'archivage, moyenne
  communautaire par référence.
- **Consultation** : recherche par nom/domaine, filtre par type, tri bidirectionnel,
  historique des dégustations et tableau de bord personnel.

---

## Pile technique

| Composant | Technologie |
| --- | --- |
| Langage & framework web | Python 3 + Flask |
| Base & accès aux données | SQLite (module standard `sqlite3`) |
| Interface | Jinja2, HTML5, CSS3 (intégré aux gabarits) |
| Sécurité des mots de passe | Werkzeug (`generate_password_hash`) |
| Tests | `unittest` (bibliothèque standard) |
| Modélisation UML | draw.io (sources éditables dans `uml/`) |

---

## Installation

Prérequis : Python 3.9 ou plus récent.

```bash
# (optionnel mais recommandé) un environnement virtuel
python -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate

# dépendances
pip install -r requirements.txt
```

## Initialisation de la base & lancement

Aucune étape d'initialisation manuelle n'est nécessaire : la base `macave.db` et ses
tables sont **créées automatiquement au premier lancement**, et un jeu de démonstration
est chargé.

```bash
python app.py
```

Puis ouvrir **http://127.0.0.1:5000** dans un navigateur.

**Comptes de démonstration** (deux utilisateurs, plusieurs étagères, vins, exemplaires
identiques et évaluations) :

| Identifiant | Mot de passe |
| --- | --- |
| `alice` | `alice123` |
| `bob` | `bob123` |

**Remettre la base à zéro** : arrêter l'application, supprimer le fichier `macave.db`,
puis relancer `python app.py` (la base de démonstration est régénérée). Pour démarrer
sur une base vraiment vide, commenter l'appel à `jeu_de_demonstration(conn)` dans
`app.py` avant de relancer.

**Clé secrète (optionnel)** : définir la variable d'environnement `MACAVE_SECRET_KEY`
pour fixer la clé de signature des sessions ; sinon une clé aléatoire est générée à
chaque démarrage. Aucun secret n'est stocké dans le dépôt.

## Tests

```bash
python -m unittest -v
```

13 tests couvrent les règles métier et les cas limites : dépassement de capacité,
retrait d'un exemplaire, déplacement, archivage, moyenne communautaire, contrôle
d'accès, données invalides et **persistance après redémarrage**.

---

## Structure du projet

```
.
├── app.py                     # Couche web Flask : routes, sessions, formulaires
├── macave_SGBD_SQLite.py      # Couche métier (classes) + accès SQLite
├── test_macave.py             # Tests automatisés (unittest)
├── requirements.txt
├── templates/                 # Gabarits Jinja2 (HTML + CSS intégré dans base.html)
├── static/uploads/            # Photos d'étiquettes téléversées (ignorées par Git)
└── uml/                       # Diagrammes UML, sources éditables (.drawio)
    ├── diagramme_cas_utilisation.drawio
    ├── diagramme_classes.drawio
    └── diagramme_sequence_archivage.drawio
```

## Architecture

Le projet suit une architecture en quatre couches, simple et modulaire :

1. **Interface** — gabarits `templates/`, CSS intégré à `base.html`.
2. **Couche web** (`app.py`) — routes, sessions, validation des requêtes, réponses
   HTTP. Ne contient aucune règle métier : elle délègue.
3. **Couche métier** (`macave_SGBD_SQLite.py`) — classes `Utilisateur`, `Cave`,
   `Etagere`, `Vin`, `Bouteille`, `Evaluation`, qui appliquent les règles de gestion.
   Ces classes sont **testables indépendamment des requêtes HTTP**.
4. **Persistance** — tables, contraintes et transactions SQLite.

## Modèle relationnel

Six tables : `utilisateur`, `cave`, `etagere`, `vin`, `bouteille`, `evaluation`.

- Un **utilisateur** possède une **cave** (relation 1–1).
- Une **cave** contient des **étagères** et des **bouteilles**.
- Une **bouteille** (exemplaire physique) référence un **vin** (référence partagée du
  catalogue) : cinq bouteilles identiques = cinq lignes `bouteille` pour une seule
  ligne `vin`.
- Une **évaluation** est liée à une bouteille archivée et à son auteur.

L'intégrité est en partie garantie par la base elle-même : clés étrangères
(`PRAGMA foreign_keys = ON`), contraintes `CHECK` (capacité > 0, prix ≥ 0, note entre
0 et 20, cohérence statut/étagère) et contraintes `UNIQUE` (identifiant, nom d'étagère
par cave, clé d'identité d'un vin).

## Choix de conception & conventions

- **Référence vs exemplaire** : la distinction `Vin` / `Bouteille` est explicite dans
  le modèle objet et le modèle relationnel.
- **Anti-doublons** : l'identité d'un vin repose sur domaine, nom/cuvée, type,
  millésime et région. Une clé d'identité normalisée (espaces multiples supprimés,
  casse ignorée via `casefold`) est stockée en colonne `UNIQUE` ; le prix et la
  description ne définissent pas l'identité.
- **Contrôle d'accès** : toute donnée privée passe par la classe `Cave`, qui vérifie
  l'appartenance et lève une erreur d'accès interdit sinon (règles R1 et R12).
- **Atomicité** : l'ajout multiple et l'archivage sont transactionnels (`with conn:`) —
  l'opération réussit entièrement ou est annulée, sans modification partielle.
- **Tri et valeurs absentes** : le tri utilise une liste blanche de colonnes (pas
  d'injection) et place toujours les valeurs nulles en dernier, dans les deux sens. Un
  vin non évalué affiche « Non évalué » et non zéro.
- **Tri par prix** : le stock affichant une ligne par exemplaire, le tri par prix porte
  sur chaque bouteille.

## Diagrammes UML

Les sources éditables (draw.io) sont dans `uml/` :

- **Cas d'utilisation** — interactions principales.
- **Classes** — attributs typés, méthodes, associations et multiplicités.
- **Séquence** — archivage d'une bouteille avec évaluation.

## Règles métier (R1–R12)

| Règle | Où elle est appliquée |
| --- | --- |
| R1 — isolation des données privées | `Cave.obtenir_etagere` / `obtenir_bouteille` |
| R2 — noms d'étagères uniques par cave | contrainte `UNIQUE (cave_id, nom)` |
| R3 — occupation ≤ capacité | `Cave.ajouter_bouteilles` |
| R4 — capacité ≥ occupation | `Etagere.modifier_capacite` |
| R5 — étagère non vide non supprimable | `Etagere.supprimer` |
| R6 — retrait d'un exemplaire | `Bouteille.retirer` |
| R7 — déplacement respecte la capacité | `Bouteille.deplacer` |
| R8 — pas de double archivage | `Bouteille.archiver` / `retirer` |
| R9 / R10 — calcul de la moyenne | `Vin.note_moyenne` |
| R11 — évaluation liée auteur/vin/bouteille | `Bouteille.archiver` |
| R12 — modification de ses seules évaluations | `Evaluation.modifier` |

## Limites connues

- Pas de jeton anti-CSRF sur les formulaires (acceptable pour une application exécutée
  localement sur les postes de TP).
- Validation d'adresse électronique volontairement simple.
- Les photos d'étiquettes sont stockées sur le disque local (dossier `static/uploads/`,
  non versionné).

Aucune fonctionnalité du périmètre n'est inachevée ; ces points sont des choix de
simplification adaptés au cadre du projet.
