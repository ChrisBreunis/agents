"""Conceptfacturen in het geheugen van de server.

Een factuur wordt nooit in één stap geboekt: eerst een concept (dat je kunt
laten zien en controleren), daarna pas het echte aanmaken in e-Boekhouden.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count


@dataclass
class Concept:
    concept_id: str
    payload: dict
    totalen: dict
    toelichting: dict = field(default_factory=dict)
    waarschuwingen: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "conceptId": self.concept_id,
            "factuur": self.payload,
            "totalen": self.totalen,
            "toelichting": self.toelichting,
            "waarschuwingen": self.waarschuwingen,
            "volgendeStap": (
                "Leg dit concept eerst voor aan de gebruiker. Roep daarna "
                f"create_invoice aan met draft_id='{self.concept_id}'."
            ),
        }


class ConceptStore:
    def __init__(self) -> None:
        self._concepten: dict[str, Concept] = {}
        self._teller = count(1)

    def nieuw(self, payload: dict, totalen: dict, toelichting: dict,
              waarschuwingen: list[str]) -> Concept:
        concept = Concept(
            concept_id=f"concept-{next(self._teller)}",
            payload=payload,
            totalen=totalen,
            toelichting=toelichting,
            waarschuwingen=waarschuwingen,
        )
        self._concepten[concept.concept_id] = concept
        return concept

    def haal(self, concept_id: str) -> Concept:
        concept = self._concepten.get(concept_id)
        if concept is None:
            bekend = ", ".join(self._concepten) or "geen"
            raise KeyError(
                f"Onbekend concept {concept_id!r}. Beschikbaar: {bekend}. "
                "Maak eerst een concept met prepare_invoice."
            )
        return concept

    def verwijder(self, concept_id: str) -> None:
        self._concepten.pop(concept_id, None)

    def alles(self) -> list[dict]:
        return [c.as_dict() for c in self._concepten.values()]
