# Instructions pour Claude

L'utilisateur parle français. Ce dépôt sert à générer des vidéos courtes avec
MoneyPrinterTurbo (voir README.md).

## Quand l'utilisateur demande une vidéo

1. Lance `./video.sh "<sujet>"` depuis la racine du dépôt, en **premier plan**,
   avec un timeout d'au moins 20 minutes. Le script installe et configure
   MoneyPrinterTurbo tout seul si besoin.
   - Voix d'homme : `VOIX=homme` ; format horizontal : `FORMAT=16:9` ; carré : `FORMAT=1:1`.
   - Vidéo plus longue : ajoute `--paragraph-number N` (1 à 10).
   - Musique : `AMBIANCE=suspense` (true crime, mystère, horreur), `AMBIANCE=calme`
     (bien-être, nature), `AMBIANCE=aucune`. Choisis-la selon le sujet si
     l'utilisateur ne précise rien.
   - Si le sujet a un mot ambigu pour les banques d'images (ex. « Zodiac » →
     astrologie), impose des mots-clés anglais concrets avec
     `--video-terms "police car night,old newspaper,..."`.
   - Les sous-titres sont calés automatiquement sur la voix (tools/sync_subs.py) ;
     ne réactive pas ceux de MoneyPrinterTurbo.
2. Récupère la ligne `VIDEO_FILE=...` et envoie le fichier à l'utilisateur
   avec `SendUserFile` (display: render).
3. Ne commit **jamais** de vidéo ni de clé API.

## En cas de problème

- Code de sortie 10 : `GEMINI_API_KEY` ou `PIXABAY_API_KEY` manque. Explique à
  l'utilisateur comment l'ajouter dans les variables d'environnement cloud
  (README, étape 3). Ne lui demande pas de coller la clé dans le chat.
- Erreur 503 de Gemini : relance avec `GEMINI_MODEL=gemini-3.8-flash` (ou un autre modèle flash).
- Erreur réseau (proxy 403, connexion refusée) : identifie le domaine bloqué et
  demande à l'utilisateur de l'ajouter dans « Allowed domains » (README, étape 2).
- En cas d'échec, lis seulement la fin du log, pas tout le log.
- N'affiche jamais le contenu de `~/MoneyPrinterTurbo/config.toml` : il contient les clés.
