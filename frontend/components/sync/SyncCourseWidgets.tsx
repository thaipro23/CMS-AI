"use client";

import { CourseOption, CourseTreeNode } from "../../types";

type TreeNodeProps = {
  node: CourseTreeNode;
  depth?: number;
  selectedNodeId: string;
  onSelect: (id: string) => void;
  expandedIds: Set<string>;
  onToggle: (id: string) => void;
};

export function TreeNode({
  node,
  depth = 0,
  selectedNodeId,
  onSelect,
  expandedIds,
  onToggle,
}: TreeNodeProps) {
  const selected = selectedNodeId === node.node_id;
  const hasChildren = Boolean(node.children?.length);
  const expanded = expandedIds.has(node.node_id);
  const chunkLabel = `${node.chunk_count} chunk${node.chunk_count > 1 ? "s" : ""}`;
  const nodeLabel = hasChildren
    ? `${node.children.length} node con`
    : "node cuối";

  return (
    <div className="tree-node" style={{ marginLeft: depth * 14 }}>
      <div
        className={
          selected
            ? "tree-row tree-row-button selected"
            : "tree-row tree-row-button"
        }
      >
        <button
          className="tree-toggle"
          type="button"
          aria-label={
            hasChildren
              ? expanded
                ? "Ẩn node con"
                : "Hiện node con"
              : "Không có node con"
          }
          disabled={!hasChildren}
          onClick={(event) => {
            event.stopPropagation();
            onToggle(node.node_id);
          }}
        >
          {hasChildren ? (expanded ? "▾" : "▸") : "•"}
        </button>
        <button
          className="tree-main"
          type="button"
          onClick={() => onSelect(node.node_id)}
        >
          <span className="soft-tag">{node.block_type}</span>
          <b>{node.title || node.node_id}</b>
          <small>
            {nodeLabel} · {chunkLabel} ·{" "}
            {node.token_count.toLocaleString("vi-VN")} tokens
          </small>
        </button>
      </div>
      {hasChildren && expanded
        ? node.children.map((child) => (
            <TreeNode
              key={child.node_id}
              node={child}
              depth={depth + 1}
              selectedNodeId={selectedNodeId}
              onSelect={onSelect}
              expandedIds={expandedIds}
              onToggle={onToggle}
            />
          ))
        : null}
    </div>
  );
}

function buildDescendantIds(root: CourseTreeNode): string[] {
  const ids: string[] = [];
  const stack = [root];
  while (stack.length) {
    const current = stack.pop()!;
    ids.push(current.node_id);
    for (const child of current.children || []) stack.push(child);
  }
  return ids;
}

export function findTreeNode(
  tree: CourseTreeNode[],
  nodeId: string,
): CourseTreeNode | null {
  const stack = [...tree];
  while (stack.length) {
    const current = stack.shift()!;
    if (current.node_id === nodeId) return current;
    stack.unshift(...(current.children || []));
  }
  return null;
}

export function collectAllNodeIds(tree: CourseTreeNode[]): string[] {
  return tree.flatMap((node) => buildDescendantIds(node));
}

export function NodePreviewText({ content }: { content: string }) {
  return (
    <div className="node-full-content rendered">
      {content.split("\n").map((line, index) => {
        const isCorrect = line.includes("[ĐÁP ÁN ĐÚNG]");
        const display = line.replace("[ĐÁP ÁN ĐÚNG]", "✓ Đáp án đúng");
        if (!display.trim())
          return (
            <div key={index} className="node-content-line blank">
              &nbsp;
            </div>
          );
        return (
          <div
            key={index}
            className={
              isCorrect
                ? "node-content-line problem-correct-line"
                : "node-content-line"
            }
          >
            {display}
          </div>
        );
      })}
    </div>
  );
}

function formatCourseOption(course: CourseOption) {
  return `${course.course_id} · ${course.chunk_count.toLocaleString("vi-VN")} chunks`;
}

export function CourseSearchPicker({
  value,
  courses,
  search,
  loading,
  open,
  onOpenChange,
  onSearchChange,
  onSelect,
  onReload,
}: {
  value: string;
  courses: CourseOption[];
  search: string;
  loading: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSearchChange: (value: string) => void;
  onSelect: (courseId: string) => void;
  onReload: () => void;
}) {
  const selected = courses.find((course) => course.course_id === value) || null;
  return (
    <div className="course-combobox">
      <button
        className="course-combobox-trigger"
        type="button"
        onClick={() => onOpenChange(!open)}
      >
        <span>
          <b>{value || "Chọn khóa học"}</b>
          <small>
            {selected
              ? `${selected.node_count.toLocaleString("vi-VN")} nodes · ${selected.chunk_count.toLocaleString("vi-VN")} chunks · ${selected.token_count.toLocaleString("vi-VN")} tokens`
              : "Chưa có trong danh sách đã sync cục bộ"}
          </small>
        </span>
        <strong>{open ? "▴" : "▾"}</strong>
      </button>
      {open ? (
        <div className="course-combobox-menu">
          <div className="course-combobox-search-row">
            <input
              className="input"
              value={search}
              onChange={(event) => onSearchChange(event.target.value)}
              placeholder="Tìm khóa học đã sync"
              autoFocus
            />
            <button
              className="btn secondary"
              type="button"
              disabled={loading}
              onClick={onReload}
            >
              Tải lại
            </button>
          </div>
          <div className="course-combobox-list">
            {loading ? (
              <div className="course-combobox-empty">Đang tải...</div>
            ) : courses.length ? (
              courses.map((course) => (
                <button
                  key={course.course_id}
                  className={
                    course.course_id === value
                      ? "course-combobox-option selected"
                      : "course-combobox-option"
                  }
                  type="button"
                  onClick={() => {
                    onSelect(course.course_id);
                    onOpenChange(false);
                  }}
                >
                  <b>{course.course_id}</b>
                  <small>{formatCourseOption(course)}</small>
                </button>
              ))
            ) : (
              <div className="course-combobox-empty">Không có khóa học phù hợp</div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}

