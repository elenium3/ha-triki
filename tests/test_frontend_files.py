"""The card's files: revalidated on every load, nothing else served."""

from __future__ import annotations

from homeassistant.core import HomeAssistant


async def test_card_files_are_revalidated(hass: HomeAssistant, setup, hass_client_no_auth) -> None:
    client = await hass_client_no_auth()
    resp = await client.get("/triki_frontend/triki-cap.js")
    assert resp.status == 200
    assert resp.headers["Cache-Control"] == "no-cache"
    etag = resp.headers["ETag"]
    again = await client.get("/triki_frontend/triki-cap.js", headers={"If-None-Match": etag})
    assert again.status == 304  # unchanged: nothing sent again


async def test_only_the_card_files_are_served(
    hass: HomeAssistant, setup, hass_client_no_auth
) -> None:
    client = await hass_client_no_auth()
    for path in ("LICENSES.md", "..%2F__init__.py", "..%2Fmanifest.json", "nope.js"):
        assert (await client.get(f"/triki_frontend/{path}")).status in (400, 404), path
