# Sources des images

Fichiers maîtres des illustrations du site. **Ce dossier n'est pas
déployé** : le workflow ne synchronise que `site/`.

## `site-aws.svg`

Schéma de la carte « hébergement AWS ». Inter y est embarquée en
base64 (licence OFL), donc le fichier rend à l'identique partout, sans
dépendre des polices installées sur la machine.

Format de sortie imposé par `.card-media` dans `site/assets/style.css` :
**1200 × 750 px, ratio 16/10**. Le CSS applique `object-fit: cover`,
tout autre ratio serait rogné sans prévenir. Les attributs `width` et
`height` de la balise `<img>` dans `index.html` doivent correspondre au
pixel près, sinon la page saute au chargement.

### Régénérer le WebP

Ouvrir le SVG dans un navigateur, capturer à 1200 × 750, puis exporter
en WebP **qualité 0,95**. En dessous de 0,9 le dégradé sombre du fond
se met à faire des blocs — c'est le cas typique où la compression
avec perte se voit sur un aplat, pas sur une photo.

En ligne de commande, si `cwebp` est disponible :

    cwebp -q 95 rendu.png -o ../site/assets/projets/site-aws.webp
