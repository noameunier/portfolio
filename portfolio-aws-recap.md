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

```yaml
name: Déployer le site

on:
  push:
    branches: [main]
    paths: ['site/**', '.github/workflows/deploy.yml']
  workflow_dispatch:

permissions:
  id-token: write
  contents: read

concurrency:
  group: deploy-site
  cancel-in-progress: true

env:
  BUCKET: portfolio-noa
  DISTRIBUTION_ID: E3VGRIF45NWE2C
  AWS_REGION: eu-west-3

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: S'authentifier auprès d'AWS
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_DEPLOY_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Envoyer les fichiers HTML
        run: |
          aws s3 sync site/ "s3://$BUCKET" \
            --delete \
            --exclude '*' --include '*.html' \
            --cache-control 'public, max-age=0, must-revalidate' \
            --content-type 'text/html; charset=utf-8'

      - name: Envoyer les autres fichiers
        run: |
          aws s3 sync site/ "s3://$BUCKET" \
            --delete \
            --exclude '*.html' \
            --cache-control 'public, max-age=86400'

      - name: Vider le cache CloudFront
        run: |
          aws cloudfront create-invalidation \
            --distribution-id "$DISTRIBUTION_ID" \
            --paths '/*'
```

Pourquoi deux `sync` : l'option `--cache-control` s'applique à toute la commande. Le HTML est envoyé sans cache navigateur (toujours la dernière version), le reste avec un cache d'un jour. L'invalidation force CloudFront à relire S3.

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

Méthode générale qui a débloqué le pipeline : quand tout semble correct, faire afficher la donnée réelle (ici le jeton OIDC) plutôt que de deviner.

---

## 8. Coûts

| Poste | Coût mensuel estimé |
|---|---|
| Zone hébergée Route 53 | 0,50 $ |
| S3 (quelques Mo) | < 0,01 $ |
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

1. **Test avant déploiement** : ajouter une étape dans le workflow (validation HTML, détection de liens morts) qui bloque le déploiement en cas d'échec.
2. **Branche + pull request** : développer sur une branche, fusionner via PR ; la fusion sur `main` déclenche le déploiement.
3. **Terraform** : décrire bucket, OAC, distribution, certificat, zone, enregistrements, fournisseur OIDC, rôle et politiques en code. Détruire et recréer en une commande.
4. **Page d'erreur** : configurer `error.html` comme réponse personnalisée 403/404 dans CloudFront.
5. **Observabilité** : regarder les métriques CloudFront (requêtes, taux de cache, erreurs) dans CloudWatch.
6. **Certification** : AWS Cloud Practitioner, puis Solutions Architect Associate.
