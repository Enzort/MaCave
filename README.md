# MaCave

Application web Flask de gestion collaborative d'une cave à vin (mini-projet ETRS711).

## Installation
    pip install -r requirements.txt

## Lancement
    python app.py
Puis ouvrir http://127.0.0.1:5000. La base `macave.db` est créée au premier lancement,
avec un jeu de démonstration : `alice / alice123` et `bob / bob123`.
Facultatif : définir la variable d'environnement `MACAVE_SECRET_KEY` (sinon clé aléatoire).

## Tests
    python -m unittest -v

## Organisation
- `macave_SGBD_SQLite.py` : classes métier (Utilisateur, Cave, Etagere, Vin, Bouteille, Evaluation) et base SQLite
- `app.py` : routes Flask (sessions, formulaires)
- `templates/` : pages HTML

## Conventions
- Une référence de vin (table `vin`) est distincte de ses exemplaires (table `bouteille`).
- Anti-doublons : la clé d'identité d'un vin est construite sans espaces superflus ni casse.
- Tri : les valeurs absentes (ex. vin non évalué) sont toujours placées en dernier.
- Tri par prix : il porte sur chaque exemplaire.
