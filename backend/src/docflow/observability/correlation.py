"""Contrat de corrélation v1 (STANDARD « Traçabilité du contexte »).

Deux objets distincts, jamais confondus :
  - la **trace** W3C (`traceparent`/`tracestate`) : unité courte, synchrone ;
  - la **corrélation métier** (`agflow.*` en baggage) : le fil long, opaque,
    stable de bout en bout, qui ne se réécrit jamais en cours de route.

Ce module ne fait que porter et propager ce contexte : pas de tracer, pas
d'exporteur (lot B). Les propagateurs W3C viennent d'`opentelemetry-api` — on
instrumente au standard, pas avec un format maison.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from contextvars import ContextVar, Token
from dataclasses import dataclass, replace
from typing import Literal

import structlog
from opentelemetry import baggage
from opentelemetry.baggage.propagation import W3CBaggagePropagator
from opentelemetry.context import Context

CorrelationKind = Literal["workflow_instance", "a2a_task", "document", "index_job"]

# `origin` de docflow dans le contrat (module qui crée le fil).
ORIGIN_DOC = "doc"

# Clés de baggage du contrat v1 — FIGÉES. Un champ ajouté = une v2, jamais une
# extension silencieuse (STANDARD §2).
_K_ORIGIN = "agflow.origin"
_K_ID = "agflow.correlation_id"
_K_KIND = "agflow.correlation_kind"
_K_STEP = "agflow.step"
_K_ACTOR = "agflow.actor_guid"

_H_TRACEPARENT = "traceparent"
_H_TRACESTATE = "tracestate"

_baggage_propagator = W3CBaggagePropagator()


@dataclass(frozen=True)
class CorrelationContext:
    """Le contexte de corrélation v1, immuable (le `correlation_id` ne se réécrit
    jamais ; `with_step` produit une copie, il ne mute pas l'existant)."""

    origin: str
    correlation_id: str
    correlation_kind: str
    step: str | None = None
    actor_guid: str | None = None
    # Relais OPAQUE du contexte de trace W3C entrant — transporté tel quel vers
    # une cible interne, jamais interprété ni réécrit.
    traceparent: str | None = None
    tracestate: str | None = None
    # Référence de trace d'un appelant EXTERNE : conservée en attribut pour
    # l'observabilité, jamais promue en parenté de span (STANDARD §4).
    peer_trace_ref: str | None = None

    def with_step(self, step: str) -> CorrelationContext:
        return replace(self, step=step)


# ── Contexte ambiant (contextvar) ─────────────────────────────────────────────

_current: ContextVar[CorrelationContext | None] = ContextVar("docflow_correlation", default=None)


def current() -> CorrelationContext | None:
    """Contexte de corrélation courant, ou None hors d'un fil établi."""
    return _current.get()


def bind(ctx: CorrelationContext) -> Token[CorrelationContext | None]:
    """Établit le contexte ambiant ET l'expose aux logs structlog.

    Le pipeline structlog a déjà `merge_contextvars` : lier ici fait remonter
    `correlation_id`/`correlation_kind`/`origin` dans chaque log JSON du fil.
    """
    structlog.contextvars.bind_contextvars(
        correlation_id=ctx.correlation_id,
        correlation_kind=ctx.correlation_kind,
        origin=ctx.origin,
    )
    return _current.set(ctx)


def reset(token: Token[CorrelationContext | None]) -> None:
    """Restaure le contexte précédent et retire les clés de log liées."""
    _current.reset(token)
    structlog.contextvars.unbind_contextvars("correlation_id", "correlation_kind", "origin")


# ── Naissance d'un fil ────────────────────────────────────────────────────────


def _opaque_id() -> str:
    """Identifiant de fil OPAQUE (uuid4). Jamais dérivé d'un titre/slug."""
    return uuid.uuid4().hex


def new_context(
    kind: CorrelationKind,
    *,
    origin: str = ORIGIN_DOC,
    correlation_id: str | None = None,
    step: str | None = None,
    actor_guid: str | None = None,
) -> CorrelationContext:
    """Nouveau fil, `correlation_id` opaque généré si non fourni."""
    return CorrelationContext(
        origin=origin,
        correlation_id=correlation_id or _opaque_id(),
        correlation_kind=kind,
        step=step,
        actor_guid=actor_guid,
    )


def new_document_context(
    document_key: uuid.UUID,
    *,
    step: str | None = None,
    actor_guid: str | None = None,
) -> CorrelationContext:
    """Fil né d'une mutation de document sans déclencheur amont.

    `correlation_id` = clé technique du document : un UUID est OPAQUE et stable
    pour toute la vie du fil du document. On n'y met JAMAIS le titre ni le slug
    (le baggage voyage en clair et traverse des frontières — STANDARD §2).
    """
    return CorrelationContext(
        origin=ORIGIN_DOC,
        correlation_id=str(document_key),
        correlation_kind="document",
        step=step,
        actor_guid=actor_guid,
    )


# ── Sérialisation / extraction W3C ────────────────────────────────────────────


def _opt(value: object) -> str | None:
    s = str(value) if value is not None else ""
    return s or None


def to_baggage_headers(ctx: CorrelationContext) -> dict[str, str]:
    """Encode les champs `agflow.*` en en-tête `baggage` W3C (sans traceparent)."""
    context: Context = Context()
    context = baggage.set_baggage(_K_ORIGIN, ctx.origin, context=context)
    context = baggage.set_baggage(_K_ID, ctx.correlation_id, context=context)
    context = baggage.set_baggage(_K_KIND, ctx.correlation_kind, context=context)
    if ctx.step:
        context = baggage.set_baggage(_K_STEP, ctx.step, context=context)
    if ctx.actor_guid:
        context = baggage.set_baggage(_K_ACTOR, ctx.actor_guid, context=context)
    carrier: dict[str, str] = {}
    _baggage_propagator.inject(carrier, context=context)
    return carrier


def inject_internal(headers: dict[str, str], ctx: CorrelationContext) -> None:
    """Pose baggage + relais `traceparent` sur un appel vers une cible INTERNE.

    À N'APPELER QUE sur une frontière interne (STANDARD §3). Vers l'extérieur
    (webhook client, cible externe) on ne pose JAMAIS de `traceparent` : la
    topologie interne ne se publie pas au-delà de la frontière de confiance
    (STANDARD §4). L'asymétrie est intentionnelle — voir les points d'appel.
    """
    headers.update(to_baggage_headers(ctx))
    if ctx.traceparent:
        headers[_H_TRACEPARENT] = ctx.traceparent
        if ctx.tracestate:
            headers[_H_TRACESTATE] = ctx.tracestate


def from_headers(headers: Mapping[str, str]) -> CorrelationContext | None:
    """Reconstruit le contexte depuis des en-têtes entrants (baggage + trace).

    Retourne None si aucun `agflow.correlation_id` n'est présent. Le fil reçu
    est relayé OPAQUEMENT : ni le kind ni l'id ne sont réécrits.
    """
    carrier = {k.lower(): v for k, v in headers.items()}
    context = _baggage_propagator.extract(carrier)
    bag = baggage.get_all(context)
    cid = bag.get(_K_ID)
    if not cid:
        return None
    return CorrelationContext(
        origin=str(bag.get(_K_ORIGIN) or ORIGIN_DOC),
        correlation_id=str(cid),
        correlation_kind=str(bag.get(_K_KIND) or "document"),
        step=_opt(bag.get(_K_STEP)),
        actor_guid=_opt(bag.get(_K_ACTOR)),
        traceparent=carrier.get(_H_TRACEPARENT),
        tracestate=carrier.get(_H_TRACESTATE),
    )


def from_event_row(row: Mapping[str, object]) -> CorrelationContext | None:
    """Reconstruit le contexte d'un event depuis les colonnes de `document_event`.

    Source du worker d'automation : l'event a été journalisé avec son contexte,
    le worker le relaie vers la cible sans le réécrire.
    """
    cid = row.get("correlation_id")
    if not cid:
        return None
    return CorrelationContext(
        origin=str(row.get("origin") or ORIGIN_DOC),
        correlation_id=str(cid),
        correlation_kind=str(row.get("correlation_kind") or "document"),
        traceparent=_opt(row.get("traceparent")),
    )
