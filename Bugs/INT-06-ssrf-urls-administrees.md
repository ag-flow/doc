# INT-06 — SSRF via URLs administrées (webhooks/automations/contracts/galerie)

- **Gravité** : 🟡 MINEUR (durcissement)
- **Confiance** : moyenne
- **Zone** : intégrations / sortie réseau
- **Fichiers** : `webhooks/service.py` (emit/test) ; `automations/worker.py` (execute) ; `contracts/service.py:184` (refresh) ; `templates/gallery.py` (fetch/pull, `_fetch` avec `follow_redirects=True` l.33)

## Description

Plusieurs fetch serveur visent des URLs **arbitraires** fournies par un admin, potentiellement vers le réseau interne (métadonnées cloud, services internes). `gallery._fetch` suit en plus les redirections. Les timeouts sont présents partout (bon point). L'exposition dépend de [AUTH-07](AUTH-07-require-admin-ne-verifie-pas-is-admin.md) (`require_admin` = tout utilisateur validé).

## Scénario de reproduction

Un utilisateur ayant accès aux surfaces `require_admin` configure un webhook/automation/source de galerie pointant sur `http://169.254.169.254/…` ou un service interne, et observe la réponse via un test/refresh.

## Impact

Exfiltration de ressources internes / scan du réseau interne depuis le serveur.

## Piste de correction

Liste d'autorisation d'hôtes ou blocage des plages privées/loopback/link-local ; restreindre `follow_redirects` et re-valider l'hôte après redirection.
