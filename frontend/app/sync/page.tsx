"use client";

import { useEffect, useMemo, useState } from "react";
import { useAppContext } from "../../context/AppContext";
import {
  cleanResyncCourse,
  deleteCourseNode,
  getChunksPage,
  getCourseNodes,
  getCourseTree,
  getCourseConcepts,
  extractCourseConcepts,
  getSyncedCourses,
  syncCourse,
  uploadFileToNode,
} from "../../lib/api";
import {
  CourseChunk,
  CourseNodeOption,
  CourseOption,
  CourseTreeNode,
  Concept,
} from "../../types";
import {
  ActionMessage,
  ActionMessageData,
  toUserError,
} from "../../components/ui/ActionMessage";
import { LoadingButton } from "../../components/ui/LoadingButton";
import {
  CourseSearchPicker,
  NodePreviewText,
  TreeNode,
  collectAllNodeIds,
  findTreeNode,
} from "../../components/sync/SyncCourseWidgets";

const NODE_PREVIEW_PAGE_SIZE = 100;
const NODE_PREVIEW_MAX_PAGES = 1000;

export default function SyncPage() {
  const { courseId, setCourseId, authHeaders, can } = useAppContext();
  const [nodes, setNodes] = useState<CourseNodeOption[]>([]);
  const [tree, setTree] = useState<CourseTreeNode[]>([]);
  const [syncedCourses, setSyncedCourses] = useState<CourseOption[]>([]);
  const [courseSearch, setCourseSearch] = useState("");
  const [manualCourseId, setManualCourseId] = useState(courseId);
  const [coursePickerLoading, setCoursePickerLoading] = useState(false);
  const [coursePickerOpen, setCoursePickerOpen] = useState(false);
  const [nodeId, setNodeId] = useState("all");
  const [message, setMessage] = useState<ActionMessageData | null>(null);
  const [loading, setLoading] = useState(false);
  const [nodePreviewLoading, setNodePreviewLoading] = useState(false);
  const [nodePreviewChunks, setNodePreviewChunks] = useState<CourseChunk[]>([]);
  const [concepts, setConcepts] = useState<Concept[]>([]);
  const [conceptLoading, setConceptLoading] = useState(false);
  const [conceptExtracting, setConceptExtracting] = useState(false);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [chunkTotal, setChunkTotal] = useState(0);
  const [selectedUploadFile, setSelectedUploadFile] = useState<File | null>(
    null,
  );
  const [uploadLoading, setUploadLoading] = useState(false);
  const [replaceExistingUpload, setReplaceExistingUpload] = useState(true);
  const [deleteConfirmNode, setDeleteConfirmNode] =
    useState<CourseNodeOption | null>(null);
  const [deleteConfirmText, setDeleteConfirmText] = useState("");
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [cleanResyncOpen, setCleanResyncOpen] = useState(false);
  const [cleanResyncText, setCleanResyncText] = useState("");
  const [cleanResyncLoading, setCleanResyncLoading] = useState(false);
  const [chunkTotalTokens, setChunkTotalTokens] = useState(0);
  const contentNodes = useMemo(
    () => nodes.filter((node) => node.chunk_count > 0),
    [nodes],
  );
  const selectedCourseOption = useMemo(
    () => syncedCourses.find((course) => course.course_id === courseId) || null,
    [courseId, syncedCourses],
  );
  const filteredSyncedCourses = useMemo(() => {
    const keyword = courseSearch.trim().toLowerCase();
    if (!keyword) return syncedCourses;
    return syncedCourses.filter((course) => {
      const title = course.title || "";
      return (
        course.course_id.toLowerCase().includes(keyword) ||
        title.toLowerCase().includes(keyword)
      );
    });
  }, [syncedCourses, courseSearch]);
  const courseDropdownOptions = useMemo(() => {
    if (filteredSyncedCourses.some((course) => course.course_id === courseId)) {
      return filteredSyncedCourses;
    }
    if (courseSearch.trim()) return filteredSyncedCourses;
    return [
      {
        course_id: courseId,
        title: selectedCourseOption?.title || courseId,
        node_count: selectedCourseOption?.node_count || 0,
        chunk_count: selectedCourseOption?.chunk_count || 0,
        token_count: selectedCourseOption?.token_count || 0,
        last_synced_at: selectedCourseOption?.last_synced_at || null,
      },
      ...filteredSyncedCourses,
    ];
  }, [courseId, filteredSyncedCourses, selectedCourseOption, courseSearch]);
  const selectedNode = useMemo(
    () => nodes.find((node) => node.node_id === nodeId) || null,
    [nodes, nodeId],
  );
  const selectedTreeNode = useMemo(
    () => (nodeId === "all" ? null : findTreeNode(tree, nodeId)),
    [tree, nodeId],
  );
  const selectedSourceTypes = useMemo(
    () =>
      Array.from(
        new Set(nodePreviewChunks.map((chunk) => chunk.source_type)),
      ).filter(Boolean),
    [nodePreviewChunks],
  );
  const selectedNodeIsUploaded = useMemo(
    () =>
      Boolean(
        selectedNode &&
        (selectedNode.block_type === "uploaded_file" ||
          selectedNode.node_id.startsWith("ai-upload:")),
      ),
    [selectedNode],
  );
  const selectedContent = useMemo(
    () =>
      nodePreviewChunks
        .map((chunk, index) => {
          const title = `Chunk ${index + 1}/${nodePreviewChunks.length} · ${chunk.source_type} · ${chunk.token_count.toLocaleString("vi-VN")} tokens`;
          return `${title}\n${chunk.content}`;
        })
        .join("\n\n---\n\n"),
    [nodePreviewChunks],
  );

  async function loadSyncedCourses() {
    setCoursePickerLoading(true);
    try {
      const courses = await getSyncedCourses(authHeaders(), "", 1000);
      setSyncedCourses(courses);
    } catch (error) {
      setMessage(toUserError(error));
    } finally {
      setCoursePickerLoading(false);
    }
  }

  async function loadStructure(options: { clearMessage?: boolean } = {}) {
    setLoading(true);
    try {
      if (options.clearMessage) setMessage(null);
      const [nextNodes, nextTree] = await Promise.all([
        getCourseNodes(courseId, authHeaders()),
        getCourseTree(courseId, authHeaders()),
      ]);
      setNodes(nextNodes);
      setTree(nextTree);
      setExpandedIds((current) => {
        if (current.size) return current;
        return new Set(collectAllNodeIds(nextTree).slice(0, 80));
      });
    } catch (error) {
      setMessage(toUserError(error));
    } finally {
      setLoading(false);
    }
  }

  async function loadChunkSummary(nextNodeId = nodeId) {
    try {
      const chunkSummary = await getChunksPage(
        courseId,
        "all",
        "",
        authHeaders(),
        nextNodeId,
        1,
        1,
      );
      setChunkTotal(chunkSummary.total);
      setChunkTotalTokens(Number(chunkSummary.total_tokens ?? 0));
    } catch (error) {
      setMessage(toUserError(error));
    }
  }

  async function loadAll(options: { clearMessage?: boolean } = {}) {
    await Promise.all([loadStructure(options), loadChunkSummary(nodeId)]);
  }

  async function loadSelectedNodePreview(nextNodeId = nodeId) {
    if (!nextNodeId || nextNodeId === "all") {
      setNodePreviewChunks([]);
    setConcepts([]);
      return;
    }
    setNodePreviewLoading(true);
    try {
      const firstPage = await getChunksPage(
        courseId,
        "all",
        "",
        authHeaders(),
        nextNodeId,
        1,
        NODE_PREVIEW_PAGE_SIZE,
      );
      const allChunks = [...firstPage.items];
      const totalPages = Math.min(
        Number(firstPage.total_pages || 1),
        NODE_PREVIEW_MAX_PAGES,
      );
      for (let page = 2; page <= totalPages; page += 1) {
        const nextPage = await getChunksPage(
          courseId,
          "all",
          "",
          authHeaders(),
          nextNodeId,
          page,
          NODE_PREVIEW_PAGE_SIZE,
        );
        allChunks.push(...nextPage.items);
      }
      setNodePreviewChunks(allChunks);
    } catch (error) {
      setMessage(toUserError(error));
      setNodePreviewChunks([]);
    } finally {
      setNodePreviewLoading(false);
    }
  }

  async function loadConcepts(nextNodeId = nodeId) {
    try {
      setConceptLoading(true);
      const data = await getCourseConcepts(courseId, authHeaders(), nextNodeId);
      setConcepts(data.concepts || []);
    } catch (error) {
      // Concept panel is optional; do not block sync UI.
      setConcepts([]);
    } finally {
      setConceptLoading(false);
    }
  }

  async function handleExtractConcepts(force = false) {
    if (!nodeId || nodeId === "all") {
      setMessage({
        type: "warning",
        title: "Chưa chọn node",
        body: "Hãy chọn một node cụ thể để trích xuất concept/vấn đề học tập.",
      });
      return;
    }
    try {
      setConceptExtracting(true);
      const data = await extractCourseConcepts(courseId, authHeaders(false), nodeId, force, 20);
      setConcepts(data.concepts || []);
      setMessage({
        type: "success",
        title: "Đã trích xuất concept",
        body: `${data.concept_count} concept/vấn đề học tập đã sẵn sàng cho generation concept-aware.`,
      });
    } catch (error) {
      setMessage(toUserError(error));
    } finally {
      setConceptExtracting(false);
    }
  }

  async function handleSync() {
    const targetCourseId = manualCourseId.trim();
    if (!targetCourseId) {
      setMessage({
        type: "warning",
        title: "Chưa nhập mã khóa học",
        body: "Hãy nhập course_id rồi bấm Đồng bộ mã này.",
      });
      return;
    }
    try {
      setLoading(true);
      if (targetCourseId !== courseId) {
        setCourseId(targetCourseId);
        setNodeId("all");
        setNodePreviewChunks([]);
        setConcepts([]);
      }
      setMessage({
        type: "info",
        body: `Đang đồng bộ khóa học ${targetCourseId}...`,
      });
      const data: any = await syncCourse(targetCourseId, authHeaders(true));
      setMessage({
        type: "success",
        title: "Đồng bộ khóa học xong",
        body: `Đã đồng bộ ${data?.chunks || data?.chunk_count || data?.blocks_seen || "nội dung"} chunks/nodes cho khóa học ${targetCourseId}.`,
      });
      await loadSyncedCourses();
      if (targetCourseId === courseId) {
        await loadAll({ clearMessage: false });
        await loadSelectedNodePreview(nodeId);
      }
    } catch (error) {
      setMessage(toUserError(error));
    } finally {
      setLoading(false);
    }
  }

  function chooseVisibleCourse(nextCourseId: string) {
    if (!nextCourseId || nextCourseId === courseId) return;
    setCourseId(nextCourseId);
    setManualCourseId(nextCourseId);
    setNodeId("all");
    setNodePreviewChunks([]);
    setMessage({
      type: "info",
      title: "Đã đổi khóa học hiển thị",
      body: `Đang tải dữ liệu đã sync của khóa học ${nextCourseId}.`,
    });
  }

  function requestCleanResync() {
    setCleanResyncText("");
    setCleanResyncOpen(true);
  }

  async function confirmCleanResync() {
    if (cleanResyncText !== "RESET_COURSE_SYNC") {
      setMessage({
        type: "warning",
        title: "Chưa xác nhận",
        body: "Bạn cần nhập đúng RESET_COURSE_SYNC để xác nhận xóa dữ liệu đồng bộ cũ và đồng bộ lại.",
      });
      return;
    }
    try {
      setCleanResyncLoading(true);
      setLoading(true);
      setMessage({
        type: "info",
        body: "Đang xóa dữ liệu đồng bộ cũ và đồng bộ lại...",
      });
      const result: any = await cleanResyncCourse(
        courseId,
        authHeaders(false),
        "RESET_COURSE_SYNC",
      );
      setCleanResyncOpen(false);
      setCleanResyncText("");
      setNodeId("all");
      setNodePreviewChunks([]);
      setMessage({
        type: "success",
        title: "Đã xóa và đồng bộ lại",
        body: `Đã xóa ${result?.deleted_nodes || 0} node sync cũ, ${result?.deleted_chunks || 0} chunks cũ, rồi đồng bộ lại ${result?.blocks_seen || 0} blocks từ CMS.`,
      });
      await loadAll({ clearMessage: false });
    } catch (error) {
      setMessage(toUserError(error));
    } finally {
      setCleanResyncLoading(false);
      setLoading(false);
    }
  }

  async function handleUploadFileToNode() {
    if (!selectedNode || nodeId === "all") {
      setMessage({
        type: "warning",
        title: "Chưa chọn node",
        body: "Hãy chọn một node CMS cụ thể trước khi upload file.",
      });
      return;
    }
    if (!selectedUploadFile) {
      setMessage({
        type: "warning",
        title: "Chưa chọn file",
        body: "Hãy chọn file PDF, DOCX, PPTX, XLSX/XLSM, CSV, TXT, HTML, JSON, XML, SRT hoặc VTT. File .doc/.xls cũ cần chuyển sang .docx/.xlsx hoặc PDF.",
      });
      return;
    }
    try {
      setUploadLoading(true);
      setMessage({
        type: "info",
        body: `Đang tách nội dung file ${selectedUploadFile.name}...`,
      });
      const result: any = await uploadFileToNode(
        courseId,
        nodeId,
        selectedUploadFile,
        authHeaders(false),
        replaceExistingUpload,
      );
      const createdNodeId = String(result?.node_id || nodeId);
      setMessage({
        type: "success",
        title: "Đã tạo node con từ file",
        body: `Đã tạo node con cho file ${result?.filename || selectedUploadFile.name}: ${result?.chunks_created || 0} chunks, ${Number(result?.tokens_indexed || 0).toLocaleString("vi-VN")} tokens.`,
      });
      setSelectedUploadFile(null);
      setNodeId(createdNodeId);
      setExpandedIds(
        (current) => new Set([...Array.from(current), nodeId, createdNodeId]),
      );
      await loadAll({ clearMessage: false });
      await loadSelectedNodePreview(createdNodeId);
    } catch (error) {
      setMessage(toUserError(error));
    } finally {
      setUploadLoading(false);
    }
  }

  function selectNode(id: string) {
    setNodeId(id);
    if (id !== "all") {
      setExpandedIds((current) => new Set([...Array.from(current), id]));
    }
  }

  function toggleNode(id: string) {
    setExpandedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function requestDeleteSelectedNode() {
    if (!selectedNode || !selectedNodeIsUploaded) {
      setMessage({
        type: "warning",
        title: "Không thể xóa node CMS gốc",
        body: "Chỉ node con do AI Server tạo khi upload file mới được xóa ở đây. Node CMS/Open edX thật cần xóa trong Studio.",
      });
      return;
    }
    setDeleteConfirmText("");
    setDeleteConfirmNode(selectedNode);
  }

  async function confirmDeleteNode() {
    if (!deleteConfirmNode) return;
    if (deleteConfirmText !== "DELETE_NODE") {
      setMessage({
        type: "warning",
        title: "Chưa xác nhận",
        body: "Bạn cần nhập đúng DELETE_NODE để xác nhận xóa node.",
      });
      return;
    }
    try {
      setDeleteLoading(true);
      const deletedId = deleteConfirmNode.node_id;
      const parentId = deleteConfirmNode.parent_id || "all";
      const result: any = await deleteCourseNode(
        courseId,
        deletedId,
        authHeaders(false),
        "DELETE_NODE",
      );
      setMessage({
        type: "success",
        title: "Đã xóa node",
        body: `Đã xóa ${result?.deleted_nodes || 1} node và ${result?.deleted_chunks || 0} chunks liên quan khỏi AI Server.`,
      });
      setDeleteConfirmNode(null);
      setDeleteConfirmText("");
      setNodeId(parentId);
      await loadAll({ clearMessage: false });
      await loadSelectedNodePreview(parentId);
    } catch (error) {
      setMessage(toUserError(error));
    } finally {
      setDeleteLoading(false);
    }
  }

  function expandAll() {
    setExpandedIds(new Set(collectAllNodeIds(tree)));
  }

  function collapseAll() {
    setExpandedIds(new Set());
  }

  useEffect(() => {
    setManualCourseId(courseId);
    const timer = window.setTimeout(() => loadAll({ clearMessage: false }), 0);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId]);

  useEffect(() => {
    const timer = window.setTimeout(() => loadSyncedCourses(), 0);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      loadChunkSummary(nodeId);
      loadSelectedNodePreview(nodeId);
      loadConcepts(nodeId);
    }, 0);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [courseId, nodeId]);

  return (
    <div className="page-stack">
      <section className="card sync-course-control-card compact-course-control-card">
        <div className="sync-field sync-field-manual">
          <label>Nhập mã khóa học để đồng bộ</label>
          <div className="sync-inline-control">
            <input
              className="input"
              value={manualCourseId}
              onChange={(event) => setManualCourseId(event.target.value)}
              placeholder="course-v1:ORG+COURSE+RUN"
            />
            <LoadingButton
              className="btn"
              loading={loading}
              disabled={!can("sync_course") || !manualCourseId.trim()}
              onClick={handleSync}
            >
              Đồng bộ
            </LoadingButton>
          </div>
        </div>

        <div className="sync-field sync-field-picker">
          <label>Chọn khóa học đã sync</label>
          <CourseSearchPicker
            value={courseId}
            courses={courseDropdownOptions}
            search={courseSearch}
            loading={coursePickerLoading}
            open={coursePickerOpen}
            onOpenChange={setCoursePickerOpen}
            onSearchChange={setCourseSearch}
            onSelect={chooseVisibleCourse}
            onReload={loadSyncedCourses}
          />
        </div>

        <div className="sync-course-actions compact-actions">
          <button
            className="btn danger"
            type="button"
            disabled={loading || !can("sync_course")}
            onClick={requestCleanResync}
          >
            Xóa & đồng bộ lại
          </button>
        </div>
      </section>

      <section className="dashboard-grid">
        <div className="metric-card">
          <span>Chunks</span>
          <b>{chunkTotal}</b>
          <small>Tổng chunks theo node đang chọn</small>
        </div>
        <div className="metric-card">
          <span>Tokens</span>
          <b>{chunkTotalTokens.toLocaleString("vi-VN")}</b>
          <small>Tổng token theo node đang chọn</small>
        </div>
        <div className="metric-card">
          <span>Nodes</span>
          <b>{nodes.length}</b>
          <small>Node trong cây khóa học</small>
        </div>
        <div className="metric-card">
          <span>Content nodes</span>
          <b>{contentNodes.length}</b>
          <small>Node có chunk/token</small>
        </div>
      </section>

      <section className="grid sync-tree-detail-grid">
        <div className="card">
          <div className="section-head">
            <div>
              <h2>Cây nội dung khóa học</h2>
            </div>
            <div className="button-row compact">
              <button className="btn secondary" onClick={expandAll}>
                Hiện tất cả
              </button>
              <button className="btn secondary" onClick={collapseAll}>
                Thu gọn
              </button>
            </div>
          </div>
          <div className="tree-box">
            <button
              className={
                nodeId === "all"
                  ? "tree-row tree-row-button selected"
                  : "tree-row tree-row-button"
              }
              onClick={() => selectNode("all")}
            >
              <span className="soft-tag">all</span>
              <b>Toàn bộ khóa học</b>
              <small>Hiển thị toàn bộ nội dung</small>
            </button>
            {tree.length ? (
              tree.map((node) => (
                <TreeNode
                  key={node.node_id}
                  node={node}
                  selectedNodeId={nodeId}
                  onSelect={selectNode}
                  expandedIds={expandedIds}
                  onToggle={toggleNode}
                />
              ))
            ) : (
              <div className="empty-state">
                Chưa có cây nội dung. Hãy đồng bộ khóa học trước.
              </div>
            )}
          </div>
        </div>
        <div className="card node-detail-card">
          <div className="section-head">
            <div>
              <h2>Nội dung node được chọn</h2>
            </div>
            {selectedNode ? (
              <span className="badge">{selectedNode.chunk_count} chunks</span>
            ) : null}
          </div>
          {nodeId === "all" ? (
            <div className="empty-state">
              Hãy chọn một node trong cây nội dung để xem full nội dung.
            </div>
          ) : selectedNode ? (
            <div className="node-detail">
              <div className="node-detail-head">
                <span className="soft-tag">{selectedNode.block_type}</span>
                <h3>{selectedNode.title}</h3>
                <p>{selectedNode.path}</p>
                <div className="node-stats">
                  <span>1 node CMS</span>
                  <span>{selectedNode.chunk_count} chunks</span>
                  <span>
                    {selectedNode.token_count.toLocaleString("vi-VN")} tokens
                  </span>
                  {selectedTreeNode?.children?.length ? (
                    <span>{selectedTreeNode.children.length} node con</span>
                  ) : (
                    <span>Không có node con</span>
                  )}
                </div>
                {selectedSourceTypes.length ? (
                  <div className="button-row compact">
                    {selectedSourceTypes.map((type) => (
                      <span key={type} className="badge">
                        {type}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
              {nodePreviewLoading ? (
                <div className="empty-state">Đang tải nội dung node...</div>
              ) : nodePreviewChunks.length ? (
                <NodePreviewText content={selectedContent} />
              ) : (
                <div className="empty-state">
                  Node này chưa có nội dung text.
                </div>
              )}

              <div className="concept-panel">
                <div className="concept-panel-head">
                  <div>
                    <b>Concept / vấn đề học tập</b>
                    <small>{concepts.length} concept cho node này</small>
                  </div>
                  <div className="button-row compact">
                    <LoadingButton
                      className="btn secondary"
                      loading={conceptExtracting}
                      loadingLabel="Đang trích xuất..."
                      disabled={!can("generate_questions")}
                      onClick={() => handleExtractConcepts(false)}
                    >
                      Trích xuất concept
                    </LoadingButton>
                    <button
                      className="btn secondary"
                      type="button"
                      disabled={conceptExtracting || !can("generate_questions")}
                      onClick={() => handleExtractConcepts(true)}
                    >
                      Làm lại
                    </button>
                  </div>
                </div>
                {conceptLoading ? (
                  <div className="empty-state compact-empty">Đang tải concept...</div>
                ) : concepts.length ? (
                  <div className="concept-list">
                    {concepts.slice(0, 8).map((concept) => (
                      <div key={concept.id} className="concept-row">
                        <div>
                          <b>{concept.title}</b>
                          <small>{concept.learning_objective || concept.summary}</small>
                        </div>
                        <span className="badge">{concept.difficulty_hint}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="empty-state compact-empty">
                    Chưa có concept. Bấm Trích xuất concept để hệ thống sinh câu hỏi theo vấn đề học tập thay vì random theo chunk.
                  </div>
                )}
              </div>


              <div className="upload-node-box upload-node-box-below-content">
                <div>
                  <b>Thêm file thành node con mới</b>
                </div>
                <div className="upload-node-controls">
                  <input
                    className="input"
                    type="file"
                    accept=".pdf,.ppt,.pptx,.docx,.xlsx,.xlsm,.csv,.tsv,.txt,.md,.markdown,.html,.htm,.json,.xml,.srt,.vtt"
                    onChange={(event) =>
                      setSelectedUploadFile(event.target.files?.[0] || null)
                    }
                  />
                  <label className="inline-check">
                    <input
                      type="checkbox"
                      checked={replaceExistingUpload}
                      onChange={(event) =>
                        setReplaceExistingUpload(event.target.checked)
                      }
                    />{" "}
                    Ghi đè nếu trùng tên file
                  </label>
                  <LoadingButton
                    className="btn"
                    loading={uploadLoading}
                    loadingLabel="Đang tạo node con..."
                    disabled={!can("sync_course") || !selectedUploadFile}
                    onClick={handleUploadFileToNode}
                  >
                    Tạo node con từ file
                  </LoadingButton>
                </div>
              </div>

              {selectedNodeIsUploaded ? (
                <div className="delete-node-box">
                  <div>
                    <b>Xóa node con này</b>
                  </div>
                  <button
                    className="btn danger"
                    type="button"
                    disabled={!can("sync_course")}
                    onClick={requestDeleteSelectedNode}
                  >
                    Xóa node
                  </button>
                </div>
              ) : null}
            </div>
          ) : (
            <div className="empty-state">
              Không tìm thấy node đã chọn trong dữ liệu hiện tại.
            </div>
          )}
        </div>
      </section>

      {cleanResyncOpen ? (
        <div className="modal-backdrop">
          <div className="card modal-card delete-confirm-card">
            <div className="section-head">
              <div>
                <h2>Xác nhận xóa dữ liệu đồng bộ khóa học</h2>
              </div>
              <button
                className="btn secondary"
                type="button"
                onClick={() => setCleanResyncOpen(false)}
              >
                Đóng
              </button>
            </div>
            <div className="notice-card warning">
              <b>Khóa học sẽ được làm sạch dữ liệu sync:</b>
              <span>{courseId}</span>
            </div>
            <label>
              Nhập <code>RESET_COURSE_SYNC</code> để xác nhận
            </label>
            <input
              className="input"
              value={cleanResyncText}
              onChange={(event) => setCleanResyncText(event.target.value)}
              placeholder="RESET_COURSE_SYNC"
              autoFocus
            />
            <div className="button-row">
              <button
                className="btn secondary"
                type="button"
                onClick={() => setCleanResyncOpen(false)}
              >
                Hủy
              </button>
              <LoadingButton
                className="btn danger"
                loading={cleanResyncLoading}
                loadingLabel="Đang xóa và đồng bộ..."
                disabled={cleanResyncText !== "RESET_COURSE_SYNC"}
                onClick={confirmCleanResync}
              >
                Xác nhận xóa & đồng bộ lại
              </LoadingButton>
            </div>
          </div>
        </div>
      ) : null}
      {deleteConfirmNode ? (
        <div className="modal-backdrop">
          <div className="card modal-card delete-confirm-card">
            <div className="section-head">
              <div>
                <h2>Xác nhận xóa node</h2>
              </div>
              <button
                className="btn secondary"
                type="button"
                onClick={() => setDeleteConfirmNode(null)}
              >
                Đóng
              </button>
            </div>
            <div className="notice-card warning">
              <b>Node sẽ bị xóa:</b>
              <span>{deleteConfirmNode.title}</span>
              <small>{deleteConfirmNode.path}</small>
            </div>
            <label>
              Nhập <code>DELETE_NODE</code> để xác nhận
            </label>
            <input
              className="input"
              value={deleteConfirmText}
              onChange={(event) => setDeleteConfirmText(event.target.value)}
              placeholder="DELETE_NODE"
              autoFocus
            />
            <div className="button-row">
              <button
                className="btn secondary"
                type="button"
                onClick={() => setDeleteConfirmNode(null)}
              >
                Hủy
              </button>
              <LoadingButton
                className="btn danger"
                loading={deleteLoading}
                loadingLabel="Đang xóa..."
                disabled={deleteConfirmText !== "DELETE_NODE"}
                onClick={confirmDeleteNode}
              >
                Xác nhận xóa
              </LoadingButton>
            </div>
          </div>
        </div>
      ) : null}
      <ActionMessage message={message} onClose={() => setMessage(null)} />
    </div>
  );
}
