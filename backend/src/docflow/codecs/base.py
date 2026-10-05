"""Contrat de codec de type de contenu (spec MLD — F3).

Un type de contenu (`document.type`, cf. `documents.content_types`) = UNE entrée
de registre portant un codec. Le type est une **clé de registre**, jamais une
condition dans le code appelant : ajouter un type de contenu ne doit modifier ni
la sauvegarde, ni la recherche, ni le calcul des backlinks.

Responsabilités du codec, toutes dérivées du contenu brut stocké dans
`document_version.content` :

- ``parse`` / ``serialize`` : forme canonique (round-trip stable). Pour un type
  dont le stockage EST déjà la forme d'édition (markdown), c'est l'identité.
- ``to_plain_text`` : projection texte pour la recherche et le RAG.
- ``references`` : liens sortants (documents, artefacts, datasets) portés par le
  contenu — la reconstruction des tables de références s'appuie dessus.

**Fail-soft** : un contenu mal formé ne fait jamais échouer une sauvegarde. Un
codec renvoie au pire un texte vide et des références vides ; il ne lève pas.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar


@dataclass(frozen=True)
class CodecError:
    """Une erreur empêchant d'accepter un contenu.

    Pensée pour être **actionnable par un agent** autant que par un humain : on
    ne dit pas seulement « invalide », on dit OÙ, POURQUOI, et ce qui aurait été
    accepté. Un appelant qui reçoit la liste complète peut corriger en une
    passe au lieu de découvrir les erreurs une par une.
    """

    #: Chemin dans le document, en notation pointée/indicée : `fields[2].type`.
    #: Chaîne vide = l'erreur porte sur le document entier.
    path: str
    #: Message lisible, en français, explicitant le problème.
    message: str
    #: Code stable pour un traitement automatique (ex. `unknown_type`).
    code: str
    #: Vocabulaire accepté à cet endroit, quand l'erreur est un mot inconnu.
    allowed: tuple[str, ...] = ()
    #: Pointeur vers l'article de grammaire, pour que l'appelant puisse lire la règle.
    doc: str | None = None


@dataclass(frozen=True)
class DocumentReferences:
    """Liens sortants portés par un contenu.

    Les types reprennent EXACTEMENT les contrats des extracteurs historiques,
    pour que la bascule sur le codec soit sans changement de comportement :

    - ``documents`` : ``{uuid canonique: libellé}`` (dernier libellé gagnant) ;
    - ``artifacts`` : ensemble d'uuid canoniques ;
    - ``datasets``  : liste d'uuid canoniques, dédupliquée dans l'ordre de
      première apparition (l'ordre est significatif côté appelant).
    """

    documents: dict[str, str] = field(default_factory=dict)
    artifacts: set[str] = field(default_factory=set)
    datasets: list[str] = field(default_factory=list)

    @classmethod
    def empty(cls) -> DocumentReferences:
        """Aucun lien sortant — cas d'un contenu opaque au registre."""
        return cls()


class ContentCodec[M](ABC):
    """Codec d'un type de contenu. ``M`` = modèle canonique parsé.

    Une implémentation est **sans état** : une instance unique est partagée par
    le registre. Le paramètre ``content`` est toujours celui de la version
    courante, et peut être ``None`` (document sans corps).
    """

    #: Valeur de `document.type` servie par ce codec. Unique dans le registre.
    content_type: ClassVar[str]

    #: Le codec sait lire les liens sortants de cette grammaire.
    #:
    #: ``False`` = contenu OPAQUE : « je ne sais pas lire ce contenu » n'est PAS
    #: « ce contenu n'a aucun lien ». La réconciliation reconstruit les tables de
    #: références à partir de ce qui est extrait, et supprime les artefacts
    #: devenus orphelins : traiter un contenu illisible comme vide détruirait des
    #: données. Un codec opaque laisse donc les références existantes INTACTES.
    extracts_references: ClassVar[bool] = True

    @abstractmethod
    def parse(self, content: str | None) -> M:
        """Contenu brut → modèle canonique. Ne lève pas : fail-soft."""

    @abstractmethod
    def serialize(self, model: M) -> str:
        """Modèle canonique → contenu brut stockable. Round-trip stable."""

    @abstractmethod
    def to_plain_text(self, content: str | None) -> str:
        """Projection texte pour la recherche et le RAG.

        Doit rendre le *sens* du document, pas sa syntaxe : c'est ce texte qui
        décide si une recherche utilisateur trouve le document.
        """

    def references(self, content: str | None) -> DocumentReferences:
        """Liens sortants portés par le contenu.

        Défaut : aucun lien. Un type de contenu qui ne porte pas de lien (ou
        dont le support n'est pas encore écrit) hérite du comportement sûr —
        jamais d'extraction hasardeuse sur une syntaxe étrangère.
        """
        return DocumentReferences.empty()

    def canonicalize(self, content: str | None) -> str:
        """Contenu → forme canonique à enregistrer.

        Appelé côté serveur juste avant l'écriture d'une révision. Une grammaire
        stricte s'en sert pour figer sa forme (ordre des clés, indentation) et
        allouer ses identifiants stables ; une grammaire libre n'y touche pas.

        **Contrat impératif : ne jamais détruire.** Un contenu illisible doit
        être rendu tel quel. On est ici sur le chemin de sauvegarde, où perdre
        du texte utilisateur est pire que le garder mal formé ; le refus est le
        rôle de ``validate``, à la frontière de l'API.
        """
        return content or ""

    def validate(self, content: str | None) -> list[CodecError]:
        """Erreurs empêchant d'ACCEPTER ce contenu. Vide = contenu valide.

        Séparé de ``parse`` à dessein, parce que lecture et écriture n'ont pas
        les mêmes exigences :

        - ``parse`` / ``to_plain_text`` / ``references`` sont sur le chemin de
          LECTURE et de sauvegarde : ils ne lèvent jamais, un contenu abîmé
          doit rester affichable et cherchable ;
        - ``validate`` est sur le chemin d'ÉCRITURE : c'est là qu'un contenu mal
          formé doit être refusé, avant d'entrer en base.

        Défaut : aucune erreur. Une grammaire libre (markdown) n'a rien à
        refuser — on n'invente pas de rejet là où tout est acceptable.
        """
        return []
