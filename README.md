# MoneyPrint — vidéos courtes par IA avec Claude Code

Ce dépôt sert à générer des vidéos courtes (TikTok, Reels, Shorts) avec
[MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo), directement
depuis une session **Claude Code dans le cloud**.

Tu donnes un sujet. L'outil écrit le script, trouve les images, ajoute la voix
off, les sous-titres et la musique, puis sort un MP4.

## Comment ça marche

| Étape | Outil | Coût |
|---|---|---|
| Écriture du script | Google **Gemini** (`gemini-3.5-flash`) | gratuit (clé Google AI Studio) |
| Vidéos d'illustration | **Pixabay** | gratuit (clé Pixabay) |
| Voix off française | **Edge TTS** (Denise ou Henri) | gratuit, sans clé |
| Montage, sous-titres, musique | **MoneyPrinterTurbo** | gratuit |

## Mise en place (une seule fois)

### 1. Les clés API

- **Gemini** : https://aistudio.google.com/app/apikey
- **Pixabay** : crée un compte, puis va sur https://pixabay.com/api/docs/ (la clé est affichée dans la section « Parameters »)

> ⚠️ **Ne mets jamais les clés dans ce dépôt.** Elles vont dans les réglages
> de l'environnement cloud (étape 3).

### 2. Accès réseau de l'environnement cloud

Dans Claude Code (web ou appli), ouvre le menu de l'environnement cloud dans la
barre de titre de la session, puis **Edit** → **Network access**. Ajoute ces
domaines dans **Allowed domains** :

```
api.pexels.com
videos.pexels.com
pixabay.com
cdn.pixabay.com
speech.platform.bing.com
generativelanguage.googleapis.com
github.com
raw.githubusercontent.com
```

(Garde aussi la case « package managers » cochée pour que les dépendances Python s'installent.)

### 3. Les variables d'environnement

Toujours dans **Edit**, section des variables d'environnement, ajoute :

```
GEMINI_API_KEY=ta_clé_gemini
PIXABAY_API_KEY=ta_clé_pixabay
```

Les nouvelles sessions les récupèrent automatiquement.

## Utilisation

Ouvre une session Claude Code sur ce dépôt et écris simplement :

> Fais-moi une vidéo sur « 5 astuces pour mieux dormir »

Claude lit `CLAUDE.md`, installe MoneyPrinterTurbo s'il manque (quelques
minutes la première fois dans une session), génère la vidéo et te l'envoie.

### En ligne de commande

```bash
./video.sh "5 astuces pour mieux dormir"
```

Options :

```bash
VOIX=homme ./video.sh "L'histoire du café"          # voix d'homme (Henri)
FORMAT=16:9 ./video.sh "Les volcans"                # horizontal (YouTube)
FORMAT=1:1 ./video.sh "Les volcans"                 # carré
./video.sh "Les volcans" --paragraph-number 3       # script plus long (1 à 10)
./video.sh "Les volcans" --video-count 3            # 3 variantes d'un coup
./video.sh "Les volcans" --no-subtitle-enabled      # sans sous-titres
./video.sh "Les volcans" --bgm-type none            # sans musique
```

Toutes les options : `cd ~/MoneyPrinterTurbo && .venv/bin/python cli.py --help`

Les vidéos finales sont copiées dans le dossier `videos/` de ce dépôt. Ce dossier
est ignoré par git, pour ne pas alourdir le dépôt.

## Fichiers

- `setup.sh` : installe MoneyPrinterTurbo dans `~/MoneyPrinterTurbo` et écrit sa configuration à partir des variables d'environnement. Tu peux le relancer sans risque.
- `video.sh` : génère une vidéo à partir d'un sujet (lance `setup.sh` au besoin).
- `CLAUDE.md` : les instructions que Claude suit dans chaque nouvelle session.

## Dépannage

- **« Variables manquantes »** : les clés ne sont pas dans les variables d'environnement (étape 3).
- **Erreur 503 « high demand » de Gemini** : le modèle est surchargé. Réessaie plus tard ou change de modèle : `GEMINI_MODEL=gemini-3.8-flash ./video.sh "..."`.
- **Erreur réseau / 403 du proxy** : un domaine manque dans la liste de l'étape 2.
- **Pexels** : les inscriptions à l'API Pexels sont fermées, d'où l'utilisation de Pixabay à la place.
