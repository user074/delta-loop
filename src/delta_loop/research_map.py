from __future__ import annotations

from .models import ProjectSnapshot, ResearchLink, ResearchRelation, now_iso


def default_relationship(
    parent_kind: str,
    child_kind: str,
    parent_work_kind: str | None = None,
) -> ResearchRelation:
    if parent_kind == "question" and child_kind == "direction":
        return "explores"
    if parent_kind == "direction" and child_kind == "approach":
        return "tests"
    if parent_kind == "approach" and child_kind == "finding":
        return "produces"
    if parent_kind == "approach" and parent_work_kind == "literature-review" and child_kind == "direction":
        return "informs"
    return "leads-to"


def ensure_research_links(workspace: ProjectSnapshot) -> bool:
    """Turn legacy parent pointers into explicit graph links without losing compatibility."""
    nodes = {node.id: node for node in workspace.nodes}
    explicit_pairs = {
        (link.source_id, link.target_id)
        for link in workspace.research_links
        if link.id != f"link-{link.source_id}-{link.target_id}"
    }
    changed = False
    for link in list(workspace.research_links):
        if (
            link.id == f"link-{link.source_id}-{link.target_id}"
            and (link.source_id, link.target_id) in explicit_pairs
        ):
            workspace.research_links.remove(link)
            changed = True
            continue
        if link.note == "Imported from the original research-map hierarchy.":
            link.note = ""
            changed = True
    existing_pairs = {(link.source_id, link.target_id) for link in workspace.research_links}
    for child in workspace.nodes:
        parent = nodes.get(child.parent_id or "")
        if not parent:
            continue
        relationship = default_relationship(parent.kind, child.kind, parent.next_work_kind)
        pair = (parent.id, child.id)
        if pair in existing_pairs:
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
        existing_pairs.add(pair)
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
        ),
        None,
    )
