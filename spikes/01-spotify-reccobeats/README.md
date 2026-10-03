# Tests de faisabilité — plateforme DJ

Deux scripts jetables pour valider les hypothèses du plan avant d'écrire le vrai code.

| Test | Question | Bloquant si KO ? |
|---|---|---|
| `spike_spotify.py` | L'API Spotify (mode dev) permet-elle de lire mes playlists et d'en **créer** ? | Oui : l'export vers rekordbox repose dessus |
| `spike_reccobeats.py` | ReccoBeats connaît-il mes morceaux, et ses BPM/tonalités sont-ils justes ? | Oui : toute la logique de suggestion en dépend |

## 0. Préparer l'application Spotify (5 min)

1. Va sur https://developer.spotify.com/dashboard et connecte-toi (compte **Premium** obligatoire).
2. *Create app* :
   - Nom : ce que tu veux
   - Redirect URI : `http://127.0.0.1:8888/callback` (exactement ; `localhost` est refusé par Spotify)
   - API utilisée : **Web API**
3. Copie le **Client ID** (pas besoin du secret : on utilise PKCE).

## 1. Construire l'image

```bash
cd spikes
DOCKER_BUILDKIT=0 docker build -t dj-spikes .
mkdir -p data
```

## 2. Test Spotify

```bash
docker run --rm -it -v "$PWD/data:/app/data" -e SPOTIFY_CLIENT_ID=TON_CLIENT_ID \
  dj-spikes python spike_spotify.py
```

Le script affiche une URL : ouvre-la, accepte, puis colle l'URL de la page (qui ne charge pas) dans le terminal.
Choisis ensuite une **playlist DJ** à toi.

À vérifier après coup : la playlist `[TEST plateforme DJ] ...` apparaît-elle dans rekordbox ? (Tu peux la supprimer ensuite.)

## 3. Exporter ta collection rekordbox (pour mesurer la précision)

Dans rekordbox : *Fichier > Exporter la collection au format XML*, enregistre-le dans `spikes/data/rekordbox.xml`.

Ouvre-le dans un éditeur et cherche un morceau Spotify : note ce que contient l'attribut `Location`. C'est la réponse à la question « que contient l'XML pour un morceau en streaming ? ».

## 4. Test ReccoBeats

```bash
docker run --rm -it -v "$PWD/data:/app/data" dj-spikes \
  python spike_reccobeats.py --rekordbox data/rekordbox.xml
```

Sans XML rekordbox, retire `--rekordbox ...` : tu n'auras que la couverture.

Résultat : bilan dans le terminal + `data/reccobeats.csv` (une ligne par morceau).

## Grille de décision

| Résultat | Conclusion |
|---|---|
| E (création de playlist) OK + visible dans rekordbox | Export Spotify → rekordbox validé |
| E KO | Export en M3U/XML seulement ; on revoit le flux |
| Couverture ReccoBeats ≥ 80 % et tonalité « identique » ≥ 70 % | ReccoBeats suffit pour la V1 |
| Couverture faible ou tonalités souvent fausses | Les valeurs rekordbox deviennent la source principale, l'analyse maison (Essentia) remonte en priorité |

Note : `data/` contient ton jeton Spotify, ne le commite pas.
