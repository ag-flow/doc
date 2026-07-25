# MBC — Registre de codecs de blocs custom

**Objectif.** Remplacer le chaînage codé en dur des blocs custom (`mermaid`, `dataset`) par un **registre déclaratif** : un composant = une entrée + un renderer. Aucun changement fonctionnel. Prérequis impératif de `40_MCMP`.

**Dépend de.** `24_MUI1` (éditeur BlockNote), `22_MDB` (bloc dataset).

## Pourquoi (constat)

Trois points de couplage dans l'état actuel :

1. **`lib/mermaidMarkdown.ts`** — une regex de fence, un placeholder et un couple parse/serialize dédiés au seul type `mermaid`.
2. **`lib/datasetMarkdown.ts`** — n'étend pas le précédent, il l'**enveloppe** : il remplace ses jetons `dataset://<uuid>` par un placeholder, délègue à `parseMarkdownWithMermaid`, puis réinjecte. La sérialisation est une chaîne `if (type === 'mermaid') … else if (type === 'dataset') … else …`.
3. **`MarkdownEditor.tsx`** — `blockSpecs` littéral et items de menu slash déclarés à la main.

Conséquences si on ajoute N composants par ce chemin :

- **Empilement.** Le Nième codec enveloppe le N−1ième. La profondeur d'appel croît avec le nombre de composants.
- **Ordre significatif.** Chaque codec fait une passe `.replace()` complète sur le markdown. L'ordre des passes devient un contrat implicite, jamais testé.
- **Collision de placeholders.** Un placeholder littéral par codec, dans un espace de noms non réservé. Un document contenant `%%DATASET_PLACEHOLDER%%` en clair corrompt le parsing.
- **Point de couplage unique.** Le sérialiseur doit connaître tous les types. Un oubli n'échoue pas : BlockNote sérialise un bloc custom inconnu **en vide**. Le mode de panne est donc la **perte silencieuse de contenu**, pas l'erreur.

Le dernier point suffit à justifier le lot. À deux composants le refactor est mécanique ; à six c'est un chantier. On le fait avant d'ajouter le troisième.

## Cible

### Le contrat

```ts
export interface BlockCodec<P = Record<string, unknown>> {
  /** Type du bloc BlockNote. Unique dans le registre. */
  type: string
  /** Détection dans le markdown. Regex globale. */
  pattern: RegExp
  /** Match markdown → props du bloc. `null` = match écarté. */
  toBlock: (match: RegExpExecArray) => P | null
  /** Props → markdown canonique. Doit être stable en round-trip. */
  toMarkdown: (props: P) => string
  /** Le composant BlockNote (`createReactBlockSpec`). */
  spec: () => BlockSpec
  /** Entrée du menu `/`. Absente pour un codec legacy. */
  slashItem?: (ctx: SlashContext) => SlashItem
  /** Reconnu en lecture/écriture mais non proposé à l'insertion. */
  legacy?: boolean
}
```

### Passe de parsing — une seule, ordonnée par position

1. Pour chaque codec, `matchAll(pattern)` → collecter `{ start, end, codec, match }`.
2. Trier par `start` croissant. Écarter tout match qui **chevauche** un match déjà retenu (le premier gagne), avec journalisation.
3. Reconstruire le markdown en une passe, chaque match remplacé par un placeholder indexé.
4. `tryParseMarkdownToBlocks` sur le résultat.
5. Réinjecter : chaque placeholder retrouvé → `{ type, props }` du codec correspondant.

Gains : plus d'ordre implicite entre codecs, un seul espace de placeholders, chevauchements détectés au lieu d'être subis.

**Placeholder.** Motif `%%DF_<nonce>_<i>%%`, le `nonce` étant tiré aléatoirement **à chaque parsing**. Aucun échappement du contenu utilisateur n'est alors nécessaire, et aucune séquence littérale du document ne peut entrer en collision.

**La technique du placeholder reste nécessaire** : BlockNote 0.51 n'expose pas de hook de parsing markdown par bloc custom (cf. commentaire en place dans `mermaidMarkdown.ts`). Le registre ne la supprime pas, il la centralise et la rend testable une fois pour toutes.

### Sérialisation

Lookup par type : `codecs.get(block.type)?.toMarkdown(props)`, sinon `blocksToMarkdownLossy`.

**Garde-fou anti-perte** : si `block.type` n'est ni un type BlockNote par défaut ni un codec enregistré, ne pas produire de vide — journaliser en erreur et **faire échouer la sauvegarde** avec un message explicite. Perdre du contenu sans le dire est interdit.

### Schéma et menu dérivés

```ts
const schema = BlockNoteSchema.create({
  blockSpecs: { ...defaultBlockSpecs, ...specsFromRegistry(registry) },
})
const slashItems = registry.filter((c) => c.slashItem).map((c) => c.slashItem!(ctx))
```

### Arborescence

```
lib/blockCodecs/
  index.ts        registre + parse/serialize génériques + docflowSchema exporté
  mermaid.ts      codec existant, migré
  dataset.ts      codec existant, migré (jeton dataset://<uuid>, legacy)
```

`lib/mermaidMarkdown.ts` et `lib/datasetMarkdown.ts` sont supprimés ; leurs tests migrent.

### Chemin lecture — état vérifié

Le rendu en lecture seule consomme **le même registre**. Vérification faite sur les trois surfaces : `PublicDocumentViewer` utilise directement `MarkdownViewer`, et `DocumentReader` l'enveloppe (`bare`). Il n'existe **aucune troisième voie de rendu** — tout le chemin lecture passe par `MarkdownViewer`.

Conséquence directe : le `schema` et l'appel de parsing sont aujourd'hui **dupliqués verbatim** entre `MarkdownEditor.tsx` et `MarkdownViewer.tsx` (mêmes `blockSpecs`, même `parseMarkdownWithBlocks`) — deux copies à garder synchrones à la main, exactement le défaut que le registre supprime. La cible : un `docflowSchema` unique exporté depuis `lib/blockCodecs/`, importé par les deux. Câbler ces **deux fichiers** couvre tout le périmètre de rendu, lecture publique comprise. `DocumentReader` et `PublicDocumentViewer` n'ont pas à être touchés.

## Points d'attention

- **Round-trip.** `markdown → blocs → markdown` doit être idempotent pour chaque codec. Test **paramétré sur le registre**, pas écrit codec par codec — sinon le prochain composant arrivera sans test.
- **Rétrocompatibilité.** `dataset://<uuid>` est du contenu déjà en base. Il reste supporté tel quel, en codec `legacy` sans item de menu. **Aucune migration de contenu.**
- **Fence inconnue.** Un document produit par un agent avec un type non encore enregistré doit rester un bloc de code intact. Aucune fence n'est consommée si aucun codec ne la revendique.
- **Rendu SVG hors session.** `PublicDocumentViewer` exécute le rendu des blocs custom côté client, sans authentification (déjà le cas pour mermaid). Tout nouveau codec doit rendre sans appel réseau authentifié — contrainte à garder en tête pour `40_MCMP` (SVG maison, pas de fetch de données au rendu).
- **Périmètre.** Ce lot ne modifie ni le rendu ni le markdown produit. Sur un document existant, le diff attendu après load + save est **vide**.

## Tâches

- [ ] `lib/blockCodecs/index.ts` : interface `BlockCodec`, registre, `parseMarkdownWithCodecs`, `serializeMarkdownWithCodecs` (nonce, tri par position, détection de chevauchement, garde anti-perte), et `docflowSchema` exporté.
- [ ] Migrer `mermaid` en codec ; supprimer `lib/mermaidMarkdown.ts`.
- [ ] Migrer `dataset` en codec `legacy` ; supprimer `lib/datasetMarkdown.ts`.
- [ ] `MarkdownEditor.tsx` : schéma et items slash dérivés du registre.
- [ ] `MarkdownViewer.tsx` : importer `docflowSchema` et le parsing du registre (supprime la copie dupliquée) ; couvre `DocumentReader` et `PublicDocumentViewer` par transitivité.
- [ ] Tests Vitest : round-trip paramétré sur le registre ; chevauchement ; fence inconnue préservée ; bloc non enregistré → erreur de sauvegarde et non perte.
- [ ] Test de non-régression : charger puis sauver un document contenant mermaid + dataset → markdown identique au caractère près.

## Definition of Done

1. `npm run build` (tsc strict) + Vitest verts.
2. Un document existant contenant un diagramme mermaid et un dataset, ouvert puis enregistré sans modification, produit un markdown **identique** à l'original — vérifié à l'édition **et** via `MarkdownViewer`.
3. Ajouter un composant fictif au registre ne touche **que** son propre fichier plus une ligne d'import — ni `MarkdownEditor.tsx`, ni `MarkdownViewer.tsx`, ni le parseur, ni le sérialiseur.
4. Un bloc de code ` ```inconnu ` traverse le round-trip sans altération.
5. `MarkdownEditor` et `MarkdownViewer` importent le **même** `docflowSchema` — plus aucune définition de `blockSpecs` dupliquée dans l'arbre.
6. Context7 consulté pour BlockNote 0.51 (`blockSpecs`, parsing markdown) avant code.

## Notes

- Le point 3 de la DoD est le critère réel de réussite : c'est lui qui rend `40_MCMP` parallélisable.
- Aucun impact backend. Le markdown reste la source de vérité, `21_RW` inchangé.
