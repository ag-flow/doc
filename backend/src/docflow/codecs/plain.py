"""Codec de repli — tout type de contenu absent du registre.

Garantit l'exigence « un type inconnu ne casse jamais la page » : le contenu est
rendu tel quel, en texte brut lisible. Aucune extraction de références n'est
tentée : chercher une syntaxe markdown dans un contenu dont on ignore la
grammaire produirait des liens faux, et le recyclage des références SUPPRIME les
artefacts devenus orphelins — une extraction hasardeuse détruirait des données.
"""

from __future__ import annotations

from docflow.codecs.base import ContentCodec

# Ce codec ne sert aucune valeur de `document.type` en propre : il est le défaut
# du registre pour toute valeur inconnue (y compris None).
PLAIN_TEXT = "__plain__"


class PlainTextCodec(ContentCodec[str]):
    """Contenu opaque : identité en parse/serialize, aucun lien sortant."""

    content_type = PLAIN_TEXT
    # Grammaire inconnue : on ne devine pas de liens, et on ne purge pas ceux
    # déjà enregistrés (cf. ContentCodec.extracts_references).
    extracts_references = False

    def parse(self, content: str | None) -> str:
        return content or ""

    def serialize(self, model: str) -> str:
        return model

    def to_plain_text(self, content: str | None) -> str:
        return content or ""
