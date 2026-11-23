"""Tests des règles métier. Lancer : python -m unittest -v"""
import os
import tempfile
import unittest

from macave_SGBD_SQLite import (DB, Utilisateur, Vin, MaCaveError, AccesInterditError,
                                Evaluation, jeu_de_demonstration)


class TestMaCave(unittest.TestCase):
    def setUp(self):
        self.conn = DB(":memory:").conn
        self.alice = Utilisateur("alice", "alice@test.fr", conn=self.conn)
        self.alice.sauvegarder("secret123")
        self.bob = Utilisateur("bob", "bob@test.fr", conn=self.conn)
        self.bob.sauvegarder("secret123")
        self.cave = self.alice.cave()
        self.vin_id = Vin("Domaine X", "Cuvée Y", "rouge", 2015, "Bordeaux", conn=self.conn).sauvegarder()

    def test_ajout_5_bouteilles_une_seule_reference(self):
        e = self.cave.creer_etagere("Salon", 10)
        self.cave.ajouter_bouteilles(self.vin_id, e.id, 5, 20)
        self.assertEqual(e.occupation(), 5)
        self.assertEqual(self.cave.tableau_de_bord()["nb_references"], 1)

    def test_depassement_de_capacite_sans_ajout_partiel(self):
        e = self.cave.creer_etagere("Salon", 10)
        self.cave.ajouter_bouteilles(self.vin_id, e.id, 5, 20)
        with self.assertRaises(MaCaveError):
            self.cave.ajouter_bouteilles(self.vin_id, e.id, 6, 20)
        self.assertEqual(e.occupation(), 5)

    def test_retrait_d_un_exemplaire(self):
        e = self.cave.creer_etagere("Salon", 10)
        bouteilles = self.cave.ajouter_bouteilles(self.vin_id, e.id, 5, 20)
        self.cave.retirer_bouteille(bouteilles[0].id)
        self.assertEqual(e.occupation(), 4)
        self.assertIsNotNone(Vin.obtenir_par_id(self.vin_id, self.conn))   # le vin reste

    def test_deplacement(self):
        a = self.cave.creer_etagere("A", 5)
        b = self.cave.creer_etagere("B", 1)
        bouteilles = self.cave.ajouter_bouteilles(self.vin_id, a.id, 2, 20)
        self.cave.deplacer_bouteille(bouteilles[0].id, b.id)
        self.assertEqual((a.occupation(), b.occupation()), (1, 1))
        with self.assertRaises(MaCaveError):                 # B est pleine
            self.cave.deplacer_bouteille(bouteilles[1].id, b.id)

    def test_archivage(self):
        e = self.cave.creer_etagere("Salon", 10)
        bouteilles = self.cave.ajouter_bouteilles(self.vin_id, e.id, 5, 20)
        self.cave.archiver_bouteille(bouteilles[0].id, 15, "bon")
        self.assertEqual(e.occupation(), 4)
        self.assertEqual(len(self.cave.historique()), 1)
        with self.assertRaises(MaCaveError):                 # déjà archivée
            self.cave.archiver_bouteille(bouteilles[0].id, 10)
        with self.assertRaises(MaCaveError):
            self.cave.retirer_bouteille(bouteilles[0].id)

    def test_moyenne_communautaire(self):
        vin = Vin.obtenir_par_id(self.vin_id, self.conn)
        self.assertIsNone(vin.note_moyenne())
        self.assertEqual(Vin.formater_note(None), "Non évalué")
        e = self.cave.creer_etagere("Salon", 10)
        bouteilles = self.cave.ajouter_bouteilles(self.vin_id, e.id, 3, 20)
        for b, note in zip(bouteilles, [16, 12, 17]):
            self.cave.archiver_bouteille(b.id, note)
        self.assertEqual(vin.note_moyenne(), 15)

    def test_modification_note_change_la_moyenne(self):
        e = self.cave.creer_etagere("Salon", 10)
        b = self.cave.ajouter_bouteilles(self.vin_id, e.id, 1, 20)[0]
        self.cave.archiver_bouteille(b.id, 10)
        ev = Evaluation.obtenir_par_id(self.cave.historique()[0]["evaluation_id"], self.conn)
        ev.modifier(18, "mieux", self.alice.id)
        self.assertEqual(Vin.obtenir_par_id(self.vin_id, self.conn).note_moyenne(), 18)
        with self.assertRaises(AccesInterditError):          # R12
            ev.modifier(1, "", self.bob.id)

    def test_controle_d_acces(self):
        e = self.cave.creer_etagere("Salon", 10)
        b = self.cave.ajouter_bouteilles(self.vin_id, e.id, 1, 20)[0]
        cave_bob = self.bob.cave()
        with self.assertRaises(AccesInterditError):
            cave_bob.obtenir_etagere(e.id)
        with self.assertRaises(AccesInterditError):
            cave_bob.retirer_bouteille(b.id)

    def test_donnees_invalides(self):
        with self.assertRaises(MaCaveError):
            self.cave.creer_etagere("Zéro", 0)
        with self.assertRaises(MaCaveError):
            self.cave.creer_etagere("Texte", "abc")
        e = self.cave.creer_etagere("Salon", 10)
        with self.assertRaises(MaCaveError):                 # R2, casse ignorée
            self.cave.creer_etagere("salon", 5)
        b = self.cave.ajouter_bouteilles(self.vin_id, e.id, 1, 20)[0]
        with self.assertRaises(MaCaveError):                 # note hors 0..20
            self.cave.archiver_bouteille(b.id, 25)

    def test_etagere_capacite_et_suppression(self):
        e = self.cave.creer_etagere("Salon", 10)
        self.cave.ajouter_bouteilles(self.vin_id, e.id, 5, 20)
        with self.assertRaises(MaCaveError):                 # R4
            e.modifier_capacite(3)
        with self.assertRaises(MaCaveError):                 # R5
            e.supprimer()

    def test_pas_de_doublon_de_vin(self):
        doublon = Vin("  domaine   x ", "CUVÉE y", "Rouge", 2015, "bordeaux", conn=self.conn)
        self.assertEqual(doublon.sauvegarder(), self.vin_id)

    def test_tableau_de_bord_sans_etagere(self):
        self.assertEqual(self.cave.tableau_de_bord()["occupation"], "Aucune étagère")

    def test_persistance_apres_redemarrage(self):
        dossier = tempfile.mkdtemp()
        chemin = os.path.join(dossier, "test.db")
        conn = DB(chemin).conn
        jeu_de_demonstration(conn)
        conn.close()
        conn2 = DB(chemin).conn                              # "redémarrage"
        alice = Utilisateur.authentifier("alice", "alice123", conn2)
        self.assertIsNotNone(alice)
        self.assertEqual(alice.cave().tableau_de_bord()["nb_bouteilles"], 8)


if __name__ == "__main__":
    unittest.main()
