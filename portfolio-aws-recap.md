# Portfolio sur AWS — fiche récap

Site statique hébergé sur AWS avec déploiement automatique depuis GitHub.
Ce document décrit ce qui a été construit, pourquoi, et comment le refaire de zéro.

---

## 1. Vue d'ensemble

```
 Développeur (VS Code)
        │  git push
        ▼
 GitHub (dépôt noameunier/portfolio)
        │  déclenche
        ▼
 GitHub Actions ──── OIDC ────► IAM (rôle github-deploy-portfolio)
        │                              │ droits limités
        │  aws s3 sync                 ▼
        └────────────────────────► S3 (bucket portfolio-noa, privé)
        │                              ▲ lecture via OAC uniquement
        │  create-invalidation         │
        └────────────────────────► CloudFront (distribution E3VGRIF45NWE2C)
                                       ▲ HTTPS (certificat ACM)
                                       │
 Visiteur ──► Route 53 (noameunier.fr → Alias CloudFront) ──┘
              ▲
              │ délégation NS
 Gandi (registrar du domaine)
```

Trajet d'une visite : le navigateur demande `noameunier.fr` → Route 53 répond « c'est CloudFront » → CloudFront sert le fichier depuis son cache, ou va le chercher dans S3 → le visiteur reçoit la page en HTTPS.

Trajet d'une mise à jour : `git push` sur `main` → GitHub Actions s'authentifie auprès d'AWS sans clé → copie `site/` vers S3 → demande à CloudFront de vider son cache → la nouvelle version est en ligne en ~1 minute.

---

## 2. Rôle de chaque service

| Service | Rôle | Analogie |
|---|---|---|
| **Gandi** | Registrar : détient le nom de domaine, on y renouvelle et on y choisit qui répond au DNS. | Le cadastre |
| **Route 53** | Hébergeur DNS : répond à « où est noameunier.fr ? ». Contient la zone hébergée et ses enregistrements. | L'annuaire |
| **ACM** | Délivre et renouvelle le certificat HTTPS gratuitement, après preuve de propriété du domaine par DNS. | La carte d'identité du site |
| **S3** | Stocke les fichiers du site (HTML, CSS, images). Bucket privé, personne n'y accède directement. | L'entrepôt |
| **CloudFront** | CDN : cache les fichiers dans le monde entier, sert en HTTPS, seule porte d'entrée vers S3. | La vitrine |
| **OAC** (Origin Access Control) | Identité que CloudFront présente à S3 pour lire le bucket privé. | Le badge de CloudFront |
| **IAM** | Gère qui a le droit de faire quoi : utilisateur `admin`, rôle pour GitHub, politiques. | Le service sécurité |
| **Fournisseur OIDC** | Dit à IAM de faire confiance aux jetons signés par GitHub. | L'accord de reconnaissance entre deux organisations |
| **GitHub Actions** | Exécute le pipeline à chaque push : authentification, envoi, invalidation. | Le livreur |
| **Budgets** | Alerte par email si les dépenses dépassent un seuil. N'arrête rien. | Le détecteur de fumée |

---

## 3. Liens entre les services

- **Gandi → Route 53** : chez Gandi, les serveurs de noms sont remplacés par les 4 `NS` de la zone Route 53. À partir de là, Gandi ne répond plus, Route 53 oui.
- **Route 53 → ACM** : ACM demande de créer deux `CNAME` de validation dans la zone. Leur présence prouve qu'on contrôle le domaine. Ils doivent rester en place pour le renouvellement automatique.
- **ACM → CloudFront** : le certificat est attaché à la distribution, avec les noms alternatifs `noameunier.fr` et `www.noameunier.fr`. Contrainte : le certificat doit être en région `us-east-1`.
- **Route 53 → CloudFront** : deux enregistrements `A` de type Alias (racine et `www`) pointent vers la distribution.
- **CloudFront → S3** : la distribution a le bucket comme origine et s'y authentifie via l'OAC. Une politique de bucket n'autorise que `cloudfront.amazonaws.com` avec l'ARN de cette distribution.
- **GitHub → IAM** : le fournisseur OIDC reconnaît les jetons de `token.actions.githubusercontent.com`. Le rôle `github-deploy-portfolio` n'accepte que les jetons dont le `sub` correspond au dépôt.
- **IAM → S3 / CloudFront** : la politique du rôle autorise uniquement écrire/supprimer dans le bucket et invalider cette distribution. Rien d'autre.

---

## 4. Identifiants de cette infrastructure

| Élément | Valeur |
|---|---|
| ID de compte AWS | `710165591195` |
| Utilisateur IAM quotidien | `admin` (groupe `admins`, `AdministratorAccess`) |
| URL de connexion | `https://710165591195.signin.aws.amazon.com/console` |
| Région principale | `eu-west-3` (Paris) |
| Bucket S3 | `portfolio-noa` |
| Distribution CloudFront | `E3VGRIF45NWE2C` |
| Domaine | `noameunier.fr` (Gandi) |
| Serveurs NS Route 53 | `ns-211.awsdns-26.com`, `ns-1455.awsdns-53.org`, `ns-981.awsdns-58.net`, `ns-1584.awsdns-06.co.uk` |
| Rôle IAM pour GitHub | `arn:aws:iam::710165591195:role/github-deploy-portfolio` |
| Dépôt GitHub | `noameunier/portfolio` (id `1348474823`, owner id `201812491`) |
| Budget | `plafond-mensuel`, 5 USD/mois |

---

## 5. Procédure de redéploiement de zéro

Ordre à respecter : chaque étape dépend de la précédente. Lieu indiqué à chaque fois.

### Étape 0 — Compte et sécurité

1. Créer le compte AWS. Activer le MFA sur le root. *(console, root)*
2. Passer au plan payant si le compte est en « Free plan » : Route 53 et l'achat de domaine y sont bloqués. *(console, root → Facturation)*
3. Activer l'accès IAM à la facturation : Compte → « Accès des utilisateurs IAM aux informations de facturation ». *(console, root)*
4. Créer l'utilisateur IAM `admin` avec accès console, dans un groupe `admins` portant `AdministratorAccess`. Activer son MFA. *(console, root → IAM)*
5. Se déconnecter du root. Tout le reste se fait en `admin`.
6. Créer un budget mensuel (modèle simplifié, 5 USD, email). *(console → Budgets)*

### Étape 1 — S3

1. Créer un bucket : région Paris, espace de noms global, nom unique en minuscules, ACL désactivées, « Bloquer tous les accès publics » coché, chiffrement SSE-S3. *(console → S3)*
2. Y charger le contenu du dossier `site/` à la racine du bucket (bouton Charger, ou `aws s3 sync ./site s3://NOM_BUCKET`). *(console ou CLI)*
3. Ne pas activer « Hébergement de site web statique » : ce mode exige un bucket public.

### Étape 2 — Certificat ACM

1. Passer en région **us-east-1**. *(console, sélecteur de région)*
2. Certificate Manager → Demander → certificat public → noms `domaine.fr` et `www.domaine.fr` → validation DNS → RSA 2048.
3. Le certificat reste « En attente de validation » jusqu'à l'étape 4.

### Étape 3 — CloudFront

1. Région Paris → CloudFront → Créer une distribution. *(console)*
2. Origine : le bucket S3. Accès à l'origine : OAC, laisser AWS écrire la politique du bucket (« Grant CloudFront access : Yes »).
3. Protocole : redirect HTTP → HTTPS. Cache : CachingOptimized. WAF : désactivé. Plan : Free ou Pay-as-you-go.
4. Noms alternatifs et certificat : vides pour l'instant.
5. Après création : Général → Paramètres → Modifier → **Objet racine par défaut** = `index.html`.
6. Noter l'ID de distribution et le domaine `xxxx.cloudfront.net`. Tester dans le navigateur.

### Étape 4 — Domaine et DNS

1. Acheter le domaine chez un registrar (Gandi). *(site du registrar)*
2. Route 53 → Zones hébergées → Créer → nom du domaine, zone publique. Noter les 4 `NS`. *(console)*
3. Chez le registrar : Serveurs de noms → Externes → coller les 4 `NS`. *(site du registrar)*
4. Attendre la propagation : `nslookup -type=NS domaine.fr 8.8.8.8` doit renvoyer les `awsdns`. *(cmd Windows)*
5. ACM (us-east-1) → certificat → « Créer des enregistrements dans Route 53 ». Attendre « Émis » (5 à 30 min). *(console)*
6. CloudFront → distribution → Modifier → noms alternatifs `domaine.fr` + `www.domaine.fr`, certificat SSL personnalisé = celui d'ACM. Attendre le déploiement. *(console)*
7. Route 53 → zone → Créer un enregistrement : nom vide, type A, Alias vers la distribution CloudFront. Idem avec nom `www`. *(console)*
8. Tester `https://domaine.fr` et `https://www.domaine.fr`.

### Étape 5 — Pipeline GitHub Actions

1. IAM → Fournisseurs d'identité → Ajouter → OpenID Connect → URL `https://token.actions.githubusercontent.com`, Public (audience) `sts.amazonaws.com`. *(console)*
2. IAM → Rôles → Créer → Identité Web → fournisseur ci-dessus, audience `sts.amazonaws.com`, organisation = identifiant GitHub, dépôt = nom du dépôt. Aucune permission à l'écran suivant. Nom `github-deploy-portfolio`.
3. Sur le rôle → Relations d'approbation → Modifier → coller la politique d'approbation (section 6). **Adapter le `sub` au format réel du jeton** (voir pièges).
4. Sur le rôle → Autorisations → Créer une politique en ligne → JSON → coller la politique de déploiement (section 6).
5. Dans le dépôt : créer `.github/workflows/deploy.yml` (section 6). Renseigner bucket, ID de distribution, ARN du rôle (en dur ou via un secret GitHub `AWS_DEPLOY_ROLE_ARN`). *(VS Code)*
6. Commit, push. Vérifier dans GitHub → Actions que tout est vert. Modifier `index.html`, push, vérifier le site.

---

## 6. Fichiers de configuration

### Politique d'approbation du rôle (trust policy)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::710165591195:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:noameunier@201812491/portfolio@1348474823:*"
        }
      }
    }
  ]
}
```

### Politique de permissions du rôle

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::portfolio-noa",
        "arn:aws:s3:::portfolio-noa/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": "cloudfront:CreateInvalidation",
      "Resource": "arn:aws:cloudfront::710165591195:distribution/E3VGRIF45NWE2C"
    }
  ]
}
```

### Workflow `.github/workflows/deploy.yml`

Le fichier complet vit dans le dépôt : il n'est volontairement pas recopié ici, pour qu'une copie ne puisse pas diverger du code réel. Il enchaîne quatre étapes :

1. Un job `verifier` appelle `check.yml` (liens, SEO, sitemap, ressources). Un échec bloque la publication.
2. `aws s3 sync site/ s3://portfolio-noa`, en quatre passes (HTML ; CSS et JS ; polices ; le reste), chacune avec son `Cache-Control`.
3. `aws cloudfront create-invalidation --paths '/*'`. L'invalidation n'est pas attendue : le rôle ne dispose que de `cloudfront:CreateInvalidation`, alors que le waiter utilise `cloudfront:GetInvalidation`. Ajouter cette permission au rôle permettrait de l'attendre.
4. Vérification des objets publiés : présence, taille et ETag (MD5) comparés au fichier local, via `list-objects-v2` (`s3:ListBucket`). Content-Type et Cache-Control demanderaient `s3:GetObject`, non accordé. Le test interroge S3 et non l'URL publique, car la restriction géographique renvoie 403 aux runners GitHub.

L'authentification se fait avec `aws-actions/configure-aws-credentials` et le secret `AWS_DEPLOY_ROLE_ARN`, qui contient l'ARN du rôle endossé par OIDC.

Le script de contrôle, `tools/check_site.py`, n'utilise que la bibliothèque standard de Python. Il vérifie l'existence des liens et des ressources, la cohérence de `canonical` et `og:url`, l'unicité des `id`, la présence de `alt`/`width`/`height` sur les images, et l'alignement de `sitemap.xml` avec les pages réellement indexables. Il tourne aussi sur chaque pull request.

Le `--delete` de chaque passe est sans danger : les filtres `--exclude` / `--include` s'appliquent aussi bien au dossier local qu'au bucket, donc une passe ne peut supprimer que des fichiers qu'elle gère elle-même.

Le cas des polices mérite l'attention inverse de celle du CSS (voir le dernier piège de la section 7). Une police ne change jamais : la mettre en cache un an évite de refaire descendre 47 Ko à chaque visiteur. En contrepartie, l'invalidation CloudFront ne rattrape pas le cache du navigateur — **pour changer de police il faut changer le nom du fichier**, jamais seulement son contenu, sinon les visiteurs gardent l'ancienne jusqu'à un an. D'où le numéro de version dans `inter-v20-latin-var.woff2`.

---

## 6 bis. Options CloudFront ajoutées ensuite

### Pages d'erreur personnalisées

Avoir une page d'erreur dans le bucket ne suffit pas : CloudFront affiche sa propre page tant qu'on ne lui indique pas quoi servir. *(console → CloudFront → distribution → onglet Pages d'erreur)*

Configuration actuelle (deux pages distinctes depuis la refonte du site) :

| Code d'erreur | Chemin de la page | Code de réponse | TTL |
|---|---|---|---|
| 403 | `/error403.html` | 403 | 10 s |
| 404 | `/error404.html` | 404 | 10 s |

Pourquoi le 403 compte autant que le 404 : avec un bucket privé lu via OAC, S3 répond « interdit » (403) et non « introuvable » (404) pour un fichier absent, car le rôle de lecture n'autorise pas à lister le bucket. Le 403 est aussi le code renvoyé par la restriction géographique — la page `error403.html` mentionne d'ailleurs explicitement la restriction régionale pour que le visiteur bloqué comprenne. La page d'erreur est servie par la même distribution, donc elle reste accessible même pour un visiteur hors zone.

Attention à la cohérence : si les fichiers d'erreur sont renommés dans le dépôt, les règles CloudFront doivent être mises à jour à la main, sinon une erreur affiche… une erreur.

Test : ouvrir `https://noameunier.fr/nimportequoi` doit afficher `error403.html`.

### Restriction géographique (geofencing)

Fonction native et gratuite de CloudFront, basée sur le pays de l'adresse IP du visiteur. *(console → CloudFront → distribution → onglet Sécurité → Restrictions géographiques → Modifier)*

- Type : liste d'autorisation.
- Pays : liste de pays européens (élargie depuis la France seule ; pas de case « Europe », chaque pays se coche individuellement).

Un visiteur hors de la liste reçoit un 403, donc `error403.html`.

À savoir :
- La géolocalisation IP n'est pas parfaite : VPN, réseaux d'entreprise et certains opérateurs mobiles peuvent être classés ailleurs. Les DOM-TOM ont leurs propres codes pays.
- Pour un portfolio, cela bloque un recruteur situé hors de la liste. Facile à élargir ou désactiver.
- Le pipeline n'est pas affecté : GitHub Actions parle à l'API S3 et CloudFront, pas à la distribution publique.
- Pour filtrer par plage d'IP ou combiner plusieurs règles, il faut AWS WAF (payant). La restriction par pays suffit pour ce besoin.

---

## 6 ter. Structure du site et choix d'URL

Depuis la refonte, le site est multi-pages, en français uniquement, ~200 Ko, sans framework ni étape de build :

```
site/                          (= racine du bucket)
├── index.html                 page d'accueil
├── assets/style.css           feuille de style unique
├── assets/site.js             script unique
├── assets/fonts/              Inter auto-hébergée (47 Ko, un fichier variable)
├── projets/*.html             4 pages projet, toutes rédigées et indexées
├── error403.html              page d'erreur 403 (mentionne la restriction géo)
├── error404.html              page d'erreur 404
├── sitemap.xml                déclare l'accueil et les 4 pages projet
├── robots.txt                 déclare le sitemap
└── og.png                     image de partage
```

**Choix d'URL : des fichiers `.html` plats** (`/projets/suguru.html`), pas des dossiers (`/projets/suguru/`). Raison : l'objet racine par défaut de CloudFront (`index.html`) ne s'applique qu'à la racine de la distribution, pas aux sous-dossiers. Une requête sur `/projets/suguru/` chercherait la clé S3 `projets/suguru/`, inexistante, et renverrait 403. Conséquence : aucune modification CloudFront n'est nécessaire pour les pages en sous-dossier. Pour des URL sans extension un jour, il faudrait une CloudFront Function en viewer-request qui réécrit les chemins vers le `.html` correspondant.

**Compatibilité avec le workflow** : dans les filtres S3 de l'AWS CLI, `*` traverse les `/`. La passe `--include '*.html'` attrape donc `projets/suguru.html`, et la passe `--exclude '*.html'` attrape `assets/style.css` et `assets/site.js`. Aucun changement de workflow requis. Le `--delete` retire du bucket les fichiers supprimés du dépôt (ex. l'ancienne version anglaise `en.html`).

**Développement local** : les chemins étant absolus (`/assets/style.css`), ouvrir `index.html` en `file://` ne fonctionne pas. Servir le dossier comme racine : `cd site && python -m http.server 8000`.

---

## 6 quater. En-têtes de sécurité et CSP

Le site ne charge aucune ressource tierce : police, styles, script et images viennent de la même distribution. Une CSP stricte est donc possible sans concession.

### Ce qui a changé dans le code

Les styles inline ont disparu, car `style-src 'self'` les refuserait :

- les couleurs d'accent des cartes et des pages projet sont dans les classes `.accent-bleu`, `.accent-nuit`, `.accent-azur` ;
- les règles des pages d'erreur sont dans `style.css` (`.error-page`).

Le seul script inline restant est la pose de la classe `js` dans le `<head>`, avant le premier rendu. Il est autorisé par empreinte :

```bash
printf '%s' "document.documentElement.classList.add('js');" \
  | openssl dgst -sha256 -binary | base64
# /x7W7R75k8Roq0WaVRQX9blP4OufE5xbAdzklGxsgpw=
```

`tools/check_site.py` refuse tout attribut `style=`, tout bloc `<style>`, tout gestionnaire `on…=` et tout script inline dont l'empreinte diffère de `HASH_SCRIPT`. **Modifier ce script impose donc de mettre à jour la constante et l'en-tête CloudFront.**

### Politique de réponse CloudFront

*(console → CloudFront → Policies → Response headers → Create policy)*

En-têtes gérés par CloudFront :

| En-tête | Valeur |
|---|---|
| Strict-Transport-Security | `max-age=31536000; includeSubDomains` |
| X-Content-Type-Options | `nosniff` |
| X-Frame-Options | `DENY` |
| Referrer-Policy | `strict-origin-when-cross-origin` |

En-têtes personnalisés :

| En-tête | Valeur |
|---|---|
| Content-Security-Policy | `default-src 'none'; script-src 'self' 'sha256-/x7W7R75k8Roq0WaVRQX9blP4OufE5xbAdzklGxsgpw='; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'` |
| Permissions-Policy | `accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()` |

`img-src` autorise `data:` parce que la favicon et la texture de bruit du CSS sont des data URI.

Puis attacher la politique à la distribution : Behaviors → Default (`*`) → Edit → Response headers policy. Ne pas activer `preload` dans HSTS avant d'être certain qu'aucun sous-domaine ne sert du HTTP : la sortie est difficile à annuler.

Le header `server: AmazonS3` reste visible. Une CloudFront Function en viewer-response peut le supprimer (`delete event.response.headers['server'];`), mais c'est cosmétique.

### Redirection www → apex

*(console → CloudFront → Functions → Create function, runtime `cloudfront-js-2.0`, événement viewer-request)*

```js
function handler(event) {
  var request = event.request;
  if (request.headers.host.value !== 'www.noameunier.fr') {
    return request;
  }
  return {
    statusCode: 301,
    statusDescription: 'Moved Permanently',
    headers: {
      location: { value: 'https://noameunier.fr' + request.uri }
    }
  };
}
```

Publier la fonction, puis l'associer à la distribution (Behaviors → Default → Function associations → Viewer request). Le site n'utilise pas de chaîne de requête ; si cela change, réinjecter `request.querystring` dans la redirection.

### Vérifier

```bash
curl -sI https://noameunier.fr/ | grep -iE 'strict-transport|content-security|x-content-type|referrer-policy|permissions-policy'
curl -sI https://www.noameunier.fr/ | head -3   # doit renvoyer 301 vers l'apex
```

Compléter avec `securityheaders.com` et `csp-evaluator.withgoogle.com`.

---

## 7. Pièges rencontrés et solutions

| Symptôme | Cause | Solution |
|---|---|---|
| `aws --version` : « Une stratégie de contrôle d'application a bloqué ce fichier » | Smart App Control de Windows 11 bloque une DLL de l'AWS CLI | Désactiver Smart App Control, ou `pip install awscli`, ou utiliser CloudShell dans le navigateur |
| CloudShell renvoie `:root` dans `get-caller-identity` | CloudShell hérite de la session console | Se reconnecter en `admin` puis rouvrir CloudShell |
| Route 53 : « Free Tier accounts are not supported for this service » | Le plan gratuit bloque l'achat de domaine et l'écriture dans les zones | Acheter le domaine ailleurs et/ou passer au plan payant |
| Certificat introuvable dans CloudFront | Créé dans une autre région que `us-east-1` | Le recréer en `us-east-1` |
| Certificat reste « en attente » | CNAME de validation absents, ou NS pas encore propagés | Vérifier la zone Route 53 et `nslookup -type=NS domaine 8.8.8.8` |
| `nslookup` : « Non-existent domain » | Cache de la box, ou domaine pas encore actif au registre | Interroger `8.8.8.8` directement, attendre |
| Distribution absente dans la liste Alias de Route 53 | Le nom alternatif n'est pas encore ajouté sur CloudFront | Ajouter le CNAME sur CloudFront d'abord, ou coller le nom `xxx.cloudfront.net` à la main |
| CloudFront : erreur sur `/` mais OK sur `/index.html` | Objet racine par défaut non renseigné | Général → Paramètres → Objet racine = `index.html` |
| GitHub Actions : « Not authorized to perform sts:AssumeRoleWithWebIdentity » | Le `sub` du jeton GitHub a un nouveau format `repo:owner@ID/repo@ID:...` | Lire le jeton réel (étape de debug) et adapter la condition `sub` du rôle |
| Page IAM « Identité Web » vs « Service AWS » | Mauvais type d'entité de confiance | GitHub = Identité Web ; EC2/Lambda = Service AWS |
| Une erreur affiche le XML AWS malgré des pages d'erreur configurées | Les règles CloudFront pointent vers un fichier renommé ou supprimé du bucket (ex. `/error.html` devenu `error403.html`) | Aligner les règles Pages d'erreur sur les noms de fichiers réels après chaque refonte |
| `/projets/xxx/` (avec slash) renvoie 403 | L'objet racine par défaut ne s'applique qu'à la racine, et la clé S3 `projets/xxx/` n'existe pas | Utiliser des URL plates `.html`, ou ajouter une CloudFront Function de réécriture |
| Après déploiement, HTML à jour mais design cassé, alors que tout est correct dans le dépôt | Le CSS était envoyé avec `max-age=86400`. L'invalidation CloudFront vide le cache du CDN, pas celui du navigateur, qui garde son ancienne feuille de style jusqu'à 24 h | Vérifier d'abord avec `Ctrl+Maj+R` ou une fenêtre privée. Correction durable : envoyer le CSS et le JS avec `max-age=0, must-revalidate`, comme le HTML |
| `aws cloudfront wait invalidation-completed` échoue aussitôt pendant le déploiement | Le waiter appelle `cloudfront:GetInvalidation`, absent de la politique du rôle (limitée à `CreateInvalidation`) | Soit ne pas attendre, soit ajouter `cloudfront:GetInvalidation` à la politique de déploiement |
| La vérification post-déploiement échoue en `AccessDenied` | `s3api head-object` exige `s3:GetObject`, alors que le rôle n'a que `PutObject`, `DeleteObject` et `ListBucket` | Utiliser `list-objects-v2` (taille et ETag, via `ListBucket`), ou accorder `s3:GetObject` pour contrôler aussi les métadonnées |
| Après activation de la CSP, les couleurs ou les animations disparaissent | Styles inline (accents, pages d'erreur) ou script inline dont l'empreinte a changé | Classes d'accent, styles d'erreur dans `style.css`, et empreinte à jour dans `HASH_SCRIPT` comme dans l'en-tête CloudFront |

Méthode générale qui a débloqué le pipeline : quand tout semble correct, faire afficher la donnée réelle (ici le jeton OIDC) plutôt que de deviner.

---

## 8. Coûts

| Poste | Coût mensuel estimé |
|---|---|
| Zone hébergée Route 53 | 0,50 $ |
| S3 (quelques Mo, police incluse) | < 0,01 $ |
| CloudFront (1 To et 10 M requêtes gratuits à vie) | 0 $ |
| ACM, IAM, Budgets | 0 $ |
| GitHub Actions (dépôt public) | 0 $ |
| Nom de domaine (Gandi, annuel) | ~1 $/mois lissé |
| **Total** | **~0,50 $/mois + domaine** |

À ne jamais créer pour un site statique : EC2, NAT Gateway (~32 $/mois), RDS, WAF.

---

## 9. Concepts appris

- **Root vs utilisateur IAM** : le root détient tout, ne sert qu'à quelques opérations rares (MFA, facturation, fermeture). Le travail quotidien se fait avec un utilisateur aux droits délégués.
- **Utilisateur vs rôle** : un utilisateur est une personne avec mot de passe ; un rôle est une identité temporaire endossée par un service ou un système externe.
- **Moindre privilège** : le rôle GitHub ne peut qu'écrire dans un bucket et invalider une distribution. Rien d'autre.
- **OIDC** : authentification sans clé stockée. GitHub signe un jeton, AWS vérifie la signature et les conditions. Rien à faire tourner ni à faire expirer.
- **Registrar vs DNS** : deux rôles distincts, souvent chez le même prestataire mais pas obligatoirement.
- **Délégation NS** : changer les serveurs de noms chez le registrar transfère l'autorité DNS à un autre hébergeur.
- **Validation DNS d'un certificat** : prouver la propriété d'un domaine en y écrivant un enregistrement que seul le propriétaire peut créer.
- **Bucket privé + OAC** : le stockage n'est jamais exposé ; le CDN est la seule porte, et il s'authentifie.
- **Cache et invalidation** : un CDN sert des copies ; après déploiement il faut lui dire de les jeter.
- **Alias vs CNAME** : l'Alias Route 53 permet de pointer la racine d'un domaine vers CloudFront, ce qu'un CNAME classique interdit, et il est gratuit.
- **Plan gratuit AWS** : pratique pour démarrer, mais bloque des services entiers. À connaître avant de planifier.

---

## 10. Suites possibles

1. **Version anglaise** : une page `/en.html` ou une arborescence `/en/`, avec `hreflang` réciproque, pour les recruteurs étrangers visés par la recherche de stage.
2. **Branche + pull request** : développer sur une branche, fusionner via PR ; la fusion sur `main` déclenche le déploiement.
3. **Terraform** : décrire bucket, OAC, distribution, certificat, zone, enregistrements, fournisseur OIDC, rôle et politiques en code. Détruire et recréer en une commande.
4. **Observabilité** : regarder les métriques CloudFront (requêtes, taux de cache, erreurs, répartition par pays) dans CloudWatch.
5. **Certification** : AWS Cloud Practitioner, puis Solutions Architect Associate.
