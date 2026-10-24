# Portfolio — noameunier.fr

Site statique du portfolio de Noa Meunier : **[noameunier.fr](https://noameunier.fr)**.
HTML, CSS et JavaScript natifs, sans framework ni étape de build. Hébergé sur AWS
(S3 privé + CloudFront) et déployé automatiquement depuis ce dépôt.

L'infrastructure complète — et sa procédure de recréation de zéro — est décrite
dans [`portfolio-aws-recap.md`](portfolio-aws-recap.md).

---

## Structure

```
site/                        ← contenu publié (racine du bucket S3)
├── index.html               accueil : présentation, expérience, projets,
│                            formation, compétences
├── projets/
│   ├── suguru.html          deep learning / CNN (2023-2024)
│   ├── site-aws.html        ce portfolio, côté infrastructure (2026)
│   ├── traitement-eau.html  filtre à eau, chef d'équipe de 13 (2023-2024)
│   └── risk.html            IA heuristique + MCTS pour PolyRisk (2025)
├── assets/
│   ├── style.css            feuille de style unique
│   ├── site.js              script unique (progressive enhancement)
│   ├── fonts/               Inter auto-hébergée, sous licence OFL
│   └── projets/             visuels des cartes et des pages projet
├── error403.html            erreur 403 (restriction géographique incluse)
├── error404.html            erreur 404
├── sitemap.xml
├── robots.txt
└── og.png                   image de partage social

tools/check_site.py          contrôles de cohérence (CI et local)
.github/workflows/
├── check.yml                vérifications sur PR et sur main
└── deploy.yml               publication sur S3 + invalidation CloudFront
```

## Développement local

Les liens du site sont absolus (`/assets/style.css`) : ouvrir `index.html`
directement en `file://` ne fonctionne pas. Il faut servir `site/` comme racine.

```bash
cd site
python3 -m http.server 8000
# puis http://localhost:8000
```

## Vérifier avant de pousser

```bash
python3 tools/check_site.py           # avertissements tolérés
python3 tools/check_site.py --strict  # avertissements bloquants
```

Le script ne dépend de rien (bibliothèque standard) et contrôle notamment :

- l'existence de tous les liens, images, scripts et ressources CSS internes ;
- la cohérence de `canonical`, `og:url`, du titre et de la description ;
- l'unicité des `id` et la présence d'un seul `<h1>` par page ;
- les attributs `alt`, `width` et `height` des images (évite le CLS) ;
- `sitemap.xml` (pages déclarées, pages indexables non déclarées, `lastmod`) ;
- `robots.txt` et l'absence de fichiers système dans `site/`.

Les avertissements sont des points de qualité (SEO, métadonnées) qui ne cassent
pas le site ; les erreurs bloquent le déploiement.

## Déploiement

Un push sur `main` touchant `site/**` déclenche [`deploy.yml`](.github/workflows/deploy.yml) :

```
push sur main
   │
   ├─ check.yml ........ contrôles de cohérence
   │                       └─ échec → rien n'est publié
   ▼
aws s3 sync site/ → s3://portfolio-noa     (4 passes, une par cache)
   ▼
invalidation CloudFront /*  (lancée, non attendue — voir récap)
   ▼
vérification des objets publiés (Content-Type, Cache-Control, ETag)
```

L'authentification se fait par **OIDC** : le workflow endosse le rôle
`github-deploy-portfolio` via le secret `AWS_DEPLOY_ROLE_ARN`. Aucune clé
d'accès n'est stockée dans le dépôt.

La vérification finale interroge S3 et non l'URL publique, car la restriction
géographique de CloudFront renvoie 403 aux runners GitHub.

### Règles de cache

| Type | `Cache-Control` | Raison |
|---|---|---|
| HTML, CSS, JS | `max-age=0, must-revalidate` | toujours la dernière version ; le navigateur revalide et reçoit un 304 |
| Polices | `max-age=31536000, immutable` | contenu figé, version dans le nom du fichier |
| Images, sitemap, robots | `max-age=86400` | changent rarement |

Pour changer la police, **renommer le fichier** : l'invalidation CloudFront ne
vide pas le cache du navigateur.

## Ajouter ou modifier une page

1. Créer le fichier dans `site/` et reprendre le `<head>` d'une page existante
   (charset, viewport, `lang="fr"`, `theme-color`, preload de la police,
   `stylesheet`, script inline de la classe `js`).
2. Renseigner `title`, `description`, `canonical` et `og:url` avec l'URL
   **exacte** de la page.
3. Utiliser des URL plates (`/projets/nom.html`), pas des dossiers : l'objet
   racine par défaut de CloudFront ne s'applique qu'à la racine.
4. Ajouter la page à `sitemap.xml`.
5. Lancer `python3 tools/check_site.py --strict`.
6. Si une page d'erreur est renommée, mettre à jour les règles « Pages d'erreur »
   de la distribution CloudFront — elles ne sont pas dans ce dépôt.

## Conventions

- Pas de build : ce qui est dans `site/` est exactement ce qui est publié.
- Le site doit rester lisible sans JavaScript ; le script n'ajoute que du confort.
- Une seule feuille de style, un seul script, une police auto-hébergée.
- Textes en français, contenu personnel : le code est réutilisable, les textes,
  photos et visuels ne le sont pas.
