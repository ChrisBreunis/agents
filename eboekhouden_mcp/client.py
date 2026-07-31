"""Dunne client voor de e-Boekhouden REST API (v1).

Regelt het sessietoken, retries op throttling/serverfouten en leesbare
foutmeldingen. De aanroepende code werkt met gewone dicts.
"""
from __future__ import annotations

import time
from typing import Any

import requests

from config import Config

# Een sessietoken is ongeveer een uur geldig; we vernieuwen ruim op tijd.
TOKEN_GELDIGHEID_SECONDEN = 50 * 60
RETRY_STATUS = (429, 500, 502, 503, 504)


class EBoekhoudenError(RuntimeError):
    """Fout uit de e-Boekhouden API, met status en (indien aanwezig) uitleg."""

    def __init__(self, status: int, bericht: str, pad: str = ""):
        self.status = status
        self.pad = pad
        super().__init__(f"e-Boekhouden gaf {status} op {pad}: {bericht}" if pad
                         else f"e-Boekhouden gaf {status}: {bericht}")


class EBoekhoudenClient:
    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        self._token: str | None = None
        self._token_tijd: float = 0.0
        # De API verwacht het sessietoken kaal in de Authorization-header. Mocht
        # jouw omgeving het 'Bearer'-voorvoegsel vereisen, dan schakelt de client
        # daar bij de eerste 401 automatisch naar over.
        self._auth_stijl = "plain"
        self._stijl_geprobeerd = False

    # ── sessie ──────────────────────────────────────────────────────────
    def _nieuw_token(self) -> None:
        url = f"{self.config.base_url}/v1/session"
        try:
            resp = self.session.post(
                url,
                json={"accessToken": self.config.api_token, "source": self.config.source},
                timeout=self.config.timeout,
            )
        except requests.RequestException as exc:
            raise EBoekhoudenError(
                0,
                f"kan {self.config.base_url} niet bereiken ({exc.__class__.__name__}). "
                "Controleer je internetverbinding, een eventuele proxy of firewall.",
                "/v1/session",
            ) from exc
        if resp.status_code >= 400:
            raise EBoekhoudenError(resp.status_code, _fouttekst(resp), "/v1/session")

        data = resp.json() if resp.content else {}
        token = data.get("token") or data.get("accessToken")
        if not token:
            raise EBoekhoudenError(
                resp.status_code,
                f"geen token in het antwoord ({data!r})",
                "/v1/session",
            )
        self._token = token
        self._token_tijd = time.monotonic()

    def _zorg_voor_token(self) -> None:
        verlopen = time.monotonic() - self._token_tijd > TOKEN_GELDIGHEID_SECONDEN
        if self._token is None or verlopen:
            self._nieuw_token()

    def _auth_header(self) -> str:
        assert self._token is not None
        return f"Bearer {self._token}" if self._auth_stijl == "bearer" else self._token

    def sluit_sessie(self) -> None:
        """Sessietoken netjes intrekken. Fouten hierbij zijn niet interessant."""
        if self._token is None:
            return
        try:
            self.session.delete(
                f"{self.config.base_url}/v1/session",
                headers={"Authorization": self._auth_header()},
                timeout=self.config.timeout,
            )
        except requests.RequestException:
            pass
        finally:
            self._token = None

    # ── verzoeken ───────────────────────────────────────────────────────
    def _request(self, methode: str, pad: str, **kwargs: Any) -> Any:
        url = f"{self.config.base_url}{pad}"
        token_vernieuwd = False

        for poging in range(5):
            self._zorg_voor_token()
            headers = {"Authorization": self._auth_header(), "Accept": "application/json"}
            headers.update(kwargs.pop("headers", {}))

            try:
                resp = self.session.request(
                    methode, url, headers=headers, timeout=self.config.timeout, **kwargs
                )
            except requests.RequestException as exc:
                if poging == 4:
                    raise EBoekhoudenError(0, f"netwerkfout: {exc}", pad) from exc
                time.sleep(2 ** poging)
                continue

            if resp.status_code == 401:
                # Eerst de andere Authorization-vorm proberen, daarna een vers token.
                if not self._stijl_geprobeerd:
                    self._stijl_geprobeerd = True
                    self._auth_stijl = "bearer" if self._auth_stijl == "plain" else "plain"
                    continue
                if not token_vernieuwd:
                    token_vernieuwd = True
                    self._token = None
                    continue
                raise EBoekhoudenError(401, _fouttekst(resp), pad)

            if resp.status_code in RETRY_STATUS and poging < 4:
                wacht = resp.headers.get("Retry-After")
                time.sleep(int(wacht) if wacht and wacht.isdigit() else 2 ** poging)
                continue

            if resp.status_code >= 400:
                raise EBoekhoudenError(resp.status_code, _fouttekst(resp), pad)

            if not resp.content:
                return None
            try:
                return resp.json()
            except ValueError:
                return resp.text

        raise EBoekhoudenError(0, "geen antwoord na meerdere pogingen", pad)

    def get(self, pad: str, params: dict | None = None) -> Any:
        return self._request("GET", pad, params=params)

    def post(self, pad: str, body: dict, params: dict | None = None) -> Any:
        return self._request("POST", pad, json=body, params=params)

    # ── endpoints ───────────────────────────────────────────────────────
    def administratie(self) -> Any:
        return self.get("/v1/administration")

    def relaties(self, limit: int = 100, offset: int = 0) -> list[dict]:
        return items(self.get("/v1/relation", {"limit": limit, "offset": offset}))

    def relatie(self, relation_id: int) -> dict:
        return self.get(f"/v1/relation/{relation_id}")

    def maak_relatie(self, body: dict) -> Any:
        return self.post("/v1/relation", body)

    def factuursjablonen(self) -> list[dict]:
        return items(self.get("/v1/invoicetemplate"))

    def grootboekrekeningen(self, limit: int = 500, offset: int = 0) -> list[dict]:
        return items(self.get("/v1/ledger", {"limit": limit, "offset": offset}))

    def facturen(self, limit: int = 50, offset: int = 0) -> list[dict]:
        return items(self.get("/v1/invoice", {"limit": limit, "offset": offset}))

    def factuur(self, invoice_id: int) -> dict:
        return self.get(f"/v1/invoice/{invoice_id}")

    def maak_factuur(self, body: dict, mailen: bool = False) -> Any:
        params = {"email": "true"} if mailen else None
        return self.post("/v1/invoice", body, params=params)


def items(payload: Any) -> list[dict]:
    """Haal de lijst uit een antwoord, ongeacht of de API een kale array of een
    omhulsel met 'items'/'data' teruggeeft."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for sleutel in ("items", "data", "results"):
            waarde = payload.get(sleutel)
            if isinstance(waarde, list):
                return waarde
        return [payload]
    return []


def _fouttekst(resp: requests.Response) -> str:
    try:
        data = resp.json()
    except ValueError:
        return (resp.text or "").strip()[:500] or resp.reason
    if isinstance(data, dict):
        for sleutel in ("message", "error", "title", "detail"):
            if data.get(sleutel):
                return str(data[sleutel])
    return str(data)[:500]
