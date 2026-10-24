#!/usr/bin/env python3
"""Vérifie la cohérence du site avant déploiement.

Le site n'a ni build ni framework : ces contrôles remplacent ce qu'un
compilateur attraperait. Ils tournent en CI sur chaque pull request et
avant chaque déploiement (voir .github/workflows/check.yml).

Deux niveaux :
  - ERREUR       : casse le déploiement, le site serait incohérent.
  - AVERTISSEMENT : à corriger, mais ne bloque pas (SEO perfectible…).

Usage :
    python3 tools/check_site.py            # avertissements tolérés
    python3 tools/check_site.py --strict   # avertissements bloquants

Aucune dépendance : bibliothèque standard uniquement.
"""
from __future__ import annotations

import base64
import hashlib
import posixpath
import sys
import xml.etree.ElementTree as ET
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

RACINE = Path(__file__).resolve().parent.parent
SITE = RACINE / "site"
DOMAINE = "https://noameunier.fr"
PAGES_ERREUR = {"error403.html", "error404.html"}

# Le seul script inline du site (la classe `js` posée avant le rendu) est
# autorisé par son empreinte dans la CSP. Toute modification du script
# doit donc mettre à jour cette constante ET l'en-tête CloudFront.
HASH_SCRIPT = "sha256-/x7W7R75k8Roq0WaVRQX9blP4OufE5xbAdzklGxsgpw="

erreurs: list[str] = []
avertissements: list[str] = []


def erreur(fichier: Path | str, message: str) -> None:
    erreurs.append(f"{nom(fichier)} : {message}")


def avertir(fichier: Path | str, message: str) -> None:
    avertissements.append(f"{nom(fichier)} : {message}")


def nom(fichier: Path | str) -> str:
    """Chemin lisible dans les logs : relatif à la racine du dépôt."""
    if isinstance(fichier, Path):
        try:
            return fichier.relative_to(RACINE).as_posix()
        except ValueError:
            return str(fichier)
    return fichier


class Page(HTMLParser):
    """Collecte les éléments utiles d'une page, avec leur ligne."""

    def __init__(self, chemin: Path) -> None:
        super().__init__(convert_charrefs=True)
        self.chemin = chemin
        self.elements: list[tuple[str, dict[str, str], int]] = []
        self.ids: dict[str, int] = {}
        self.dans_titre = False
        self.titre = ""
        self.dans_script = False
        self.script_courant = ""
        self.ligne_script = 0
        self.scripts_inline: list[tuple[str, int]] = []

    def handle_starttag(self, tag, attrs):
        attributs = {cle: (valeur or "") for cle, valeur in attrs}
        ligne = self.getpos()[0]
        self.elements.append((tag, attributs, ligne))
        if "id" in attributs:
            identifiant = attributs["id"]
            if identifiant in self.ids:
                erreur(
                    self.chemin,
                    f"ligne {ligne} : id « {identifiant} » déjà utilisé "
                    f"ligne {self.ids[identifiant]}",
                )
            else:
                self.ids[identifiant] = ligne
        if tag == "title":
            self.dans_titre = True
        if tag == "script" and "src" not in attributs:
            self.dans_script = True
            self.script_courant = ""
            self.ligne_script = ligne

    def handle_endtag(self, tag):
        if tag == "title":
            self.dans_titre = False
        if tag == "script" and self.dans_script:
            self.scripts_inline.append((self.script_courant, self.ligne_script))
            self.dans_script = False

    def handle_data(self, data):
        if self.dans_titre:
            self.titre += data
        if self.dans_script:
            self.script_courant += data

    # ── Accesseurs ────────────────────────────────────────────────────
    def de_type(self, tag: str):
        return [(a, l) for t, a, l in self.elements if t == tag]

    def metas(self) -> dict[str, str]:
        trouve: dict[str, str] = {}
        for attributs, _ in self.de_type("meta"):
            cle = attributs.get("name") or attributs.get("property")
            if cle and "content" in attributs:
                trouve[cle] = attributs["content"]
        return trouve

    def liens(self):
        return self.de_type("link")

    def balises(self) -> set[str]:
        return {t for t, _, _ in self.elements}


def relatif(page: Path) -> str:
    """Chemin de la page depuis site/, en URL (« / » pour l'accueil)."""
    chemin = page.relative_to(SITE).as_posix()
    return "/" if chemin == "index.html" else f"/{chemin}"


def resoudre(url: str, source: Path) -> Path | None:
    """Traduit une URL interne en fichier local, ou None si externe.

    ``source`` est la page ou la feuille de style qui contient l'URL :
    elle sert de base aux chemins relatifs.
    """
    morceau = urlparse(url)
    if morceau.scheme or morceau.netloc:
        if morceau.netloc not in ("noameunier.fr", "www.noameunier.fr"):
            return None
        chemin = morceau.path or "/"
    else:
        chemin = morceau.path
        if not chemin:
            return None
        if not chemin.startswith("/"):
            base = source.relative_to(SITE).parent.as_posix()
            chemin = "/" + (f"{base}/{chemin}" if base != "." else chemin)

    if chemin.endswith("/"):
        chemin += "index.html"
    chemin = posixpath.normpath(chemin).lstrip("/")
    if chemin in ("", "."):
        chemin = "index.html"
    if chemin == ".." or chemin.startswith("../"):
        return None
    return SITE / chemin


def controler_head(page: Page, chemin_url: str) -> None:
    chemin = page.chemin
    metas = page.metas()
    balises = page.balises()

    if "html" not in balises:
        erreur(chemin, "balise <html> absente")
    else:
        attributs_html = page.de_type("html")[0][0]
        if attributs_html.get("lang") != "fr":
            erreur(chemin, "attribut lang=\"fr\" attendu sur <html>")
    if not any(a.get("charset") for a, _ in page.de_type("meta")):
        erreur(chemin, "meta charset absent")
    if "viewport" not in metas:
        erreur(chemin, "meta viewport absent")

    est_erreur = chemin.name in PAGES_ERREUR
    titre = " ".join(page.titre.split())
    if not titre:
        erreur(chemin, "titre de page absent")
    elif not 15 <= len(titre) <= 65:
        avertir(chemin, f"titre de {len(titre)} signes (viser 15-65) : « {titre} »")

    if est_erreur:
        if metas.get("robots") != "noindex":
            erreur(chemin, "une page d'erreur doit porter robots=noindex")
        return

    description = metas.get("description", "")
    if not description:
        erreur(chemin, "meta description absente")
    elif not 50 <= len(description) <= 170:
        avertir(
            chemin,
            f"description de {len(description)} signes (viser 50-170)",
        )

    canonique = [a.get("href") for a, _ in page.liens() if a.get("rel") == "canonical"]
    attendu = DOMAINE + chemin_url
    if not canonique:
        erreur(chemin, "lien canonical absent")
    elif len(canonique) > 1:
        erreur(chemin, "plusieurs liens canonical")
    elif canonique[0] != attendu:
        erreur(chemin, f"canonical « {canonique[0]} » au lieu de « {attendu} »")

    for obligatoire in ("og:title", "og:description", "og:url", "og:image"):
        if not metas.get(obligatoire):
            erreur(chemin, f"métadonnée {obligatoire} absente")
    if metas.get("og:url") and metas["og:url"] != attendu:
        erreur(chemin, f"og:url « {metas['og:url']} » au lieu de « {attendu} »")
    if not metas.get("og:image:alt"):
        avertir(chemin, "og:image:alt absent")

    # Blocs partagés par toutes les pages : leur oubli est invisible en
    # local mais casse la police ou le partage social en production.
    if not any(a.get("rel") == "preload" and a.get("as") == "font"
               for a, _ in page.liens()):
        erreur(chemin, "preload de la police absent")
    if not any(a.get("rel") == "stylesheet" for a, _ in page.liens()):
        erreur(chemin, "feuille de style absente")
    if "theme-color" not in metas:
        avertir(chemin, "meta theme-color absent")


def controler_contenu(page: Page, pages: dict[str, Page]) -> None:
    chemin = page.chemin

    h1 = page.de_type("h1")
    if len(h1) != 1:
        erreur(chemin, f"{len(h1)} balise(s) <h1>, une seule attendue")

    # Liens, scripts, feuilles de style, images : tout ce qui est interne
    # doit exister sur le disque, avec la bonne casse.
    for attribut, balise in (("href", "a"), ("href", "link"), ("src", "script"),
                             ("src", "img")):
        for attributs, ligne in page.de_type(balise):
            url = attributs.get(attribut, "")
            if not url or url.startswith(("mailto:", "tel:", "data:")):
                continue
            if url.startswith("#"):
                continue
            cible = resoudre(url, chemin)
            if cible is not None and not cible.is_file():
                erreur(chemin, f"ligne {ligne} : {url} introuvable ({cible})")

    # Une ancre (« /#projets ») doit désigner un id réel sur la page visée.
    for attributs, ligne in page.de_type("a"):
        url = attributs.get("href", "")
        if "#" not in url:
            continue
        base, fragment = url.split("#", 1)
        if not fragment:
            continue
        if base:
            cible = resoudre(base, chemin)
            page_visee = pages.get(relatif(cible)) if cible else None
        else:
            page_visee = page
        if page_visee is not None and fragment not in page_visee.ids:
            erreur(
                chemin,
                f"ligne {ligne} : ancre « #{fragment} » absente de "
                f"{relatif(page_visee.chemin)}",
            )

    for _balise, attributs, ligne in page.elements:
        for attribut in ("aria-labelledby", "aria-controls", "aria-describedby"):
            for reference in attributs.get(attribut, "").split():
                if reference not in page.ids:
                    erreur(
                        chemin,
                        f"ligne {ligne} : {attribut} pointe vers « {reference} » absent",
                    )

    # CSP stricte : aucun style inline ni gestionnaire d'événement
    # inline. Le seul script inline est autorisé par son empreinte, qui
    # doit rester identique à celle publiée dans l'en-tête CloudFront.
    for balise, attributs, ligne in page.elements:
        if balise == "style":
            erreur(chemin, f"ligne {ligne} : bloc <style> interdit (CSP)")
        if "style" in attributs:
            erreur(chemin, f"ligne {ligne} : attribut style= interdit (CSP)")
        for nom in attributs:
            if nom.startswith("on"):
                erreur(chemin, f"ligne {ligne} : gestionnaire {nom}= interdit (CSP)")

    for contenu, ligne in page.scripts_inline:
        empreinte = base64.b64encode(
            hashlib.sha256(contenu.encode("utf-8")).digest()
        ).decode()
        if f"sha256-{empreinte}" != HASH_SCRIPT:
            erreur(
                chemin,
                f"ligne {ligne} : script inline non autorisé par la CSP "
                f"(hash sha256-{empreinte})",
            )

    for attributs, ligne in page.de_type("img"):
        if "alt" not in attributs:
            erreur(chemin, f"ligne {ligne} : image sans attribut alt")
        for dimension in ("width", "height"):
            if dimension not in attributs:
                erreur(chemin, f"ligne {ligne} : image sans {dimension} (CLS)")
        srcset = attributs.get("srcset", "")
        for candidat in srcset.split(","):
            url = candidat.strip().split(" ")[0]
            if not url:
                continue
            cible = resoudre(url, chemin)
            if cible is not None and not cible.is_file():
                erreur(chemin, f"ligne {ligne} : {url} (srcset) introuvable")

    for attributs, ligne in page.de_type("a"):
        if attributs.get("target") == "_blank":
            rel = attributs.get("rel", "")
            if "noopener" not in rel.split():
                erreur(chemin, f"ligne {ligne} : target=_blank sans rel=noopener")


def controler_css() -> None:
    """Toute ressource citée par le CSS doit exister."""
    for feuille in sorted(SITE.rglob("*.css")):
        contenu = feuille.read_text(encoding="utf-8")
        index = 0
        while True:
            debut = contenu.find("url(", index)
            if debut == -1:
                break
            fin = contenu.find(")", debut)
            if fin == -1:
                erreur(feuille, "appel url( non fermé")
                break
            index = fin + 1
            url = contenu[debut + 4:fin].strip().strip("\"'")
            if url.startswith(("data:", "http:", "https:", "#")):
                continue
            cible = resoudre(url, feuille)
            if cible is not None and not cible.is_file():
                erreur(feuille, f"ressource {url} introuvable")


def controler_sitemap(pages: dict[str, Page]) -> None:
    chemin = SITE / "sitemap.xml"
    if not chemin.is_file():
        erreur("site", "sitemap.xml absent")
        return
    try:
        arbre = ET.parse(chemin)
    except ET.ParseError as exc:
        erreur(chemin, f"XML invalide : {exc}")
        return

    espace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    declares: set[str] = set()
    for url in arbre.getroot().findall(f"{espace}url"):
        loc = (url.findtext(f"{espace}loc") or "").strip()
        if not loc.startswith(DOMAINE):
            erreur(chemin, f"URL hors domaine : {loc}")
            continue
        chemin_url = loc[len(DOMAINE):] or "/"
        declares.add(chemin_url)
        page = pages.get(chemin_url)
        if page is None:
            erreur(chemin, f"{loc} ne correspond à aucune page")
            continue
        if page.metas().get("robots") == "noindex":
            erreur(chemin, f"{loc} est en noindex mais déclarée au sitemap")
        derniere = url.findtext(f"{espace}lastmod")
        if derniere:
            try:
                if date.fromisoformat(derniere.strip()) > date.today():
                    avertir(chemin, f"lastmod dans le futur pour {loc}")
            except ValueError:
                erreur(chemin, f"lastmod invalide pour {loc} : {derniere}")

    for chemin_url, page in pages.items():
        if page.chemin.name in PAGES_ERREUR:
            continue
        if chemin_url not in declares:
            erreur(chemin, f"{chemin_url} est indexable mais absente du sitemap")


def controler_robots() -> None:
    chemin = SITE / "robots.txt"
    if not chemin.is_file():
        erreur("site", "robots.txt absent")
        return
    contenu = chemin.read_text(encoding="utf-8")
    if f"Sitemap: {DOMAINE}/sitemap.xml" not in contenu:
        erreur(chemin, f"ligne « Sitemap: {DOMAINE}/sitemap.xml » absente")
    if "Disallow: /" in contenu:
        erreur(chemin, "le site est entièrement interdit aux robots")


def controler_artefacts_parasites() -> None:
    for parasite in (".DS_Store", "Thumbs.db", "desktop.ini"):
        for fichier in SITE.rglob(parasite):
            erreur(fichier, "fichier de système à ne pas publier")


def principal() -> int:
    strict = "--strict" in sys.argv[1:]
    if not SITE.is_dir():
        print(f"ERREUR : dossier {SITE} introuvable", file=sys.stderr)
        return 2

    pages: dict[str, Page] = {}
    for fichier in sorted(SITE.rglob("*.html")):
        page = Page(fichier)
        page.feed(fichier.read_text(encoding="utf-8"))
        page.close()
        pages[relatif(fichier)] = page

    for chemin_url, page in pages.items():
        controler_head(page, chemin_url)
        controler_contenu(page, pages)

    controler_css()
    controler_sitemap(pages)
    controler_robots()
    controler_artefacts_parasites()

    for message in sorted(set(avertissements)):
        print(f"AVERTISSEMENT · {message}")
    for message in erreurs:
        print(f"ERREUR · {message}")

    print(
        f"\n{len(pages)} pages contrôlées · "
        f"{len(erreurs)} erreur(s) · {len(set(avertissements))} avertissement(s)"
    )
    if erreurs or (strict and avertissements):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(principal())
