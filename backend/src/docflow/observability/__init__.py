"""Observabilité — traçabilité du contexte (STANDARD « Traçabilité du contexte »).

Fondation locale du contrat de corrélation v1 : contexte ambiant, contrat de
champs figé (`agflow.*`), propagation W3C (traceparent + baggage) via
`opentelemetry-api`. Aucun exporteur ni tracer ici : l'émission OTLP réelle
(spans, span link, capture payload) est un lot ultérieur gaté sur l'infra Alloy.
"""

from __future__ import annotations
