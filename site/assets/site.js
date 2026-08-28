/* ═══════════════════════════════════════════════════════════════════
   NOA MEUNIER — script unique du site
   ───────────────────────────────────────────────────────────────────
   Règle qui gouverne tout ce fichier : le site doit rester complet et
   lisible sans lui. Le script n'ajoute que du confort — apparition au
   défilement, section active, barre de progression, bouton d'impression.
   Rien d'essentiel n'en dépend.

   La classe `js` est posée à part, en ligne dans le <head> de chaque
   page, avant le premier rendu : c'est elle qui autorise le CSS à
   masquer les blocs avant leur apparition. Si ce fichier ne se charge
   pas, `revele()` remet tout visible dès le premier appel.
   ═══════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  var doc = document;
  var reduit = window.matchMedia &&
               window.matchMedia('(prefers-reduced-motion: reduce)').matches;


  /* ── 1. Apparition au défilement ─────────────────────────────────
     Chaque bloc portant `.reveal` apparaît une fois, quand il entre
     dans l'écran. Les blocs voisins d'un même parent sont décalés de
     70 ms les uns des autres (variable --i lue par le CSS).          */
  var aReveler = [].slice.call(doc.querySelectorAll('.reveal'));

  function toutMontrer() {
    aReveler.forEach(function (el) { el.classList.add('in'); });
  }

  if (!aReveler.length) {
    /* rien à faire */
  } else if (reduit || !('IntersectionObserver' in window)) {
    toutMontrer();
  } else {
    /* Décalage : position du bloc parmi ses frères également révélés. */
    var compteurs = new Map();
    aReveler.forEach(function (el) {
      var parent = el.parentNode;
      var n = compteurs.get(parent) || 0;
      compteurs.set(parent, n + 1);
      el.style.setProperty('--i', Math.min(n, 6));
    });

    var vigie = new IntersectionObserver(function (entrees) {
      entrees.forEach(function (e) {
        if (!e.isIntersecting) { return; }
        e.target.classList.add('in');
        vigie.unobserve(e.target);   /* une seule fois, jamais au retour */
      });
    }, {
      /* Déclenche un peu avant le bas de l'écran : le bloc est déjà
         en place quand le regard y arrive. */
      rootMargin: '0px 0px -12% 0px',
      threshold: 0.05
    });

    aReveler.forEach(function (el) { vigie.observe(el); });

    /* Filet de sécurité : au-delà de 3 s, on montre tout, quoi qu'il
       arrive (onglet resté en arrière-plan, observateur muet…). */
    window.setTimeout(toutMontrer, 3000);
  }


  /* ── 2. Barre de progression et ombre de la barre de navigation ── */
  var barre = doc.querySelector('.progress');
  var nav   = doc.querySelector('.nav');
  var tic   = false;

  function auDefilement() {
    var y = window.scrollY || doc.documentElement.scrollTop;

    if (barre) {
      var total = doc.documentElement.scrollHeight - window.innerHeight;
      var part  = total > 0 ? Math.min(y / total, 1) : 0;
      barre.style.transform = 'scaleX(' + part + ')';
    }
    if (nav) { nav.classList.toggle('stuck', y > 8); }

    marquerSection();

    tic = false;
  }

  function planifier() {
    if (tic) { return; }
    tic = true;
    window.requestAnimationFrame(auDefilement);
  }

  if (barre || nav) {
    window.addEventListener('scroll', planifier, { passive: true });
    window.addEventListener('resize', planifier, { passive: true });
    auDefilement();
  }


  /* ── 3. Section active dans la navigation ────────────────────────
     Calculé à la géométrie, dans le même passage que le défilement.
     Un IntersectionObserver accumulait un état qui pouvait rester
     périmé après un saut brusque (ancre, fin de page) et désignait
     alors la mauvaise section. Ici rien n'est mémorisé : à chaque
     image, on relit les positions réelles.

     Règle : la section active est la dernière dont le haut est déjà
     passé au-dessus du tiers supérieur de l'écran. Arrivé en bas de
     page, c'est toujours la dernière, sinon la section finale ne
     serait jamais marquée. */
  var liens = [].slice.call(doc.querySelectorAll('.nav-links a[href^="#"]'));
  var sections = [];

  liens.forEach(function (a) {
    var section = doc.getElementById(a.getAttribute('href').slice(1));
    if (section) { sections.push({ lien: a, el: section }); }
  });

  function marquerSection() {
    /* Appelée une première fois par auDefilement(), avant même que la
       liste ci-dessus soit construite : elle doit le supporter. */
    if (!sections || !sections.length) { return; }

    var seuil = window.innerHeight * 0.3;
    var enBas = window.innerHeight + window.scrollY >=
                doc.documentElement.scrollHeight - 2;
    var actif = enBas ? sections[sections.length - 1] : null;

    if (!actif) {
      for (var i = 0; i < sections.length; i++) {
        if (sections[i].el.getBoundingClientRect().top <= seuil) {
          actif = sections[i];
        }
      }
    }

    sections.forEach(function (s) {
      if (s === actif) { s.lien.setAttribute('aria-current', 'true'); }
      else { s.lien.removeAttribute('aria-current'); }
    });
  }

  marquerSection();

  /* ── 4. L'année du pied de page ──────────────────────────────────
     Écrite en dur dans le HTML : ceci ne fait que la rafraîchir.     */
  var annee = doc.getElementById('annee');
  if (annee) { annee.textContent = new Date().getFullYear(); }


  /* ── 5. Impression ───────────────────────────────────────────────
     Il n'y a plus de bouton dans la page, mais Ctrl/⌘+P reste
     possible : avant toute impression, on force l'affichage des blocs
     pas encore apparus. Sans cela, on imprimerait du vide. */
  window.addEventListener('beforeprint', toutMontrer);
  if (window.matchMedia) {
    var impression = window.matchMedia('print');
    var surChangement = function (e) { if (e.matches) { toutMontrer(); } };
    if (impression.addEventListener) { impression.addEventListener('change', surChangement); }
    else if (impression.addListener) { impression.addListener(surChangement); }
  }

}());
