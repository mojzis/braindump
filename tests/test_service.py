from __future__ import annotations

from braindump.service import (
    BraindumpService,
    CreateRequest,
    SearchRequest,
    UpdateRequest,
)


def test_service_handoff_roundtrip_and_branch_filter(cfg):
    service = BraindumpService(cfg)
    created = service.create(
        CreateRequest(
            entry_type="handoff",
            title="Service handoff",
            body="Service body",
            branch="feature/service",
        )
    )

    view = service.get_entry(created.entry.id)
    assert view is not None
    assert view.body == "Service body"
    assert view.entry.branch == "feature/service"
    assert [
        hit.entry.id
        for hit in service.search(
            SearchRequest(types=("handoff",), branch="feature/service")
        )
    ] == [created.entry.id]

    updated = service.update(UpdateRequest(created.entry.id, {"branch": "release"}))
    assert updated.branch == "release"
