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
     On suit les <section id> et on marque le lien correspondant. La
     bande observée est le tiers haut de l'écran : la section active
     est celle qu'on est en train de lire, pas celle qui affleure.    */
  var liens = [].slice.call(doc.querySelectorAll('.nav-links a[href^="#"]'));

  if (liens.length && 'IntersectionObserver' in window) {
    var parId = {};
    var cibles = [];

    liens.forEach(function (a) {
      var section = doc.getElementById(a.getAttribute('href').slice(1));
      if (section) { parId[section.id] = a; cibles.push(section); }
    });

    var visibles = new Set();

    var suiveur = new IntersectionObserver(function (entrees) {
      entrees.forEach(function (e) {
        if (e.isIntersecting) { visibles.add(e.target.id); }
        else { visibles.delete(e.target.id); }
      });

      /* La première section visible dans l'ordre du document gagne. */
      var actif = null;
      for (var i = 0; i < cibles.length; i++) {
        if (visibles.has(cibles[i].id)) { actif = cibles[i].id; break; }
      }

      liens.forEach(function (a) {
        var id = a.getAttribute('href').slice(1);
        if (id === actif) { a.setAttribute('aria-current', 'true'); }
        else { a.removeAttribute('aria-current'); }
      });
    }, { rootMargin: '-20% 0px -60% 0px', threshold: 0 });

    cibles.forEach(function (s) { suiveur.observe(s); });
  }


  /* ── 4. L'année du pied de page ──────────────────────────────────
     Écrite en dur dans le HTML : ceci ne fait que la rafraîchir.     */
  var annee = doc.getElementById('annee');
  if (annee) { annee.textContent = new Date().getFullYear(); }


  /* ── 5. Bouton d'impression ──────────────────────────────────────
     Caché dans le HTML, révélé seulement ici : proposer un bouton
     mort serait pire que ne pas en proposer.                         */
  var bouton = doc.querySelector('.print');
  if (bouton) {
    bouton.hidden = false;
    bouton.addEventListener('click', function () { window.print(); });
  }

  /* Avant toute impression, y compris Ctrl/⌘+P, on force l'affichage
     des blocs pas encore apparus. Sans cela, on imprime du vide. */
  window.addEventListener('beforeprint', toutMontrer);
  if (window.matchMedia) {
    var impression = window.matchMedia('print');
    var surChangement = function (e) { if (e.matches) { toutMontrer(); } };
    if (impression.addEventListener) { impression.addEventListener('change', surChangement); }
    else if (impression.addListener) { impression.addListener(surChangement); }
  }

}());
