"""MaCave - classes métier + accès à la base SQLite."""
import sqlite3
from datetime import date
from werkzeug.security import generate_password_hash, check_password_hash

TYPES_VIN = ["rouge", "blanc", "rosé", "effervescent"]


# ---------------------------------------------------------------------
# Erreurs
# ---------------------------------------------------------------------
class MaCaveError(Exception):
    """Erreur métier : le message est affiché tel quel à l'utilisateur."""

class AccesInterditError(MaCaveError):
    """Tentative d'accès aux données d'un autre utilisateur (R1, R12)."""

class IntrouvableError(MaCaveError):
    """Identifiant qui n'existe pas."""


# ---------------------------------------------------------------------
# Fonctions utilitaires
# ---------------------------------------------------------------------
def entier_positif(valeur, champ):
    try:
        n = int(str(valeur).strip())
    except ValueError:
        raise MaCaveError(champ + " doit être un entier strictement positif.")
    if n <= 0:
        raise MaCaveError(champ + " doit être un entier strictement positif.")
    return n


def lire_prix(valeur):
    try:
        prix = float(str(valeur).strip().replace(",", "."))
    except ValueError:
        raise MaCaveError("Le prix d'achat doit être un nombre.")
    if prix < 0:
        raise MaCaveError("Le prix d'achat ne peut pas être négatif.")
    return prix


def lire_note(valeur):
    try:
        note = int(str(valeur).strip())
    except ValueError:
        raise MaCaveError("La note doit être un entier entre 0 et 20.")
    if note < 0 or note > 20:
        raise MaCaveError("La note doit être un entier entre 0 et 20.")
    return note


def lire_id(valeur):
    try:
        return int(valeur)
    except (TypeError, ValueError):
        raise IntrouvableError("Élément introuvable.")


def filtre_recherche(recherche, type_vin):
    """Morceau de WHERE commun : recherche sur nom/domaine + filtre sur le type."""
    sql, params = "", []
    if recherche and recherche.strip():
        sql += " AND (v.nom LIKE ? OR v.domaine LIKE ?)"
        params += ["%" + recherche.strip() + "%"] * 2
    if type_vin:
        sql += " AND v.type = ?"
        params.append(type_vin)
    return sql, params


def clause_tri(tri, ordre, colonnes, defaut):
    """ORDER BY avec liste blanche. Les valeurs absentes (NULL) sont toujours en dernier."""
    col = colonnes.get(tri, colonnes[defaut])
    sens = "DESC" if ordre == "desc" else "ASC"
    return " ORDER BY (" + col + " IS NULL), " + col + " COLLATE NOCASE " + sens


# Moyenne communautaire d'un vin (v = table vin de la requête englobante)
NOTE_MOYENNE = """(SELECT AVG(e2.note) FROM evaluation e2
                   JOIN bouteille b2 ON b2.id = e2.bouteille_id WHERE b2.vin_id = v.id)"""


# ---------------------------------------------------------------------
# Base de données
# ---------------------------------------------------------------------
class DB:
    def __init__(self, chemin="macave.db"):
        self.conn = sqlite3.connect(chemin, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.creer_tables()

    def creer_tables(self):
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS utilisateur (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            identifiant TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL,
            mot_de_passe_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cave (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            utilisateur_id INTEGER NOT NULL UNIQUE REFERENCES utilisateur(id)
        );
        CREATE TABLE IF NOT EXISTS etagere (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cave_id INTEGER NOT NULL REFERENCES cave(id),
            nom TEXT NOT NULL COLLATE NOCASE,
            capacite_max INTEGER NOT NULL CHECK (capacite_max > 0),
            UNIQUE (cave_id, nom)
        );
        CREATE TABLE IF NOT EXISTS vin (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domaine TEXT NOT NULL,
            nom TEXT NOT NULL,
            type TEXT NOT NULL CHECK (type IN ('rouge','blanc','rosé','effervescent')),
            millesime INTEGER NOT NULL,
            region TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            photo TEXT,
            cle_identite TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS bouteille (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vin_id INTEGER NOT NULL REFERENCES vin(id),
            cave_id INTEGER NOT NULL REFERENCES cave(id),
            etagere_id INTEGER REFERENCES etagere(id),
            prix_achat REAL NOT NULL CHECK (prix_achat >= 0),
            date_ajout TEXT NOT NULL,
            date_sortie TEXT,
            statut TEXT NOT NULL CHECK (statut IN ('en_stock','archivee')),
            CHECK ((statut = 'en_stock' AND etagere_id IS NOT NULL)
                OR (statut = 'archivee' AND etagere_id IS NULL))
        );
        CREATE TABLE IF NOT EXISTS evaluation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bouteille_id INTEGER NOT NULL UNIQUE REFERENCES bouteille(id),
            auteur_id INTEGER NOT NULL REFERENCES utilisateur(id),
            note INTEGER NOT NULL CHECK (note BETWEEN 0 AND 20),
            commentaire TEXT,
            date TEXT NOT NULL
        );
        """)
        self.conn.commit()


# ---------------------------------------------------------------------
# Utilisateur
# ---------------------------------------------------------------------
class Utilisateur:
    def __init__(self, identifiant, email, id=None, mot_de_passe_hash=None, conn=None):
        self.id = id
        self.identifiant = (identifiant or "").strip()
        self.email = (email or "").strip()
        self.mot_de_passe_hash = mot_de_passe_hash
        self.conn = conn

    @staticmethod
    def verifier_email(email):
        if "@" not in email or email.startswith("@") or email.endswith("@"):
            raise MaCaveError("Adresse électronique invalide.")

    @staticmethod
    def hacher(mot_de_passe):
        if not mot_de_passe or len(mot_de_passe) < 6:
            raise MaCaveError("Le mot de passe doit contenir au moins 6 caractères.")
        return generate_password_hash(mot_de_passe)

    def sauvegarder(self, mot_de_passe):
        """Crée le compte et sa cave privée (une seule transaction)."""
        if not self.identifiant:
            raise MaCaveError("L'identifiant est obligatoire.")
        self.verifier_email(self.email)
        self.mot_de_passe_hash = self.hacher(mot_de_passe)
        try:
            with self.conn:
                cur = self.conn.execute(
                    "INSERT INTO utilisateur (identifiant, email, mot_de_passe_hash) VALUES (?,?,?)",
                    (self.identifiant, self.email, self.mot_de_passe_hash))
                self.id = cur.lastrowid
                self.conn.execute("INSERT INTO cave (utilisateur_id) VALUES (?)", (self.id,))
        except sqlite3.IntegrityError:
            raise MaCaveError("Cet identifiant est déjà utilisé.")

    def verifier_mot_de_passe(self, mot_de_passe):
        return check_password_hash(self.mot_de_passe_hash, mot_de_passe)

    def changer_mot_de_passe(self, mot_de_passe):
        nouveau_hash = self.hacher(mot_de_passe)
        with self.conn:
            self.conn.execute("UPDATE utilisateur SET mot_de_passe_hash=? WHERE id=?",
                              (nouveau_hash, self.id))
        self.mot_de_passe_hash = nouveau_hash

    def modifier_email(self, email):
        email = (email or "").strip()
        self.verifier_email(email)
        with self.conn:
            self.conn.execute("UPDATE utilisateur SET email=? WHERE id=?", (email, self.id))
        self.email = email

    @classmethod
    def depuis_ligne(cls, row, conn):
        return cls(row["identifiant"], row["email"], row["id"], row["mot_de_passe_hash"], conn)

    @classmethod
    def obtenir_par_id(cls, id, conn):
        row = conn.execute("SELECT * FROM utilisateur WHERE id=?", (id,)).fetchone()
        return cls.depuis_ligne(row, conn) if row else None

    @classmethod
    def authentifier(cls, identifiant, mot_de_passe, conn):
        """Retourne l'utilisateur si identifiant et mot de passe sont corrects, sinon None."""
        row = conn.execute("SELECT * FROM utilisateur WHERE identifiant=?",
                           ((identifiant or "").strip(),)).fetchone()
        if row is None:
            return None
        u = cls.depuis_ligne(row, conn)
        return u if u.verifier_mot_de_passe(mot_de_passe) else None

    def cave(self):
        row = self.conn.execute("SELECT id FROM cave WHERE utilisateur_id=?", (self.id,)).fetchone()
        return Cave(self.id, row["id"], self.conn)


# ---------------------------------------------------------------------
# Etagere
# ---------------------------------------------------------------------
class Etagere:
    def __init__(self, nom, capacite_max, cave_id, id=None, conn=None):
        nom = (nom or "").strip()
        if not nom:
            raise MaCaveError("Le nom de l'étagère est obligatoire.")
        self.id = id
        self.nom = nom
        self.capacite_max = entier_positif(capacite_max, "La capacité")
        self.cave_id = cave_id
        self.conn = conn

    @classmethod
    def depuis_ligne(cls, row, conn):
        return cls(row["nom"], row["capacite_max"], row["cave_id"], row["id"], conn)

    def sauvegarder(self):
        try:
            with self.conn:
                cur = self.conn.execute(
                    "INSERT INTO etagere (cave_id, nom, capacite_max) VALUES (?,?,?)",
                    (self.cave_id, self.nom, self.capacite_max))
                self.id = cur.lastrowid
        except sqlite3.IntegrityError:                      # R2
            raise MaCaveError("Une étagère « " + self.nom + " » existe déjà dans votre cave.")

    def occupation(self):
        return self.conn.execute(
            "SELECT COUNT(*) FROM bouteille WHERE etagere_id=? AND statut='en_stock'",
            (self.id,)).fetchone()[0]

    def places_libres(self):
        return self.capacite_max - self.occupation()

    def peut_accueillir(self, n):
        return n <= self.places_libres()

    def bouteilles(self):
        return self.conn.execute("""
            SELECT b.id AS bouteille_id, b.prix_achat, v.id AS vin_id,
                   v.domaine, v.nom, v.type, v.millesime, v.region
            FROM bouteille b JOIN vin v ON v.id = b.vin_id
            WHERE b.etagere_id=? AND b.statut='en_stock'
            ORDER BY v.domaine COLLATE NOCASE, v.nom COLLATE NOCASE, b.id""", (self.id,)).fetchall()

    def renommer(self, nom):
        nom = (nom or "").strip()
        if not nom:
            raise MaCaveError("Le nom de l'étagère est obligatoire.")
        try:
            with self.conn:
                self.conn.execute("UPDATE etagere SET nom=? WHERE id=?", (nom, self.id))
        except sqlite3.IntegrityError:                      # R2
            raise MaCaveError("Une étagère « " + nom + " » existe déjà dans votre cave.")
        self.nom = nom

    def modifier_capacite(self, capacite):
        capacite = entier_positif(capacite, "La capacité")
        occ = self.occupation()
        if capacite < occ:                                  # R4
            raise MaCaveError("Capacité minimale : " + str(occ) + " (bouteilles actuellement stockées).")
        with self.conn:
            self.conn.execute("UPDATE etagere SET capacite_max=? WHERE id=?", (capacite, self.id))
        self.capacite_max = capacite

    def supprimer(self):
        occ = self.occupation()
        if occ > 0:                                         # R5
            raise MaCaveError("L'étagère « " + self.nom + " » contient encore " + str(occ) +
                              " bouteille(s) : déplacez-les ou retirez-les d'abord.")
        with self.conn:
            self.conn.execute("DELETE FROM etagere WHERE id=?", (self.id,))


# ---------------------------------------------------------------------
# Vin : référence du catalogue partagé
# ---------------------------------------------------------------------
class Vin:
    COLONNES_TRI = {"domaine": "v.domaine", "nom": "v.nom", "type": "v.type",
                    "millesime": "v.millesime", "region": "v.region",
                    "note_moyenne": NOTE_MOYENNE}

    def __init__(self, domaine, nom, type, millesime, region,
                 description="", photo=None, id=None, conn=None):
        # on enlève les espaces en trop
        self.domaine = " ".join((domaine or "").split())
        self.nom = " ".join((nom or "").split())
        self.region = " ".join((region or "").split())
        if not (self.domaine and self.nom and self.region):
            raise MaCaveError("Domaine, nom et région sont obligatoires.")
        self.type = str(type).strip().lower()
        if self.type not in TYPES_VIN:
            raise MaCaveError("Type de vin invalide (rouge, blanc, rosé ou effervescent).")
        try:
            self.millesime = int(str(millesime).strip())
        except ValueError:
            raise MaCaveError("Le millésime doit être un nombre entier.")
        if self.millesime < 1800 or self.millesime > date.today().year + 1:
            raise MaCaveError("Millésime hors limites.")
        self.description = description or ""
        self.photo = photo
        self.id = id
        self.conn = conn

    @staticmethod
    def normaliser(texte):
        """Espaces multiples supprimés et casse ignorée."""
        return " ".join(texte.split()).casefold()

    def cle_identite(self):
        """Identité d'un vin : domaine, nom, type, millésime, région (pas le prix)."""
        return "|".join([self.normaliser(self.domaine), self.normaliser(self.nom), self.type,
                         str(self.millesime), self.normaliser(self.region)])

    def id_existant(self):
        """Id de la référence si elle est déjà dans le catalogue, sinon None."""
        row = self.conn.execute("SELECT id FROM vin WHERE cle_identite=?",
                                (self.cle_identite(),)).fetchone()
        return row["id"] if row else None

    def sauvegarder(self):
        """Crée la référence, ou récupère l'existante si c'est un doublon."""
        existant = self.id_existant()
        if existant:
            self.id = existant
            return self.id
        with self.conn:
            cur = self.conn.execute(
                """INSERT INTO vin (domaine, nom, type, millesime, region, description, photo, cle_identite)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (self.domaine, self.nom, self.type, self.millesime, self.region,
                 self.description, self.photo, self.cle_identite()))
            self.id = cur.lastrowid
        return self.id

    def note_moyenne(self):
        """Moyenne des évaluations (R9, R10). None s'il n'y en a aucune."""
        return self.conn.execute("""
            SELECT AVG(e.note) FROM evaluation e JOIN bouteille b ON b.id = e.bouteille_id
            WHERE b.vin_id=?""", (self.id,)).fetchone()[0]

    @staticmethod
    def formater_note(note):
        if note is None:
            return "Non évalué"
        return "%.1f/20" % note

    def evaluations(self):
        """Évaluations de la communauté (rien sur la cave de l'auteur)."""
        return self.conn.execute("""
            SELECT e.id AS evaluation_id, e.note, e.commentaire, e.date,
                   e.auteur_id, u.identifiant AS auteur
            FROM evaluation e
            JOIN bouteille b ON b.id = e.bouteille_id
            JOIN utilisateur u ON u.id = e.auteur_id
            WHERE b.vin_id=? ORDER BY e.date DESC, e.id DESC""", (self.id,)).fetchall()

    @classmethod
    def obtenir_par_id(cls, id, conn):
        r = conn.execute("SELECT * FROM vin WHERE id=?", (id,)).fetchone()
        if r is None:
            return None
        return cls(r["domaine"], r["nom"], r["type"], r["millesime"], r["region"],
                   r["description"], r["photo"], r["id"], conn)

    @classmethod
    def catalogue(cls, conn, recherche=None, type_vin=None, tri="domaine", ordre="asc"):
        filtre, params = filtre_recherche(recherche, type_vin)
        sql = "SELECT v.*, " + NOTE_MOYENNE + " AS note_moyenne FROM vin v WHERE 1=1" + filtre
        sql += clause_tri(tri, ordre, cls.COLONNES_TRI, "domaine") + ", v.id"
        return conn.execute(sql, params).fetchall()


# ---------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------
class Evaluation:
    def __init__(self, bouteille_id, auteur_id, note, commentaire=None,
                 date_eval=None, id=None, conn=None):
        self.id = id
        self.bouteille_id = bouteille_id
        self.auteur_id = auteur_id
        self.note = lire_note(note)
        self.commentaire = (commentaire or "").strip() or None
        self.date = date_eval or date.today().isoformat()
        self.conn = conn

    def sauvegarder(self):
        """Pas de commit ici : l'appelant gère la transaction (voir Bouteille.archiver)."""
        cur = self.conn.execute(
            "INSERT INTO evaluation (bouteille_id, auteur_id, note, commentaire, date) VALUES (?,?,?,?,?)",
            (self.bouteille_id, self.auteur_id, self.note, self.commentaire, self.date))
        self.id = cur.lastrowid

    def modifier(self, note, commentaire, utilisateur_id):
        if utilisateur_id != self.auteur_id:                # R12
            raise AccesInterditError("Vous ne pouvez modifier que vos propres évaluations.")
        note = lire_note(note)
        commentaire = (commentaire or "").strip() or None
        with self.conn:
            self.conn.execute("UPDATE evaluation SET note=?, commentaire=? WHERE id=?",
                              (note, commentaire, self.id))
        self.note = note
        self.commentaire = commentaire

    def vin_id(self):
        return self.conn.execute("SELECT vin_id FROM bouteille WHERE id=?",
                                 (self.bouteille_id,)).fetchone()["vin_id"]

    @classmethod
    def obtenir_par_id(cls, id, conn):
        r = conn.execute("SELECT * FROM evaluation WHERE id=?", (id,)).fetchone()
        if r is None:
            return None
        return cls(r["bouteille_id"], r["auteur_id"], r["note"], r["commentaire"],
                   r["date"], r["id"], conn)


# ---------------------------------------------------------------------
# Bouteille : un exemplaire physique d'un vin
# ---------------------------------------------------------------------
class Bouteille:
    def __init__(self, vin_id, cave_id, etagere_id, prix_achat, date_ajout=None,
                 id=None, statut="en_stock", date_sortie=None, conn=None):
        self.id = id
        self.vin_id = vin_id
        self.cave_id = cave_id
        self.etagere_id = etagere_id          # None quand elle est archivée
        self.prix_achat = lire_prix(prix_achat)
        self.date_ajout = date_ajout or date.today().isoformat()
        self.date_sortie = date_sortie
        self.statut = statut
        self.conn = conn

    @classmethod
    def depuis_ligne(cls, row, conn):
        return cls(row["vin_id"], row["cave_id"], row["etagere_id"], row["prix_achat"],
                   row["date_ajout"], row["id"], row["statut"], row["date_sortie"], conn)

    def est_en_stock(self):
        return self.statut == "en_stock"

    def sauvegarder(self):
        """Pas de commit ici : l'appelant gère la transaction (voir Cave.ajouter_bouteilles)."""
        cur = self.conn.execute(
            """INSERT INTO bouteille (vin_id, cave_id, etagere_id, prix_achat, date_ajout, statut)
               VALUES (?,?,?,?,?, 'en_stock')""",
            (self.vin_id, self.cave_id, self.etagere_id, self.prix_achat, self.date_ajout))
        self.id = cur.lastrowid

    def deplacer(self, etagere):
        if not self.est_en_stock():
            raise MaCaveError("Une bouteille archivée ne peut pas être déplacée.")
        if etagere.id == self.etagere_id:
            raise MaCaveError("La bouteille est déjà sur cette étagère.")
        if not etagere.peut_accueillir(1):                  # R7
            raise MaCaveError("L'étagère « " + etagere.nom + " » est pleine.")
        with self.conn:
            self.conn.execute("UPDATE bouteille SET etagere_id=? WHERE id=?", (etagere.id, self.id))
        self.etagere_id = etagere.id

    def archiver(self, note, commentaire=None):
        """Dégustation : la bouteille quitte l'étagère et une évaluation est créée (atomique)."""
        if not self.est_en_stock():                         # R8
            raise MaCaveError("Cette bouteille est déjà archivée.")
        auteur_id = self.conn.execute("SELECT utilisateur_id FROM cave WHERE id=?",
                                      (self.cave_id,)).fetchone()[0]
        evaluation = Evaluation(self.id, auteur_id, note, commentaire, conn=self.conn)
        sortie = date.today().isoformat()
        with self.conn:
            self.conn.execute(
                "UPDATE bouteille SET statut='archivee', etagere_id=NULL, date_sortie=? WHERE id=?",
                (sortie, self.id))
            evaluation.sauvegarder()
        self.statut = "archivee"
        self.etagere_id = None
        self.date_sortie = sortie

    def retirer(self):
        """Retrait définitif : l'exemplaire est supprimé, le vin reste dans le catalogue."""
        if not self.est_en_stock():                         # R8
            raise MaCaveError("Une bouteille archivée ne peut pas être retirée.")
        with self.conn:
            self.conn.execute("DELETE FROM bouteille WHERE id=?", (self.id,))


# ---------------------------------------------------------------------
# Cave : passage obligé pour accéder aux données d'un utilisateur (R1)
# ---------------------------------------------------------------------
class Cave:
    COLONNES_STOCK = dict(Vin.COLONNES_TRI, prix_achat="b.prix_achat")
    COLONNES_HISTORIQUE = dict(Vin.COLONNES_TRI, note_perso="ev.note", date_sortie="b.date_sortie")

    def __init__(self, utilisateur_id, id, conn):
        self.utilisateur_id = utilisateur_id
        self.id = id
        self.conn = conn

    # --- accès contrôlés -----------------------------------------------
    def obtenir_etagere(self, etagere_id):
        row = self.conn.execute("SELECT * FROM etagere WHERE id=?", (lire_id(etagere_id),)).fetchone()
        if row is None:
            raise IntrouvableError("Étagère introuvable.")
        if row["cave_id"] != self.id:
            raise AccesInterditError("Cette étagère ne vous appartient pas.")
        return Etagere.depuis_ligne(row, self.conn)

    def obtenir_bouteille(self, bouteille_id):
        row = self.conn.execute("SELECT * FROM bouteille WHERE id=?", (lire_id(bouteille_id),)).fetchone()
        if row is None:
            raise IntrouvableError("Bouteille introuvable.")
        if row["cave_id"] != self.id:
            raise AccesInterditError("Cette bouteille ne vous appartient pas.")
        return Bouteille.depuis_ligne(row, self.conn)

    # --- étagères --------------------------------------------------------
    def etageres(self):
        rows = self.conn.execute("SELECT * FROM etagere WHERE cave_id=? ORDER BY nom COLLATE NOCASE",
                                 (self.id,)).fetchall()
        return [Etagere.depuis_ligne(r, self.conn) for r in rows]

    def creer_etagere(self, nom, capacite):
        e = Etagere(nom, capacite, self.id, conn=self.conn)
        e.sauvegarder()
        return e

    def supprimer_etagere(self, etagere_id):
        self.obtenir_etagere(etagere_id).supprimer()

    # --- bouteilles --------------------------------------------------------
    def ajouter_bouteilles(self, vin_id, etagere_id, quantite, prix_achat):
        """Ajoute plusieurs exemplaires identiques : tout ou rien."""
        quantite = entier_positif(quantite, "La quantité")
        prix = lire_prix(prix_achat)
        etagere = self.obtenir_etagere(etagere_id)
        vin_id = lire_id(vin_id)
        if Vin.obtenir_par_id(vin_id, self.conn) is None:
            raise IntrouvableError("Ce vin n'existe pas dans le catalogue.")
        if not etagere.peut_accueillir(quantite):           # R3
            raise MaCaveError("L'étagère « " + etagere.nom + " » n'a que " +
                              str(etagere.places_libres()) + " place(s) libre(s) pour " +
                              str(quantite) + " bouteille(s) demandée(s). Rien n'a été ajouté.")
        creees = []
        with self.conn:                                     # une seule transaction
            for i in range(quantite):
                b = Bouteille(vin_id, self.id, etagere.id, prix, conn=self.conn)
                b.sauvegarder()
                creees.append(b)
        return creees

    def deplacer_bouteille(self, bouteille_id, etagere_id):
        self.obtenir_bouteille(bouteille_id).deplacer(self.obtenir_etagere(etagere_id))

    def archiver_bouteille(self, bouteille_id, note, commentaire=None):
        self.obtenir_bouteille(bouteille_id).archiver(note, commentaire)

    def retirer_bouteille(self, bouteille_id):
        self.obtenir_bouteille(bouteille_id).retirer()

    # --- consultation ----------------------------------------------------------
    def bouteilles_en_stock(self, recherche=None, type_vin=None, etagere_id=None,
                            tri="domaine", ordre="asc"):
        """Une ligne par exemplaire : le tri par prix porte donc sur chaque bouteille."""
        filtre, params = filtre_recherche(recherche, type_vin)
        sql = """SELECT b.id AS bouteille_id, b.prix_achat, b.date_ajout, b.etagere_id,
                        e.nom AS etagere_nom, v.id AS vin_id, v.domaine, v.nom, v.type,
                        v.millesime, v.region, """ + NOTE_MOYENNE + """ AS note_moyenne
                 FROM bouteille b JOIN vin v ON v.id = b.vin_id JOIN etagere e ON e.id = b.etagere_id
                 WHERE b.cave_id=? AND b.statut='en_stock'""" + filtre
        params = [self.id] + params
        if etagere_id:
            sql += " AND b.etagere_id=?"
            params.append(lire_id(etagere_id))
        sql += clause_tri(tri, ordre, self.COLONNES_STOCK, "domaine") + ", b.id"
        return self.conn.execute(sql, params).fetchall()

    def historique(self, recherche=None, type_vin=None, tri="date_sortie", ordre="desc"):
        """Bouteilles archivées avec ma note. Tri : les valeurs absentes sont en dernier."""
        filtre, params = filtre_recherche(recherche, type_vin)
        sql = """SELECT b.id AS bouteille_id, b.prix_achat, b.date_sortie,
                        v.id AS vin_id, v.domaine, v.nom, v.type, v.millesime, v.region,
                        """ + NOTE_MOYENNE + """ AS note_moyenne,
                        ev.id AS evaluation_id, ev.note AS note_perso, ev.commentaire
                 FROM bouteille b JOIN vin v ON v.id = b.vin_id
                 JOIN evaluation ev ON ev.bouteille_id = b.id
                 WHERE b.cave_id=? AND b.statut='archivee'""" + filtre
        sql += clause_tri(tri, ordre, self.COLONNES_HISTORIQUE, "date_sortie") + ", b.id"
        return self.conn.execute(sql, [self.id] + params).fetchall()

    # --- tableau de bord --------------------------------------------------------
    def tableau_de_bord(self):
        c = self.conn
        nb_bouteilles = c.execute("SELECT COUNT(*) FROM bouteille WHERE cave_id=? AND statut='en_stock'",
                                  (self.id,)).fetchone()[0]
        nb_references = c.execute(
            "SELECT COUNT(DISTINCT vin_id) FROM bouteille WHERE cave_id=? AND statut='en_stock'",
            (self.id,)).fetchone()[0]
        capacite = c.execute("SELECT COALESCE(SUM(capacite_max),0) FROM etagere WHERE cave_id=?",
                             (self.id,)).fetchone()[0]
        valeur = c.execute(
            "SELECT COALESCE(SUM(prix_achat),0) FROM bouteille WHERE cave_id=? AND statut='en_stock'",
            (self.id,)).fetchone()[0]
        if capacite == 0:                                   # pas de division par zéro
            occupation = "Aucune étagère"
        else:
            occupation = "%.0f %%" % (nb_bouteilles * 100 / capacite)
        return {"nb_bouteilles": nb_bouteilles, "nb_references": nb_references,
                "nb_etageres": len(self.etageres()), "occupation": occupation,
                "valeur_stock": valeur}


# ---------------------------------------------------------------------
# Jeu de démonstration
# ---------------------------------------------------------------------
def jeu_de_demonstration(conn):
    if Utilisateur.authentifier("alice", "alice123", conn):
        return                                              # déjà chargé
    alice = Utilisateur("alice", "alice@example.fr", conn=conn)
    alice.sauvegarder("alice123")
    bob = Utilisateur("bob", "bob@example.fr", conn=conn)
    bob.sauvegarder("bob123")
    ca, cb = alice.cave(), bob.cave()

    salon = ca.creer_etagere("Salon", 10)
    voute = ca.creer_etagere("Cave voûtée", 20)
    cellier = cb.creer_etagere("Cellier", 12)

    montelena = Vin("Château Montelena", "Cabernet Sauvignon", "rouge", 1967, "Californie",
                    "Cabernet californien mythique.", conn=conn).sauvegarder()
    weinbach = Vin("Domaine Weinbach", "Riesling Schlossberg", "blanc", 2019, "Alsace",
                   "Riesling sec et minéral.", conn=conn).sauvegarder()
    champagne = Vin("Billecart-Salmon", "Brut Réserve", "effervescent", 2015, "Champagne",
                    "Champagne fin et vif.", conn=conn).sauvegarder()

    montelena_a = ca.ajouter_bouteilles(montelena, salon.id, 5, 80)
    ca.ajouter_bouteilles(weinbach, voute.id, 3, 35)
    ca.ajouter_bouteilles(champagne, voute.id, 2, 55)
    montelena_b = cb.ajouter_bouteilles(montelena, cellier.id, 2, 90)
    cb.ajouter_bouteilles(weinbach, cellier.id, 3, 32)

    ca.archiver_bouteille(montelena_a[0].id, 16, "Puissant, tanins soyeux.")
    ca.archiver_bouteille(montelena_a[1].id, 12, "Un peu fatigué.")
    cb.archiver_bouteille(montelena_b[0].id, 17, "Magnifique.")     # moyenne : 15/20
