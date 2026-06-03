from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.course import ContentChunk, Topic

# Generic words must not become topics. The old extractor allowed single words
# such as "Dùng", "Tải", "Liệu", "Giới" to become topics, which looked weird
# in the UI. Keep this list intentionally broad for Vietnamese course content.
STOPWORDS = {
    "và", "là", "của", "có", "trong", "cho", "một", "các", "được", "với", "khi", "thì", "này", "đó",
    "dùng", "sử", "dụng", "tải", "liệu", "tài", "giới", "thiệu", "cơ", "bản", "nội", "dung", "bài",
    "học", "sinh", "viên", "câu", "hỏi", "đáp", "án", "đúng", "sai", "trắc", "nghiệm", "kiểm", "tra",
    "the", "and", "for", "with", "that", "this", "from", "are", "you", "your", "into", "using", "use", "used",
    "overview", "introduction", "basic", "lesson", "chapter", "unit", "reading", "video", "slide", "handout",
}

BAD_AUTO_TOPIC_TITLES = {
    "Dùng", "Tải", "Liệu", "Tài", "Giới", "Core", "Api", "Database", "Rest Api", "Dbcontext", "Được", "Một",
}


@dataclass(frozen=True)
class TopicRule:
    title: str
    patterns: tuple[str, ...]
    summary: str
    weight: int = 5


TOPIC_RULES: tuple[TopicRule, ...] = (
    TopicRule("REST API", (r"\brest\s*api\b", r"representational\s+state"), "Khái niệm REST API và cách tổ chức tài nguyên trong API.", 10),
    TopicRule("HTTP Methods", (r"\bhttp\s+methods?\b", r"\bget\b", r"\bpost\b", r"\bput\b", r"\bdelete\b", r"\bpatch\b"), "Các phương thức HTTP như GET, POST, PUT, DELETE và PATCH.", 9),
    TopicRule("Entity Framework Core", (r"\bentity\s+framework\s+core\b", r"\bef\s*core\b"), "ORM Entity Framework Core trong .NET.", 9),
    TopicRule("DbContext", (r"\bdbcontext\b", r"\bdb\s+context\b"), "Vai trò của DbContext trong EF Core.", 8),
    TopicRule("Migration", (r"\bmigrations?\b", r"\bdatabase\s+schema\b", r"\bschema\b"), "Migration để tạo và cập nhật schema database.", 7),
    TopicRule("Open edX Course Content", (r"\bopen\s*edx\b", r"\bcourse\s+blocks?\b", r"\bstudio\b", r"\bcms\b"), "Nội dung khóa học Open edX, course blocks, CMS/Studio và component.", 8),
    TopicRule("Course Sync", (r"\bsync\b", r"\bđồng\s+bộ\b", r"\bcontent\s+hash\b", r"\bhash\b"), "Đồng bộ nội dung khóa học, lưu hash và phát hiện thay đổi.", 7),
    TopicRule("AI Question Bank", (r"\bquestion\s+bank\b", r"\bngân\s+hàng\s+câu\s+hỏi\b", r"\blearning\s+check\b"), "Ngân hàng câu hỏi AI Learning Check.", 8),
    TopicRule("Teacher Review", (r"\bteacher\s+review\b", r"\breview\b", r"\bapprove\b", r"\breject\b", r"\bduyệt\b"), "Luồng giáo viên duyệt, sửa, approve hoặc reject câu hỏi.", 7),
    TopicRule("Cost Control", (r"\bcost\s+control\b", r"\bquota\b", r"\bbudget\b", r"\bhard\s+stop\b", r"\btoken\b", r"\bchi\s+phí\b"), "Kiểm soát token, quota, ngân sách và hard stop.", 8),
    TopicRule("Model Gateway", (r"\bmodel\s+gateway\b", r"\bgpt\b", r"\bgpt-?5\b", r"\bllm\b", r"\bvllm\b"), "Model Gateway để gọi GPT API hoặc local model.", 6),
    TopicRule("Source Grounding", (r"\bsource\s+grounding\b", r"\bsource\s+reference\b", r"\bsource_ref\b", r"\bchunk\b"), "Kiểm tra câu hỏi có nguồn tham chiếu hợp lệ.", 6),
    TopicRule("Duplicate Detection", (r"\bduplicate\b", r"\bembedding\b", r"\bvector\b", r"\bcosine\b"), "Phát hiện câu hỏi trùng bằng embedding/vector similarity.", 6),
)


class TopicService:
    """Topic extraction for MVP with stable, human-friendly topic names.

    v19 originally used single keyword frequency, so the UI could show odd topics
    like "Dùng", "Tải", "Liệu". This version uses controlled phrase rules first,
    then falls back to multi-word terms only. It also cleans old bad auto topics
    when refresh=true is called from the UI.
    """

    def __init__(self, db: Session):
        self.db = db

    def extract_and_assign(self, course_id: str, max_topics: int = 10) -> list[Topic]:
        chunks = self.db.query(ContentChunk).filter(ContentChunk.course_id == course_id).all()
        if not chunks:
            return []

        scores: Counter[str] = Counter()
        summaries: dict[str, str] = {}
        chunk_matches: dict[str, list[str]] = {}

        for chunk in chunks:
            titles = self._match_controlled_topics(chunk)
            if not titles:
                titles = self._fallback_phrase_topics(chunk.content)
            chunk_matches[chunk.id] = titles
            for index, title in enumerate(titles[:4]):
                # Earlier matches from controlled rules get slightly higher weight.
                scores[title] += max(1, 4 - index)
                summaries.setdefault(title, self._summary_for_title(title))

        if not scores:
            scores["Nội dung bài học"] = 1
            summaries["Nội dung bài học"] = "Chủ đề tổng hợp từ nội dung khóa học."

        desired_titles = [title for title, _ in scores.most_common(max_topics)]
        self._cleanup_old_auto_topics(course_id, set(desired_titles))

        existing = {self._canonical_key(topic.title): topic for topic in self.db.query(Topic).filter(Topic.course_id == course_id).all()}
        topics: list[Topic] = []
        for index, title in enumerate(desired_titles, start=1):
            key = self._canonical_key(title)
            topic = existing.get(key)
            if topic is None:
                topic = Topic(
                    course_id=course_id,
                    title=title,
                    summary=summaries.get(title, f"Chủ đề tự động trích xuất từ course content: {title}"),
                    importance_score=max(1, max_topics - index + 1),
                )
                self.db.add(topic)
                self.db.flush()
            else:
                topic.title = title
                topic.summary = summaries.get(title, topic.summary)
            topic.importance_score = max(1, max_topics - index + 1)
            topics.append(topic)

        topic_by_key = {self._canonical_key(topic.title): topic for topic in topics}
        for chunk in chunks:
            matched_titles = chunk_matches.get(chunk.id, [])
            assigned = None
            for title in matched_titles:
                assigned = topic_by_key.get(self._canonical_key(title))
                if assigned:
                    break
            if assigned is None and topics:
                assigned = topics[0]
            if assigned:
                chunk.topic_id = assigned.id

        self.db.commit()
        return topics

    def topic_inputs(self, course_id: str) -> list[dict]:
        topics = self.db.query(Topic).filter(Topic.course_id == course_id).all()
        token_by_topic = defaultdict(int)
        for chunk in self.db.query(ContentChunk).filter(ContentChunk.course_id == course_id).all():
            if chunk.topic_id:
                token_by_topic[chunk.topic_id] += chunk.token_count
        return [{"id": t.id, "title": t.title, "importance_score": t.importance_score, "token_count": token_by_topic[t.id]} for t in topics]

    def _match_controlled_topics(self, chunk: ContentChunk) -> list[str]:
        haystack = "\n".join([
            chunk.content or "",
            chunk.block_id or "",
            chunk.source_ref or "",
            chunk.source_type or "",
        ])
        matched: list[tuple[int, str]] = []
        for rule in TOPIC_RULES:
            for pattern in rule.patterns:
                if re.search(pattern, haystack, flags=re.I | re.U):
                    matched.append((rule.weight, rule.title))
                    break
        # Preserve order by weight desc, dedupe title.
        seen = set()
        output = []
        for _, title in sorted(matched, key=lambda item: item[0], reverse=True):
            if title not in seen:
                output.append(title)
                seen.add(title)
        return output

    def _fallback_phrase_topics(self, text: str) -> list[str]:
        text = text or ""
        # Use 2-3 word phrases only; never allow a single generic token to become a topic.
        tokens = [t.strip("._-").lower() for t in re.findall(r"[A-Za-zÀ-ỹ][\wÀ-ỹ\-\.]{2,}", text)]
        tokens = [t for t in tokens if t and t not in STOPWORDS and not t.isdigit()]
        phrases: Counter[str] = Counter()
        for n in (3, 2):
            for i in range(0, max(0, len(tokens) - n + 1)):
                phrase_tokens = tokens[i:i + n]
                if any(token in STOPWORDS for token in phrase_tokens):
                    continue
                phrase = " ".join(phrase_tokens)
                if self._looks_like_bad_topic(phrase):
                    continue
                phrases[self._humanize_phrase(phrase)] += 1
        return [phrase for phrase, _ in phrases.most_common(3)]

    def _cleanup_old_auto_topics(self, course_id: str, desired_titles: set[str]) -> None:
        desired_keys = {self._canonical_key(title) for title in desired_titles}
        topics = self.db.query(Topic).filter(Topic.course_id == course_id).all()
        bad_topic_ids = []
        for topic in topics:
            key = self._canonical_key(topic.title)
            auto_summary = (topic.summary or "").lower().startswith("chủ đề tự động")
            if topic.title in BAD_AUTO_TOPIC_TITLES or (auto_summary and key not in desired_keys and self._looks_like_bad_topic(topic.title)):
                bad_topic_ids.append(topic.id)
        if not bad_topic_ids:
            return
        self.db.query(ContentChunk).filter(ContentChunk.course_id == course_id, ContentChunk.topic_id.in_(bad_topic_ids)).update({ContentChunk.topic_id: None}, synchronize_session=False)
        for topic in self.db.query(Topic).filter(Topic.id.in_(bad_topic_ids)).all():
            self.db.delete(topic)
        self.db.flush()

    def _summary_for_title(self, title: str) -> str:
        for rule in TOPIC_RULES:
            if rule.title == title:
                return rule.summary
        return f"Chủ đề tự động trích xuất từ course content: {title}"

    def _canonical_key(self, value: str) -> str:
        return re.sub(r"\s+", " ", (value or "").strip().lower())

    def _looks_like_bad_topic(self, value: str) -> bool:
        words = re.findall(r"[A-Za-zÀ-ỹ][\wÀ-ỹ\-\.]*", value or "")
        if not words:
            return True
        if len(words) == 1 and self._canonical_key(words[0]) in STOPWORDS:
            return True
        # Avoid phrases made only from generic Vietnamese words.
        meaningful = [w for w in words if self._canonical_key(w) not in STOPWORDS]
        return len(meaningful) == 0

    def _humanize_phrase(self, phrase: str) -> str:
        aliases = {
            "rest api": "REST API",
            "http methods": "HTTP Methods",
            "entity framework": "Entity Framework",
            "entity framework core": "Entity Framework Core",
            "ef core": "EF Core",
            "dbcontext": "DbContext",
            "db context": "DbContext",
            "open edx": "Open edX",
            "question bank": "Question Bank",
            "cost control": "Cost Control",
            "model gateway": "Model Gateway",
        }
        key = self._canonical_key(phrase)
        if key in aliases:
            return aliases[key]
        return " ".join(word.capitalize() if word.isascii() else word.capitalize() for word in phrase.split())
