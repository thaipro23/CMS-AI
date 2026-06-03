from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CourseTreeNode:
    node_id: str
    block_type: str
    title: str
    parent_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    children: list["CourseTreeNode"] = field(default_factory=list)


class CourseTreeBuilder:
    """Build and traverse Open edX Course -> Section -> Unit -> Component tree.

    Open edX-like payloads can contain BOTH `parent_block_id` and `children`.
    If we blindly connect both directions, the same edge is created twice and the
    flattened list contains duplicate blocks. That later violates the DB unique
    constraint `(course_id, block_id)` during sync. This builder therefore keeps
    an edge set and a traversal visited set.
    """

    def build(self, blocks: list[dict[str, Any]]) -> list[CourseTreeNode]:
        nodes: dict[str, CourseTreeNode] = {}
        child_ids: set[str] = set()
        edges: set[tuple[str, str]] = set()

        for block in blocks:
            block_id = str(block.get("block_id") or block.get("id") or "")
            if not block_id:
                continue
            # If a connector accidentally returns the same block twice, keep the
            # first raw payload and let flatten_blocks de-duplicate the result.
            nodes.setdefault(block_id, CourseTreeNode(
                node_id=block_id,
                block_type=str(block.get("type") or block.get("block_type") or "unknown"),
                title=str(block.get("display_name") or block.get("title") or block_id),
                parent_id=block.get("parent_block_id") or block.get("parent"),
                raw=block,
            ))

        def add_edge(parent_id: str | None, child_id: str | None) -> None:
            if not parent_id or not child_id:
                return
            if parent_id not in nodes or child_id not in nodes:
                return
            key = (parent_id, child_id)
            if key in edges:
                return
            edges.add(key)
            nodes[parent_id].children.append(nodes[child_id])
            child_ids.add(child_id)
            nodes[child_id].parent_id = parent_id

        for block in blocks:
            block_id = str(block.get("block_id") or block.get("id") or "")
            parent_id = block.get("parent_block_id") or block.get("parent")
            add_edge(parent_id, block_id)
            for child_id in block.get("children") or []:
                add_edge(block_id, str(child_id))

        roots = [node for node_id, node in nodes.items() if node_id not in child_ids]
        return roots or list(nodes.values())

    def traverse(self, roots: list[CourseTreeNode]) -> list[CourseTreeNode]:
        result: list[CourseTreeNode] = []
        stack = list(reversed(roots))
        visited: set[str] = set()
        while stack:
            node = stack.pop()
            if node.node_id in visited:
                continue
            visited.add(node.node_id)
            result.append(node)
            stack.extend(reversed(node.children))
        return result

    def flatten_blocks(self, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        roots = self.build(blocks)
        ordered = self.traverse(roots)
        flattened: list[dict[str, Any]] = []
        seen: set[str] = set()
        for node in ordered:
            if node.node_id in seen:
                continue
            seen.add(node.node_id)
            flattened.append(node.raw | {"parent_block_id": node.parent_id})
        return flattened
