"""MaCave - application Flask. Lancer : python app.py"""
import os
import uuid
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash, g

from macave_SGBD_SQLite import (DB, Utilisateur, Vin, Evaluation, TYPES_VIN, MaCaveError,
                                AccesInterditError, IntrouvableError, jeu_de_demonstration)

BASE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)
# La clé secrète vient d'une variable d'environnement (jamais écrite dans le code)
app.config["SECRET_KEY"] = os.environ.get("MACAVE_SECRET_KEY") or os.urandom(24).hex()
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024

DOSSIER_PHOTOS = os.path.join(BASE, "static", "uploads")
os.makedirs(DOSSIER_PHOTOS, exist_ok=True)
EXTENSIONS_PHOTO = ["png", "jpg", "jpeg", "webp"]

db = DB(os.path.join(BASE, "macave.db"))
conn = db.conn

# disponibles dans tous les templates
app.jinja_env.globals["types_vin"] = TYPES_VIN
app.jinja_env.globals["note_texte"] = Vin.formater_note


# ---------------------------------------------------------------------
# Outils
# ---------------------------------------------------------------------
@app.before_request
def charger_utilisateur():
    g.user = None
    g.cave = None
    if "uid" in session:
        g.user = Utilisateur.obtenir_par_id(session["uid"], conn)
        if g.user is None:
            session.clear()
        else:
            g.cave = g.user.cave()


def connexion_requise(f):
    @wraps(f)
    def verifier(*args, **kwargs):
        if g.user is None:
            flash("Veuillez vous connecter.", "info")
            return redirect(url_for("connexion"))
        return f(*args, **kwargs)
    return verifier


def enregistrer_photo(fichier):
    if not fichier or not fichier.filename:
        return None
    ext = fichier.filename.rsplit(".", 1)[-1].lower()
    if ext not in EXTENSIONS_PHOTO:
        raise MaCaveError("Photo : formats acceptés png, jpg, jpeg ou webp.")
    nom = uuid.uuid4().hex + "." + ext
    fichier.save(os.path.join(DOSSIER_PHOTOS, nom))
    return nom


def vin_ou_404(vin_id):
    vin = Vin.obtenir_par_id(vin_id, conn)
    if vin is None:
        raise IntrouvableError("Ce vin n'existe pas dans le catalogue.")
    return vin


# ---------------------------------------------------------------------
# Erreurs
# ---------------------------------------------------------------------
@app.errorhandler(AccesInterditError)
def erreur_403(e):
    return render_template("erreur.html", code=403, message=str(e)), 403


@app.errorhandler(IntrouvableError)
def erreur_introuvable(e):
    return render_template("erreur.html", code=404, message=str(e)), 404


@app.errorhandler(404)
def erreur_404(e):
    return render_template("erreur.html", code=404, message="Cette page n'existe pas."), 404


@app.errorhandler(413)
def erreur_413(e):
    return render_template("erreur.html", code=413, message="Fichier trop gros (4 Mo maximum)."), 413


# ---------------------------------------------------------------------
# Comptes
# ---------------------------------------------------------------------
@app.route("/inscription", methods=["GET", "POST"])
def inscription():
    if g.user:
        return redirect(url_for("index"))
    if request.method == "POST":
        f = request.form
        try:
            if f["mot_de_passe"] != f["confirmation"]:
                raise MaCaveError("Les deux mots de passe ne correspondent pas.")
            u = Utilisateur(f["identifiant"], f["email"], conn=conn)
            u.sauvegarder(f["mot_de_passe"])
            session.clear()
            session["uid"] = u.id
            flash("Compte créé. Commencez par créer une étagère.", "succès")
            return redirect(url_for("etageres"))
        except MaCaveError as e:
            flash(str(e), "erreur")
    return render_template("inscription.html")


@app.route("/connexion", methods=["GET", "POST"])
def connexion():
    if g.user:
        return redirect(url_for("index"))
    if request.method == "POST":
        u = Utilisateur.authentifier(request.form["identifiant"], request.form["mot_de_passe"], conn)
        if u:
            session.clear()
            session["uid"] = u.id
            return redirect(url_for("index"))
        flash("Identifiant ou mot de passe incorrect.", "erreur")
    return render_template("connexion.html")


@app.route("/deconnexion", methods=["POST"])
def deconnexion():
    session.clear()
    return redirect(url_for("connexion"))


@app.route("/profil", methods=["GET", "POST"])
@connexion_requise
def profil():
    if request.method == "POST":
        f = request.form
        try:
            if f["action"] == "email":
                g.user.modifier_email(f["email"])
                flash("Adresse électronique modifiée.", "succès")
            else:
                if not g.user.verifier_mot_de_passe(f["actuel"]):
                    raise MaCaveError("Le mot de passe actuel est incorrect.")
                if f["nouveau"] != f["confirmation"]:
                    raise MaCaveError("Les deux mots de passe ne correspondent pas.")
                g.user.changer_mot_de_passe(f["nouveau"])
                flash("Mot de passe modifié.", "succès")
            return redirect(url_for("profil"))
        except MaCaveError as e:
            flash(str(e), "erreur")
    return render_template("profil.html")


# ---------------------------------------------------------------------
# Accueil et étagères
# ---------------------------------------------------------------------
@app.route("/")
def index():
    if g.user is None:
        return redirect(url_for("connexion"))
    return render_template("index.html", bord=g.cave.tableau_de_bord(),
                           etageres=g.cave.etageres(), recents=g.cave.historique()[:5])


@app.route("/etageres")
@connexion_requise
def etageres():
    return render_template("etageres.html", etageres=g.cave.etageres())


@app.route("/etageres/ajouter", methods=["POST"])
@connexion_requise
def ajouter_etagere():
    try:
        e = g.cave.creer_etagere(request.form["nom"], request.form["capacite"])
        flash("Étagère « " + e.nom + " » créée.", "succès")
    except MaCaveError as e:
        flash(str(e), "erreur")
    return redirect(url_for("etageres"))


@app.route("/etageres/<int:etagere_id>")
@connexion_requise
def etagere(etagere_id):
    e = g.cave.obtenir_etagere(etagere_id)
    return render_template("etagere.html", e=e, contenu=e.bouteilles())


@app.route("/etageres/<int:etagere_id>/renommer", methods=["POST"])
@connexion_requise
def renommer_etagere(etagere_id):
    try:
        g.cave.obtenir_etagere(etagere_id).renommer(request.form["nom"])
        flash("Étagère renommée.", "succès")
    except AccesInterditError:
        raise
    except MaCaveError as e:
        flash(str(e), "erreur")
    return redirect(url_for("etagere", etagere_id=etagere_id))


@app.route("/etageres/<int:etagere_id>/capacite", methods=["POST"])
@connexion_requise
def capacite_etagere(etagere_id):
    try:
        g.cave.obtenir_etagere(etagere_id).modifier_capacite(request.form["capacite"])
        flash("Capacité modifiée.", "succès")
    except AccesInterditError:
        raise
    except MaCaveError as e:
        flash(str(e), "erreur")
    return redirect(url_for("etagere", etagere_id=etagere_id))


@app.route("/etageres/<int:etagere_id>/supprimer", methods=["POST"])
@connexion_requise
def supprimer_etagere(etagere_id):
    try:
        g.cave.supprimer_etagere(etagere_id)
        flash("Étagère supprimée.", "succès")
        return redirect(url_for("etageres"))
    except AccesInterditError:
        raise
    except MaCaveError as e:
        flash(str(e), "erreur")
        return redirect(url_for("etagere", etagere_id=etagere_id))


# ---------------------------------------------------------------------
# Stock et historique
# ---------------------------------------------------------------------
@app.route("/stock")
@connexion_requise
def stock():
    a = request.args
    lignes = g.cave.bouteilles_en_stock(a.get("q"), a.get("type"), a.get("etagere"),
                                        a.get("tri", "domaine"), a.get("ordre", "asc"))
    return render_template("stock.html", lignes=lignes, etageres=g.cave.etageres())


@app.route("/bouteilles/<int:bouteille_id>/deplacer", methods=["POST"])
@connexion_requise
def deplacer(bouteille_id):
    try:
        g.cave.deplacer_bouteille(bouteille_id, request.form["etagere"])
        flash("Bouteille déplacée.", "succès")
    except AccesInterditError:
        raise
    except MaCaveError as e:
        flash(str(e), "erreur")
    return redirect(url_for("stock"))


@app.route("/bouteilles/<int:bouteille_id>/archiver", methods=["GET", "POST"])
@connexion_requise
def archiver(bouteille_id):
    b = g.cave.obtenir_bouteille(bouteille_id)
    if not b.est_en_stock():
        flash("Cette bouteille est déjà archivée.", "erreur")
        return redirect(url_for("historique"))
    if request.method == "POST":
        try:
            g.cave.archiver_bouteille(bouteille_id, request.form["note"], request.form.get("commentaire"))
            flash("Dégustation enregistrée.", "succès")
            return redirect(url_for("historique"))
        except MaCaveError as e:
            flash(str(e), "erreur")
    return render_template("archiver.html", b=b, vin=vin_ou_404(b.vin_id))


@app.route("/bouteilles/<int:bouteille_id>/retirer", methods=["POST"])
@connexion_requise
def retirer(bouteille_id):
    try:
        g.cave.retirer_bouteille(bouteille_id)
        flash("Bouteille retirée de la cave.", "succès")
    except AccesInterditError:
        raise
    except MaCaveError as e:
        flash(str(e), "erreur")
    return redirect(url_for("stock"))


@app.route("/historique")
@connexion_requise
def historique():
    a = request.args
    lignes = g.cave.historique(a.get("q"), a.get("type"), a.get("tri", "date_sortie"), a.get("ordre", "desc"))
    return render_template("historique.html", lignes=lignes)


# ---------------------------------------------------------------------
# Catalogue des vins (partagé)
# ---------------------------------------------------------------------
@app.route("/vins")
@connexion_requise
def vins():
    a = request.args
    lignes = Vin.catalogue(conn, a.get("q"), a.get("type"), a.get("tri", "domaine"), a.get("ordre", "asc"))
    return render_template("vins.html", lignes=lignes)


@app.route("/vins/nouveau", methods=["GET", "POST"])
@connexion_requise
def nouveau_vin():
    if request.method == "POST":
        f = request.form
        try:
            v = Vin(f["domaine"], f["nom"], f["type"], f["millesime"], f["region"],
                    f.get("description", ""), conn=conn)
            existant = v.id_existant()
            if existant:
                flash("Cette référence existe déjà dans le catalogue.", "info")
                return redirect(url_for("vin", vin_id=existant))
            v.photo = enregistrer_photo(request.files.get("photo"))
            v.sauvegarder()
            flash("Référence créée. Vous pouvez y ajouter des bouteilles.", "succès")
            return redirect(url_for("vin", vin_id=v.id))
        except MaCaveError as e:
            flash(str(e), "erreur")
    return render_template("nouveau_vin.html", f=request.form)


@app.route("/vins/<int:vin_id>")
@connexion_requise
def vin(vin_id):
    v = vin_ou_404(vin_id)
    mes_exemplaires = [l for l in g.cave.bouteilles_en_stock() if l["vin_id"] == v.id]
    return render_template("vin.html", v=v, moyenne=v.note_moyenne(), evaluations=v.evaluations(),
                           exemplaires=mes_exemplaires, etageres=g.cave.etageres())


@app.route("/vins/<int:vin_id>/ajouter-bouteilles", methods=["POST"])
@connexion_requise
def ajouter_bouteilles(vin_id):
    f = request.form
    try:
        creees = g.cave.ajouter_bouteilles(vin_id, f["etagere"], f["quantite"], f["prix"])
        flash(str(len(creees)) + " bouteille(s) ajoutée(s).", "succès")
    except AccesInterditError:
        raise
    except MaCaveError as e:
        flash(str(e), "erreur")
    return redirect(url_for("vin", vin_id=vin_id))


@app.route("/evaluations/<int:evaluation_id>/modifier", methods=["GET", "POST"])
@connexion_requise
def modifier_evaluation(evaluation_id):
    ev = Evaluation.obtenir_par_id(evaluation_id, conn)
    if ev is None:
        raise IntrouvableError("Évaluation introuvable.")
    if ev.auteur_id != g.user.id:
        raise AccesInterditError("Vous ne pouvez modifier que vos propres évaluations.")
    if request.method == "POST":
        try:
            ev.modifier(request.form["note"], request.form.get("commentaire"), g.user.id)
            flash("Évaluation modifiée.", "succès")
            return redirect(url_for("vin", vin_id=ev.vin_id()))
        except MaCaveError as e:
            flash(str(e), "erreur")
    return render_template("evaluation.html", ev=ev, v=vin_ou_404(ev.vin_id()))


if __name__ == "__main__":
    jeu_de_demonstration(conn)    # alice / alice123 et bob / bob123
    app.run(debug=True)
