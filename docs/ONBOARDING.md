# docflow — Guide de démarrage

> Ce guide s'adresse à une personne qui découvre docflow pour la première fois — qu'elle soit administratrice d'une nouvelle instance ou simple utilisatrice qui rejoint un workspace existant.

---

## 1. Première connexion : l'écran de bienvenue

Au tout premier démarrage d'une instance vierge, docflow affiche un **wizard de configuration initiale**. Cet écran n'apparaît qu'une seule fois.

Vous devrez saisir :
- Votre **adresse email** (qui deviendra le login administrateur)
- Un **mot de passe sécurisé** (≥ 12 caractères recommandé)

Ce compte est le compte **break-glass** : il reste toujours accessible, même si une authentification OIDC est configurée ultérieurement.

Si un compte admin existe déjà, rendez-vous directement sur la page de **connexion**.

---

## 2. Se connecter

Entrez votre email et votre mot de passe. Si l'administrateur a configuré un **SSO (Keycloak / OIDC)**, un bouton « Continuer avec votre organisation » apparaît également.

Après connexion, vous obtenez un **token JWT** (géré automatiquement par l'interface). Il expire périodiquement — la déconnexion / reconnexion est suffisante.

---

## 3. Comprendre l'organisation de docflow

```
Instance
└── Workspace (ex. "Produit 2026")
    ├── Types fonctionnels (ex. Epic, Feature, Tâche, Décision)
    │   └── Propriétés typées (ex. Statut, Priorité, Échéance)
    ├── Blocs de données (ex. "Backlog", "Sprint 12")
    │   └── Documents (pages markdown)
    │       └── Sous-documents (hiérarchie libre)
    └── Vues sauvegardées (filtres, boards)
```

**Workspace** : tout le contenu vit dans un workspace. On peut en avoir plusieurs (par équipe, par projet, par client).

**Type fonctionnel** : c'est vous qui définissez les types (`Epic`, `Feature`, `Bug`, `Décision`, `Personne`…). Rien n'est câblé. Un type peut avoir un type parent (hiérarchie d'héritage).

**Propriété** : chaque type peut avoir des propriétés typées (`text`, `int`, `date`, `bool`, `url`, `float`, `liste`, `référence vers un doc`). Le **statut** est simplement une propriété de type liste restreinte.

**Bloc de données** : un conteneur de documents à l'intérieur d'un workspace (comparable à une « base » dans Notion). Un bloc peut avoir un type fonctionnel racine.

**Document** : une page markdown avec un titre, un contenu, un type et des valeurs de propriétés. Les documents s'organisent en arbre (parent/enfant).

---

## 4. Créer un premier workspace

1. Depuis la page d'accueil, cliquez sur **« Nouveau workspace »**.
2. Donnez-lui un **nom** (le slug est généré automatiquement).
3. Cliquez sur **Créer**.

Vous êtes maintenant dans votre workspace vide.

---

## 5. Définir vos types fonctionnels

> Faites cela avant de créer des documents. C'est la configuration qui donne du sens à vos données.

1. Dans le menu gauche, cliquez sur l'icône **Types** (ou allez dans `Administration → Types`).
2. Cliquez sur **+ Nouveau type**.
3. Donnez un nom (ex. `Feature`) et optionnellement un type parent (ex. `Epic`).
4. Validez.

Répétez pour tous vos types (`Epic`, `Feature`, `Tâche`, `Décision`…).

### Ajouter des propriétés à un type

1. Cliquez sur le type créé.
2. Dans le panneau propriétés, cliquez sur **+ Ajouter une propriété**.
3. Choisissez le nom, le type de valeur, et si elle est obligatoire.
4. Pour un **statut**, choisissez le type `Liste restreinte` puis ajoutez les valeurs (`À faire`, `En cours`, `Terminé`…) dans la section « Valeurs autorisées ».

### Ajouter un template de contenu

Chaque type peut avoir un **squelette markdown** qui pré-remplit le corps d'un nouveau document de ce type :

1. Dans le type, cliquez sur `Modèle de contenu`.
2. Saisissez votre markdown de départ. Exemples de variables disponibles : `{{title}}` (titre du doc) et `{{date}}` (date du jour).

---

## 6. Créer des blocs et des documents

### Créer un bloc

Un bloc structure vos documents (ex. `Backlog`, `Sprint 12`, `Décisions Q3`) :

1. Dans le menu gauche, cliquez sur **Blocs**.
2. Cliquez sur **+ Nouveau bloc**.
3. Donnez un nom et, optionnellement, un type fonctionnel racine (les documents du bloc devront être de ce type ou d'un sous-type).

### Créer un document

1. Dans un bloc, cliquez sur **+ Nouveau document**.
2. Choisissez le type fonctionnel, donnez un titre.
3. Si le type a un template de contenu, le corps est pré-rempli automatiquement.
4. Remplissez les propriétés dans le panneau latéral (statut, date, priorité…).

### Hiérarchie de documents

Un document peut avoir des **sous-documents** (enfants). Dans l'arbre, cliquez sur le document parent puis **+ Ajouter un enfant**. La hiérarchie est libre et illimitée.

---

## 7. Éditer un document

L'éditeur est un éditeur **markdown enrichi**. Vous pouvez :

- Saisir du markdown directement.
- Utiliser les **commandes slash** (`/link`, `/heading`, `/code`…).
- Insérer un **lien vers un autre document** : tapez `/link`, cherchez le document par son titre, cliquez dessus. Le lien s'insère sous la forme `[Titre](docflow://doc/...)` et apparaît cliquable.

Les modifications sont **versionnées**. Si deux personnes modifient en même temps, un message de **conflit** apparaît avec le choix de garder votre version ou celle du serveur.

---

## 8. Naviguer et filtrer avec les vues

Les **vues sauvegardées** vous permettent de créer des requêtes nommées sur vos documents.

1. Dans le menu gauche, cliquez sur **Vues**.
2. Cliquez sur **+ Nouvelle vue**.
3. Donnez un nom, choisissez un layout (`table` ou `board kanban`).
4. Ajoutez des filtres (type, statut, date…) et un tri.
5. Pour un board, choisissez la propriété de regroupement (généralement le statut).
6. Sauvegardez. La vue est accessible depuis le menu.

Une vue peut être **partagée** (visible par tous dans le workspace) ou **privée** (visible uniquement par vous).

---

## 9. Voir qui vous cite (backlinks)

Dans le panneau d'un document, la section **« Référencé par »** liste tous les documents qui contiennent un lien vers celui que vous lisez. Cliquez sur un résultat pour naviguer vers la source.

---

## 10. Exporter vos données

Pour exporter un workspace en Markdown compatible Obsidian :

1. Allez dans la page du bloc ou du workspace.
2. Cliquez sur **Exporter (markdown)**.
3. Une archive ZIP se télécharge. Elle contient un dossier par bloc, avec un fichier `.md` par document et un frontmatter YAML contenant toutes les propriétés.

L'archive s'ouvre directement comme **vault Obsidian**.

---

## 11. Administration (pour les administrateurs)

### Gérer les utilisateurs

Menu `Administration → Utilisateurs` : créer, modifier, désactiver des comptes. Le compte bootstrap ne peut jamais être désactivé.

### Configurer le SSO

Menu `Administration → OIDC` : saisir l'issuer, le client ID et le secret (stocké dans le coffre-fort, jamais en clair).

### Coffre de secrets

Menu `Administration → Vault` : connecter un wallet **Harpocrate** ou créer des secrets locaux. Les références `${vault://...}` sont utilisées dans les headers d'automates et la configuration OIDC.

### Webhooks et automates

- **Webhooks** (`Administration → Webhooks`) : notifier un système externe quand un document est créé/modifié/supprimé.
- **Automates** (`Administration → Automates`) : appels HTTP déclenchés par le journal des changements (garantie de livraison, supporte les débounces). Cas d'usage : réindexation dans un moteur de recherche.

### Templates de workspace

Menu `Administration → Templates` : importer un template de structure qui pré-crée des types fonctionnels, des propriétés et des blocs dans un workspace.

---

## 12. Raccourcis utiles

| Action | Raccourci / chemin |
|--------|--------------------|
| Nouvelle vue | Menu `Vues` → `+ Nouvelle vue` |
| Lien vers un doc dans l'éditeur | Taper `/link` dans le corps |
| Export markdown | Page du bloc → bouton `Exporter` |
| Voir les backlinks | Panneau latéral du document → section `Référencé par` |
| Résoudre un conflit | Bandeau orange en bas de l'éditeur → `Garder la mienne` / `Prendre la serveur` |

---

## 13. Concepts clés à retenir

| Concept | Ce que c'est |
|---------|-------------|
| **Slug** | Identifiant stable (URL-safe). Immuable une fois créé. |
| **Type fonctionnel** | Catégorie de document définie par vous. Pas de types câblés. |
| **Statut** | Une propriété `liste restreinte`. Vous définissez les valeurs. |
| **Bloc** | Conteneur de documents dans un workspace. |
| **Version** | Chaque modification est numérotée (OCC). Conflits = résolvables. |
| **Référence** | Propriété qui pointe un autre document (typée, validée à l'écriture). |
| **Lien de contenu** | `[Titre](docflow://doc/...)` dans le markdown — souple, FK molle. |
| **Backlink** | Tout document qui vous cite (visible dans le panneau). |
| **Vault** | Coffre de secrets — les tokens ne sont jamais stockés en clair. |

---

*Besoin d'aller plus loin ? Consultez [FONCTIONNALITES.md](FONCTIONNALITES.md) pour la documentation complète des fonctionnalités.*
