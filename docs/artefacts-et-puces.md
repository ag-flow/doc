# Artefacts & puces de fichier

> À publier dans le bloc **Documentation** de docflow (section « 5 — Référence
> API & MCP »). Décrit le cycle de vie d'un artefact et son insertion dans un
> document, côté agent (MCP) comme côté REST.

## Concept

Un **artefact** est un fichier binaire stocké dans un workspace (image, PDF,
audio, archive, document Office…). Il est :

- **dédupliqué** par empreinte sha256 : pousser deux fois le même contenu
  retourne le même `id` (`deduplicated: true`) ;
- **rattaché par référence** : un artefact non référencé par un document
  enregistré est **purgé automatiquement** après quelques heures ;
- **isolé par workspace** : jamais servi hors de son workspace (sauf lien signé
  ou document exposé).

Extensions acceptées : images (`png, jpg, jpeg, gif, webp, svg`), documents
(`pdf, txt, md, csv, json, docx, xlsx, pptx`), audio (`mp3, wav, m4a, ogg`),
vidéo (`mp4, webm`), archives (`zip`). Le type `text/html` est **exclu**
(un binaire servi depuis notre origine serait un vecteur XSS) ; tout est servi
avec l'en-tête `nosniff`.

## Insertion dans un document

Deux formes, selon le type :

| Type | Forme markdown | Rendu |
|------|----------------|-------|
| Image | `![nom](url)` | image inline |
| Tout autre fichier | `[libellé](artifact://<uuid>)` **seul sur sa ligne** | puce téléchargeable |

La **puce** affiche icône (selon le type), nom, extension, taille lisible, et
deux actions : **Télécharger** (téléchargement authentifié) et **Ouvrir** (lien
signé de courte durée, nouvel onglet). Un **libellé vide** retombe sur le nom de
fichier :

```
[](artifact://550e8400-e29b-41d4-a716-446655440000)
```

Le même lien `artifact://` **au fil du texte** (pas seul sur sa ligne) reste un
**lien cliquable** — il n'est pas transformé en puce. La distinction est
purement positionnelle.

## Côté agent (MCP)

Ordre typique :

1. **`create_artifact`** — pousser le binaire par `data_base64` (inline) **ou**
   `source_url` (URL publique que le serveur télécharge lui-même — à préférer
   pour un gros fichier, les octets ne transitent pas par la conversation).
   Retourne `{id, url, deduplicated, media_type, size_bytes, sha256}`.
2. **`update_document`** (ou `create_document`) — insérer dans le contenu
   `![nom](url)` (image) ou `[libellé](artifact://id)` seul sur sa ligne (puce).
3. **`list_artifacts`** — lister les artefacts d'un workspace, paginé
   (`limit` 1..200, `offset`), du plus récent au plus ancien :
   `{items:[{id, filename, media_type, size_bytes, extension, created_at,
   refcount}], total, limit, offset}`.
4. **`get_artifact`** — métadonnées d'un artefact (dont `refcount`).
5. **`get_artifact_link`** — lien de téléchargement signé (HMAC, expiration),
   utilisable sans authentification jusqu'à expiration.

## Côté REST

- `POST /api/workspaces/{ws}/artifacts` — upload multipart (`file`). Champs
  `filename` et `media_type` optionnels (surcharges ; `media_type` borné à la
  whitelist). Retourne l'artefact créé.
- `GET /api/workspaces/{ws}/artifacts/{id}` — contenu inline ;
  `?disposition=attachment` force le téléchargement.
- `GET /api/workspaces/{ws}/artifacts/{id}/meta` — métadonnées.
- `GET /api/workspaces/{ws}/artifacts/{id}/link` — lien signé court
  `{url, expires_in_seconds}` (exploitable sans Bearer).
- `POST /api/workspaces/{ws}/documents/{id}/append` — `{content, position}`
  (`top`|`bottom`) : ajoute un fragment markdown au bord du document
  (positionnement **littéral**), pratique pour attacher une puce.

Exemple de bout en bout : `docs/examples/pipeline_artefact.sh`.

## Évolutions

- La whitelist d'extensions est la frontière de sécurité : l'étendre à un
  nouveau type se fait dans `backend/src/docflow/artifacts/service.py`
  (`ALLOWED_MEDIA_TYPES`) — jamais un type actif servi depuis notre origine.
- Le déclenchement automatique d'un pipeline artefact (règle sur événement)
  vit dans **ag.flow**, hors de ce dépôt.
