# INT-02 — Debounce d'automation : famine de tout le workspace
> ✅ **CORRIGÉ** le 2026-07-04 par agent autonome Opus.

- **Gravité** : 🟠 MAJEUR (logique)
- **Confiance** : haute
- **Zone** : intégrations / automations
- **Fichiers** : `backend/src/docflow/automations/worker.py:206-218`

## Description

Quand un document est « chaud » (une entrée `document_change_log` dans les `delay_minutes`), le code fait `break` sur la boucle des changements. Comme les `rows` sont triées par `seq` sur **tout le workspace** et que le curseur n'est pas avancé, on interrompt le traitement de **tous** les changements suivants du batch, y compris ceux d'autres documents non concernés par le délai.

## Scénario de reproduction

1. Document A édité en continu (toujours « chaud »).
2. Document B (seq plus élevé) modifié une fois.
3. À chaque tick, le worker atteint A, `break`, et ne traite **jamais** B tant que A n'est pas refroidi.

## Impact

Un seul document fréquemment modifié gèle les automations de l'ensemble du workspace (famine).

## Piste de correction

Ne pas `break` ; sauter le document chaud sans avancer le curseur au-delà de lui (traiter les changements par document, ou maintenir un curseur « min unprocessed » plutôt qu'un `break` global).
