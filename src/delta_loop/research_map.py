from __future__ import annotations

from .models import ProjectSnapshot, ResearchLink, ResearchRelation, now_iso


def default_relationship(parent_kind: str, child_kind: str) -> ResearchRelation | None:
    if parent_kind == "question" and child_kind == "direction":
        return "explores"
    if parent_kind == "direction" and child_kind == "approach":
        return "tests"
    return None


def ensure_research_links(workspace: ProjectSnapshot) -> bool:
    """Turn legacy parent pointers into explicit graph links without losing compatibility."""
    nodes = {node.id: node for node in workspace.nodes}
    existing = {
        (link.source_id, link.target_id, link.relationship)
        for link in workspace.research_links
    }
    changed = False
    for link in workspace.research_links:
        if link.note == "Imported from the original research-map hierarchy.":
            link.note = ""
            changed = True
    for child in workspace.nodes:
        parent = nodes.get(child.parent_id or "")
        if not parent:
            continue
        relationship = default_relationship(parent.kind, child.kind)
        key = (parent.id, child.id, relationship)
        if not relationship or key in existing:
            continue
        workspace.research_links.append(
            ResearchLink(
                id=f"link-{parent.id}-{child.id}",
                source_id=parent.id,
                target_id=child.id,
                relationship=relationship,
                note="",
                created_at=workspace.imported_at or now_iso(),
            )
        )
        existing.add(key)
        changed = True
    return changed


def primary_parent_link(workspace: ProjectSnapshot, node_id: str) -> ResearchLink | None:
    node = next((item for item in workspace.nodes if item.id == node_id), None)
    if not node or not node.parent_id:
        return None
    return next(
        (
            link for link in workspace.research_links
            if link.source_id == node.parent_id and link.target_id == node.id
            and link.relationship in {"explores", "tests"}
        ),
        None,
    )
