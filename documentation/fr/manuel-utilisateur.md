# Manuel utilisateur — docflow

## Sommaire

1. [Connexion](#1-connexion)
2. [Workspaces](#2-workspaces)
3. [Documents](#3-documents)
4. [Types fonctionnels](#4-types-fonctionnels)
5. [Blocs de données](#5-blocs-de-données)
6. [Templates](#6-templates)
7. [Webhooks](#7-webhooks)
8. [Automates](#8-automates)
9. [Vault (secrets)](#9-vault-secrets)
10. [Authentification OIDC](#10-authentification-oidc)
11. [Documents publics](#11-documents-publics)

---

## 1. Connexion

### Compte local (admin bootstrap)

Saisir l'adresse email et le mot de passe configurés lors de l'installation. Ce compte est toujours disponible, même si l'authentification OIDC est activée — c'est le compte de secours.

### Connexion OIDC (Keycloak)

Si un administrateur a configuré OIDC, un bouton « Se connecter avec Keycloak » apparaît sur la page de login. Cliquer dessus redirige vers Keycloak. À la première connexion, le compte est créé automatiquement dans docflow.

---

## 2. Workspaces

Un workspace est un espace de travail isolé. Les documents, types, blocs et automates d'un workspace sont invisibles depuis un autre.

### Créer un workspace

Depuis la page d'accueil, cliquer sur **« Nouveau workspace »**, saisir un nom et un slug (identifiant URL, lettres minuscules et tirets uniquement).

### Naviguer entre workspaces

La liste des workspaces apparaît sur la page d'accueil. Cliquer sur un workspace ouvre sa vue principale.

---

## 3. Documents

### Arborescence

La vue principale d'un workspace affiche l'arbre des documents dans le panneau de gauche. Les documents peuvent être imbriqués librement (un document peut avoir des sous-documents).

**Créer un document**

- Cliquer sur **« + »** à côté d'un document existant pour créer un enfant.
- Saisir le titre puis appuyer sur **Entrée** pour valider.

**Déplacer / réorganiser**

Utiliser le drag-and-drop dans l'arborescence pour changer la hiérarchie ou l'ordre.

### Éditeur de document

Cliquer sur un document ouvre l'éditeur. Il contient deux zones :

- **Zone de texte** (gauche) : contenu en Markdown. Syntaxe complète supportée (titres, listes, tableaux, liens, code, etc.).
- **Panneau de propriétés** (droite) : type fonctionnel, statut et propriétés personnalisées du document.

**Mode rédaction (plein écran)**

Cliquer sur l'icône de plein écran en haut à droite de l'éditeur pour masquer le panneau de propriétés et écrire sans distraction. Appuyer sur **Échap** pour quitter ce mode.

**Liens inter-documents**

Dans l'éditeur, saisir `[[` pour ouvrir le sélecteur de liens. Il permet de créer un lien Markdown vers n'importe quel document du workspace ou d'un autre workspace.

### Propriétés

Chaque document peut avoir un **type fonctionnel** (ex. Epic, Feature, Bug) qui définit un ensemble de propriétés. Depuis le panneau de droite :

- Sélectionner le type fonctionnel dans la liste déroulante.
- Remplir les propriétés qui apparaissent (texte, nombre, liste restreinte).
- Le **statut** est une propriété spéciale affichée en haut du panneau.

### Recherche

La barre de recherche en haut de l'arborescence permet de chercher des documents par titre dans le workspace courant.

---

## 4. Types fonctionnels

Accessible depuis **Types** dans la barre latérale.

Un type fonctionnel est un modèle de document (ex. Tâche, Epic, Décision). Il définit les propriétés disponibles sur les documents de ce type.

### Créer un type

Cliquer sur **« + Nouveau type »**, saisir un libellé et un slug. Le slug est l'identifiant stable (immuable une fois créé).

### Hiérarchie de types

Un type peut avoir un type parent (ex. Feature est un enfant d'Epic). Sélectionner le parent lors de la création ou de la modification.

### Propriétés d'un type

Sélectionner un type dans la liste pour voir et modifier ses propriétés.

**Ajouter une propriété**

Cliquer sur **« + Propriété »** et choisir :
- **Texte** : champ texte libre.
- **Entier** : nombre entier.
- **Liste restreinte** : l'utilisateur choisit parmi une liste de valeurs prédéfinies.

Pour une liste restreinte, cliquer sur la propriété pour ajouter les valeurs autorisées (chacune avec un slug stable, un libellé et un ordre).

**Statut**

Le statut d'un document est une propriété de type liste restreinte marquée comme « statut ». Cocher **« Utiliser comme statut »** lors de la création de la propriété.

### Contraintes de type

Une contrainte restreint les types de documents autorisés à l'intérieur d'un bloc de données. Se configure dans la section **Contraintes** du type.

---

## 5. Blocs de données

Accessible depuis **Blocs** dans la barre latérale.

Un bloc de données est un conteneur structuré de documents partageant tous le même type fonctionnel. Il est utile pour organiser des listes homogènes (backlog, registre de décisions, etc.).

### Créer un bloc

Cliquer sur **« + Nouveau bloc »**, saisir un nom. Optionnellement restreindre aux types autorisés.

### Ajouter des documents à un bloc

Ouvrir un bloc, cliquer sur **« + Document »**. Le document est créé avec le type imposé par le bloc.

### Exposition publique

Un bloc peut être exposé en lecture seule sans authentification. Activer **« Exposé publiquement »** sur le bloc pour obtenir une URL d'accès public.

---

## 6. Templates

Accessible depuis **Templates** dans la barre latérale.

Un template est un document modèle que l'on peut instancier pour pré-remplir le contenu d'un nouveau document. Créer un template comme un document normal, puis le marquer comme template.

---

## 7. Webhooks

Accessible depuis **Webhooks** dans la barre latérale.

Les webhooks permettent d'envoyer une requête HTTP vers une URL externe à chaque modification de document dans le workspace.

### Créer un webhook

Cliquer sur **« + Webhook »** :
- **URL** : endpoint de destination.
- **Actif** : activer/désactiver sans supprimer.
- **Headers** : ajouter des headers HTTP (ex. `Authorization`). La valeur peut être saisie en clair ou référencer un secret Harpocrate sous la forme `${vault://wallet:/chemin}`.

### Événements

Un webhook se déclenche sur les événements de modification de documents (création, mise à jour de contenu ou de propriétés).

---

## 8. Automates

Accessible depuis **Automates** (icône ⚡) dans la barre latérale.

Les automates permettent d'appeler une API externe automatiquement lorsqu'un document est créé ou modifié. La page est divisée en deux sections : **Contrats** et **Automates**.

### Contrats OpenAPI

Un contrat est une spécification OpenAPI importée qui décrit une API externe. Il permet à docflow de proposer les opérations disponibles lors de la configuration d'un automate.

**Importer un contrat**

Deux méthodes :
- **Par URL** : saisir l'URL du fichier OpenAPI (JSON ou YAML), cliquer sur **Importer**.
- **Par collage** : coller directement le JSON de la spec, cliquer sur **Importer**.

**Actualiser un contrat**

Cliquer sur **Actualiser** pour re-télécharger la spec depuis son URL d'origine.

### Créer un automate

Cliquer sur **« + Automate »** :

| Champ | Description |
|---|---|
| **Libellé** | Nom de l'automate |
| **Actif** | Activer/désactiver l'automate |
| **À la création** | Se déclenche lors de la création d'un document |
| **À la modification** | Se déclenche lors de la modification d'un document |
| **Délai débounce** | Attendre N minutes après la dernière modification avant d'exécuter (évite les appels répétés lors d'une rédaction active) |
| **Contrat OpenAPI** | Optionnel — sélectionner un contrat pour parcourir ses opérations |
| **Opération** | Optionnel — sélectionner une opération pour pré-remplir méthode et corps |
| **URL** | URL complète de l'endpoint |
| **Méthode** | GET / POST / PUT / PATCH / DELETE |
| **Corps (JSON)** | Corps de la requête en JSON avec variables substituables |
| **Headers** | Headers HTTP additionnels (valeur en clair ou `${vault://…}`) |

**Variables disponibles dans le corps**

Cliquer sur les boutons de variable pour les insérer dans le JSON :

- `{id_document}` — identifiant UUID du document
- `{title}` — titre du document
- `{content}` — contenu Markdown du document

Les valeurs sont automatiquement échappées pour produire un JSON valide.

### Historique des exécutions

Cliquer sur le nom d'un automate pour voir son historique d'exécutions : document concerné, version, statut (`pending` / `ok` / `failed`), date.

**Rejouer une exécution**

Pour une exécution en échec, cliquer sur **Rejouer** pour la relancer immédiatement.

---

## 9. Vault (secrets)

Accessible depuis **Vault** dans la barre latérale.

Le vault permet de stocker des secrets (tokens API, mots de passe) de façon sécurisée, utilisables dans les headers de webhooks et d'automates.

### Wallets Harpocrate

Un wallet est une connexion à un vault Harpocrate distant. Configurer :
- **Nom** : identifiant du wallet (utilisé dans `${vault://nom:/…}`)
- **URL Harpocrate** : URL du service
- **Token API** : token Bearer (`hrpv_…`) pour s'authentifier

Les tokens sont chiffrés en base de données (clé `ENCRYPTION_KEY`).

### Secrets locaux

Les secrets locaux sont des paires clé/valeur stockées chiffrées en base. Ils peuvent être référencés par leur chemin dans les headers de webhook ou d'automate sous la forme `${vault://wallet:/chemin}`.

---

## 10. Authentification OIDC

Accessible depuis **OIDC** dans la barre latérale (admin uniquement).

Configurer l'authentification déléguée à Keycloak :

| Champ | Valeur |
|---|---|
| **Issuer URL** | URL du realm Keycloak (ex. `https://security.yoops.org/realms/yoops`) |
| **Client ID** | Identifiant du client déclaré dans Keycloak (ex. `docflow`) |
| **Client secret** | Secret du client — peut être saisi en clair ou sous forme `${vault://…}` |

Une fois configuré, le bouton OIDC apparaît sur la page de login. Les utilisateurs Keycloak sont créés automatiquement à la première connexion.

> Le compte admin bootstrap reste toujours actif, même avec OIDC configuré.

---

## 11. Documents publics

Un document ou un bloc peut être exposé en lecture seule sans authentification.

**Activer l'exposition**

Dans l'éditeur de document ou la vue d'un bloc, activer **« Exposé publiquement »**. Une URL publique est alors disponible, accessible sans connexion.

L'URL publique suit le format :
```
https://<domaine>/public/documents/<id>
https://<domaine>/public/blocks/<id>
```
