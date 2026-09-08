"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type QuestionTypeWeights = {
  single_select: number;
  multi_select: number;
  dropdown_fill: number;
  text_input: number;
  numerical_input: number;
};

const STORAGE_KEY = "bank-quiz-constraint-mode-v2";
const DEFAULT_WEIGHTS: QuestionTypeWeights = {
  single_select: 50,
  multi_select: 30,
  dropdown_fill: 20,
  text_input: 0,
  numerical_input: 0,
};

function clampPercent(value: number) {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, Math.trunc(value)));
}

export default function ConstraintModeControls() {
  const [difficultyEnabled, setDifficultyEnabled] = useState(true);
  const [questionTypeEnabled, setQuestionTypeEnabled] = useState(false);
  const [weights, setWeights] = useState<QuestionTypeWeights>(DEFAULT_WEIGHTS);

  const difficultyRef = useRef(true);
  const questionTypeRef = useRef(false);
  const weightsRef = useRef<QuestionTypeWeights>(DEFAULT_WEIGHTS);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const saved = JSON.parse(raw) as Partial<{
        difficultyEnabled: boolean;
        questionTypeEnabled: boolean;
        weights: Partial<QuestionTypeWeights>;
      }>;
      const nextWeights = { ...DEFAULT_WEIGHTS, ...(saved.weights || {}) };
      if (typeof saved.difficultyEnabled === "boolean") setDifficultyEnabled(saved.difficultyEnabled);
      if (typeof saved.questionTypeEnabled === "boolean") setQuestionTypeEnabled(saved.questionTypeEnabled);
      setWeights({
        single_select: clampPercent(Number(nextWeights.single_select)),
        multi_select: clampPercent(Number(nextWeights.multi_select)),
        dropdown_fill: clampPercent(Number(nextWeights.dropdown_fill)),
        text_input: clampPercent(Number(nextWeights.text_input)),
        numerical_input: clampPercent(Number(nextWeights.numerical_input)),
      });
    } catch {
      // Ignore stale local settings and keep safe defaults.
    }
  }, []);

  useEffect(() => {
    difficultyRef.current = difficultyEnabled;
    questionTypeRef.current = questionTypeEnabled;
    weightsRef.current = weights;
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ difficultyEnabled, questionTypeEnabled, weights }),
    );
  }, [difficultyEnabled, questionTypeEnabled, weights]);

  useEffect(() => {
    const originalFetch = window.fetch.bind(window);

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.toString()
            : input.url;

      const isConstraintRequest =
        /\/question-bank-v2\/releases\/[^/]+\/quiz\/(?:preview|create-job)(?:\?|$)/.test(url);

      if (isConstraintRequest && typeof init?.body === "string") {
        try {
          const payload = JSON.parse(init.body) as Record<string, unknown>;
          payload.difficulty_enabled = difficultyRef.current;
          payload.question_type_enabled = questionTypeRef.current;
          payload.question_type_weights = { ...weightsRef.current };
          init = { ...init, body: JSON.stringify(payload) };
        } catch {
          // Preserve the original request when the payload is not JSON.
        }
      }

      return originalFetch(input, init);
    };

    return () => {
      window.fetch = originalFetch;
    };
  }, []);

  const typeTotal = useMemo(
    () => Object.values(weights).reduce((sum, value) => sum + Number(value || 0), 0),
    [weights],
  );

  function updateWeight(key: keyof QuestionTypeWeights, value: number) {
    setWeights((current) => ({ ...current, [key]: clampPercent(value) }));
  }

  return (
    <section
      className="card"
      aria-label="Quy tắc chia câu Quiz và Final test"
      style={{ margin: "16px 24px 0", padding: 16 }}
    >
      <div className="section-heading compact-heading">
        <div>
          <h3>Quy tắc chia câu Quiz + Final test</h3>
          <p className="muted">
            Tắt tiêu chí nào thì hệ thống bỏ qua tiêu chí đó. Final test vẫn luôn chia đều theo từng Bài/Release.
          </p>
        </div>
      </div>

      <div className="option-grid compact-options">
        <label className="toggle-line toggle-strong">
          <input
            type="checkbox"
            checked={difficultyEnabled}
            onChange={(event) => setDifficultyEnabled(event.target.checked)}
          />
          <span>Chia theo độ khó</span>
        </label>
        <label className="toggle-line toggle-strong">
          <input
            type="checkbox"
            checked={questionTypeEnabled}
            onChange={(event) => setQuestionTypeEnabled(event.target.checked)}
          />
          <span>Chia theo định dạng câu</span>
        </label>
      </div>

      {!difficultyEnabled ? (
        <p className="muted" style={{ marginTop: 8 }}>
          Độ khó đang tắt: tỷ lệ Dễ/Trung bình/Khó trong popup Tạo Quiz sẽ được bỏ qua.
        </p>
      ) : null}

      <div style={{ marginTop: 14, opacity: questionTypeEnabled ? 1 : 0.6 }}>
        <div className="section-heading compact-heading">
          <div>
            <h3>Tỷ lệ định dạng câu</h3>
            <p className="muted">
              Chỉ áp dụng khi bật “Chia theo định dạng câu”. Tổng tỷ lệ phải bằng 100%.
            </p>
          </div>
          <span className={`status ${typeTotal === 100 ? "success" : "warning"}`}>
            {typeTotal}%
          </span>
        </div>

        <div className="quiz-small-grid">
          <label>
            Chọn 1 đáp án (%)
            <input
              className="input"
              type="number"
              min={0}
              max={100}
              disabled={!questionTypeEnabled}
              value={weights.single_select}
              onChange={(event) => updateWeight("single_select", Number(event.target.value))}
            />
          </label>
          <label>
            Chọn nhiều đáp án (%)
            <input
              className="input"
              type="number"
              min={0}
              max={100}
              disabled={!questionTypeEnabled}
              value={weights.multi_select}
              onChange={(event) => updateWeight("multi_select", Number(event.target.value))}
            />
          </label>
          <label>
            Chọn / điền ô trống (%)
            <input
              className="input"
              type="number"
              min={0}
              max={100}
              disabled={!questionTypeEnabled}
              value={weights.dropdown_fill}
              onChange={(event) => updateWeight("dropdown_fill", Number(event.target.value))}
            />
          </label>
          <label>
            Nhập văn bản (%)
            <input
              className="input"
              type="number"
              min={0}
              max={100}
              disabled={!questionTypeEnabled}
              value={weights.text_input}
              onChange={(event) => updateWeight("text_input", Number(event.target.value))}
            />
          </label>
          <label>
            Nhập số (%)
            <input
              className="input"
              type="number"
              min={0}
              max={100}
              disabled={!questionTypeEnabled}
              value={weights.numerical_input}
              onChange={(event) => updateWeight("numerical_input", Number(event.target.value))}
            />
          </label>
        </div>
      </div>
    </section>
  );
}
