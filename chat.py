from pathlib import Path

code = r'''
import re
import copy
import uuid
from datetime import datetime
from collections import defaultdict

import streamlit as st

# ============================================================
# MochiMochi - Scan All Demo
# ============================================================
# Demo features:
#   - Scan with a configurable maximum number of NEW words
#   - Scan All: process the entire text in chunks
#   - Normalize + deduplicate candidates
#   - Detect words already present in Notebook
#   - Preview before saving
#   - Select/unselect individual candidates
#   - Undo the last scan
#
# This demo intentionally does NOT require an AI API.
# Replace extract_candidates_from_chunk() with your AI call later.
# ============================================================

st.set_page_config(
    page_title="MochiMochi - Scan All Demo",
    page_icon="📚",
    layout="wide",
)

# ----------------------------
# Constants
# ----------------------------

MAX_CHARS_PER_CHUNK = 1800

STOPWORDS = {
    "about", "above", "after", "again", "against", "almost", "also",
    "although", "always", "among", "another", "around", "because",
    "before", "being", "below", "between", "both", "could", "during",
    "each", "either", "enough", "every", "first", "from", "further",
    "have", "having", "here", "hers", "himself", "however", "into",
    "itself", "just", "more", "most", "much", "never", "other",
    "others", "over", "same", "should", "since", "some", "such",
    "than", "that", "their", "theirs", "them", "themselves", "then",
    "there", "these", "they", "this", "those", "through", "under",
    "until", "very", "what", "when", "where", "which", "while",
    "with", "would", "your", "yours", "you", "yourself",
    "and", "are", "but", "for", "not", "our", "out", "was", "were",
    "will", "with", "into", "from", "has", "had", "its", "it's",
    "can", "may", "might", "must", "shall", "who", "whose",
}

# A small demo vocabulary/meaning map.
# In the real app, AI/dictionary can provide meaning + IPA + example.
DEMO_MEANINGS = {
    "resilience": ("khả năng phục hồi", "/rɪˈzɪliəns/"),
    "resilient": ("kiên cường; có khả năng phục hồi", "/rɪˈzɪliənt/"),
    "sustainable": ("bền vững", "/səˈsteɪnəbəl/"),
    "sustainability": ("tính bền vững", "/səˌsteɪnəˈbɪləti/"),
    "adaptation": ("sự thích nghi", "/ˌædæpˈteɪʃən/"),
    "adapt": ("thích nghi; điều chỉnh", "/əˈdæpt/"),
    "mitigate": ("giảm nhẹ; làm dịu", "/ˈmɪtɪɡeɪt/"),
    "significant": ("đáng kể; quan trọng", "/sɪɡˈnɪfɪkənt/"),
    "consequence": ("hậu quả", "/ˈkɒnsɪkwens/"),
    "environment": ("môi trường", "/ɪnˈvaɪrənmənt/"),
    "innovation": ("sự đổi mới", "/ˌɪnəˈveɪʃən/"),
    "efficient": ("hiệu quả", "/ɪˈfɪʃənt/"),
    "inequality": ("bất bình đẳng", "/ˌɪnɪˈkwɒləti/"),
    "urbanization": ("đô thị hóa", "/ˌɜːbənaɪˈzeɪʃən/"),
    "biodiversity": ("đa dạng sinh học", "/ˌbaɪəʊdaɪˈvɜːsəti/"),
    "implement": ("triển khai; thực hiện", "/ˈɪmplɪment/"),
    "approach": ("cách tiếp cận", "/əˈprəʊtʃ/"),
    "evidence": ("bằng chứng", "/ˈevɪdəns/"),
    "decline": ("sự suy giảm; suy giảm", "/dɪˈklaɪn/"),
    "enhance": ("nâng cao; tăng cường", "/ɪnˈhɑːns/"),
}

# ----------------------------
# State
# ----------------------------

def init_state():
    defaults = {
        "notebook": [
            {
                "id": "existing-1",
                "word": "resilience",
                "meaning": "khả năng phục hồi",
                "phonetic": "/rɪˈzɪliəns/",
                "example": "Resilience helps people recover from difficult situations.",
                "source": "Notebook",
                "created_at": datetime.now().isoformat(),
            },
            {
                "id": "existing-2",
                "word": "adapt",
                "meaning": "thích nghi; điều chỉnh",
                "phonetic": "/əˈdæpt/",
                "example": "Students need to adapt to new learning environments.",
                "source": "Notebook",
                "created_at": datetime.now().isoformat(),
            },
        ],
        "scan_results": [],
        "scan_session_id": None,
        "scan_preview": False,
        "last_scan_backup": None,
        "last_scan_added_ids": [],
        "last_scan_count": 0,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_state()


# ----------------------------
# Utility
# ----------------------------

def normalize_word(word: str) -> str:
    word = word.strip().lower()
    word = re.sub(r"[^a-zA-Z'-]", "", word)
    return word


def split_into_chunks(text: str, max_chars: int = MAX_CHARS_PER_CHUNK):
    """Split long reading text without cutting words where possible."""
    text = re.sub(r"\s+", " ", text.strip())

    if not text:
        return []

    if len(text) <= max_chars:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = min(start + max_chars, len(text))

        if end < len(text):
            split_at = text.rfind(" ", start, end)
            if split_at > start + max_chars * 0.55:
                end = split_at

        chunks.append(text[start:end].strip())
        start = end

    return [c for c in chunks if c]


def sentence_containing(text: str, word: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text)

    for sentence in sentences:
        if re.search(rf"\b{re.escape(word)}\b", sentence, flags=re.I):
            return sentence.strip()

    return text[:220].strip()


def score_candidate(word: str, chunk: str) -> int:
    """
    Simple demo score.
    In the real app this can be replaced by:
        CEFR + frequency + context importance + AI relevance score
    """
    score = 0

    if word in DEMO_MEANINGS:
        score += 50

    if len(word) >= 8:
        score += 15
    elif len(word) >= 6:
        score += 8

    if word.endswith(("tion", "ment", "ity", "ness", "ance", "ence")):
        score += 10

    return score


def build_candidate(word: str, context: str, session_id: str):
    meaning, ipa = DEMO_MEANINGS.get(
        word,
        ("Chưa có nghĩa — cần AI/dictionary", ""),
    )

    return {
        "id": str(uuid.uuid4()),
        "word": word,
        "meaning": meaning,
        "phonetic": ipa,
        "context": context,
        "example": context,
        "source": "Reading Scan",
        "scan_session_id": session_id,
        "selected": True,
        "score": score_candidate(word, context),
    }


# ----------------------------
# Extraction
# ----------------------------

def extract_candidates_from_chunk(chunk: str, session_id: str):
    """
    Demo extractor.

    It first prefers words from DEMO_MEANINGS, then adds longer
    English words. Replace this function with the actual AI batch
    request in the production app.
    """
    words = re.findall(r"\b[A-Za-z][A-Za-z'-]{3,}\b", chunk)

    counts = defaultdict(int)
    for raw in words:
        word = normalize_word(raw)

        if not word:
            continue
        if word in STOPWORDS:
            continue
        if len(word) < 5:
            continue

        counts[word] += 1

    candidates = []

    for word, count in counts.items():
        # Demo heuristic:
        # known demo words OR relatively uncommon-looking long words
        if word not in DEMO_MEANINGS and len(word) < 8:
            continue

        context = sentence_containing(chunk, word)
        candidate = build_candidate(word, context, session_id)
        candidate["occurrences"] = count
        candidate["score"] += min(count * 3, 12)
        candidates.append(candidate)

    candidates.sort(key=lambda x: (-x["score"], x["word"]))

    return candidates


# ----------------------------
# Dedup / merge
# ----------------------------

def notebook_index():
    """
    Build:
      word -> list of existing notebook items

    We intentionally keep multiple senses.
    """
    index = defaultdict(list)

    for item in st.session_state.notebook:
        index[normalize_word(item.get("word", ""))].append(item)

    return index


def semantic_key(word: str, meaning: str):
    """
    A safe-ish duplicate key for the demo:
        same word + same normalized meaning

    Different meanings are NOT automatically merged.
    """
    return (
        normalize_word(word),
        re.sub(r"\s+", " ", meaning.strip().lower()),
    )


def deduplicate_candidates(candidates):
    """
    Merge exact duplicates produced by different chunks.

    If the same word appears with different contexts, keep one item
    but preserve multiple contexts.
    """
    grouped = {}

    for item in candidates:
        key = semantic_key(item["word"], item["meaning"])

        if key not in grouped:
            item = copy.deepcopy(item)
            item["contexts"] = [item["context"]]
            grouped[key] = item
        else:
            current = grouped[key]

            if item["context"] not in current["contexts"]:
                current["contexts"].append(item["context"])

            current["occurrences"] = (
                current.get("occurrences", 0)
                + item.get("occurrences", 0)
            )

            current["score"] = max(
                current.get("score", 0),
                item.get("score", 0),
            )

    result = list(grouped.values())

    for item in result:
        item["context_count"] = len(item["contexts"])

    result.sort(
        key=lambda x: (
            -x.get("score", 0),
            -x.get("occurrences", 0),
            x["word"],
        )
    )

    return result


def compare_with_notebook(candidates):
    index = notebook_index()

    for item in candidates:
        word = normalize_word(item["word"])
        existing = index.get(word, [])

        item["already_exists"] = bool(existing)

        # Exact same word + meaning
        item["exact_duplicate"] = any(
            semantic_key(x.get("word", ""), x.get("meaning", ""))
            == semantic_key(item["word"], item["meaning"])
            for x in existing
        )

        item["existing_items"] = existing

        # Default:
        # exact duplicate -> don't select
        # same word but different meaning -> select for user review
        if item["exact_duplicate"]:
            item["selected"] = False
        else:
            item["selected"] = True

    return candidates


# ----------------------------
# Scan
# ----------------------------

def perform_scan(text: str, mode: str, limit: int):
    session_id = str(uuid.uuid4())

    chunks = split_into_chunks(text)

    all_candidates = []

    progress = st.progress(0)
    status = st.empty()

    total = len(chunks)

    for i, chunk in enumerate(chunks, start=1):
        status.write(f"🔎 Đang quét chunk {i}/{total}...")

        candidates = extract_candidates_from_chunk(
            chunk,
            session_id,
        )

        all_candidates.extend(candidates)
        progress.progress(i / total)

    progress.empty()
    status.empty()

    candidates = deduplicate_candidates(all_candidates)
    candidates = compare_with_notebook(candidates)

    if mode == "Giới hạn":
        # Limit means final candidate count, not chunk count.
        candidates = candidates[:limit]

    return session_id, candidates


def save_selected_candidates():
    selected = [
        x
        for x in st.session_state.scan_results
        if x.get("selected")
    ]

    if not selected:
        return 0

    # Backup BEFORE mutation.
    st.session_state.last_scan_backup = copy.deepcopy(
        st.session_state.notebook
    )

    added_ids = []

    for item in selected:
        # Never add exact duplicate.
        if item.get("exact_duplicate"):
            continue

        new_item = {
            "id": str(uuid.uuid4()),
            "word": item["word"],
            "meaning": item["meaning"],
            "phonetic": item.get("phonetic", ""),
            "example": item.get("example", ""),
            "source": "Reading Scan",
            "source_contexts": item.get(
                "contexts",
                [item.get("context", "")],
            ),
            "created_at": datetime.now().isoformat(),
            "level": 0,
            "hook": 1,
            "review_count": 0,
            "correct_count": 0,
            "wrong_count": 0,
            "pending_ai_example": True,
            "scan_session_id": st.session_state.scan_session_id,
        }

        st.session_state.notebook.append(new_item)
        added_ids.append(new_item["id"])

    st.session_state.last_scan_added_ids = added_ids
    st.session_state.last_scan_count = len(added_ids)

    # Clear preview after save.
    st.session_state.scan_results = []
    st.session_state.scan_preview = False

    return len(added_ids)


def undo_last_scan():
    backup = st.session_state.last_scan_backup

    if backup is None:
        return False

    st.session_state.notebook = backup
    st.session_state.last_scan_backup = None
    st.session_state.last_scan_added_ids = []
    st.session_state.last_scan_count = 0

    return True


# ----------------------------
# UI
# ----------------------------

st.title("📚 MochiMochi — Scan All Demo")
st.caption(
    "Demo kiến trúc Scan All: chunk → extract → deduplicate → "
    "compare Notebook → preview → save → undo."
)

with st.sidebar:
    st.header("⚙️ Scan")

    mode = st.radio(
        "Chế độ",
        ["Giới hạn", "Scan All"],
        index=0,
    )

    limit = st.selectbox(
        "Số từ tối đa",
        [10, 20, 50, 100, 200],
        index=1,
        disabled=(mode == "Scan All"),
    )

    st.divider()

    st.metric("Từ trong Sổ Tay", len(st.session_state.notebook))

    if st.session_state.last_scan_count:
        st.success(
            f"Scan gần nhất đã thêm "
            f"{st.session_state.last_scan_count} từ."
        )

    if st.session_state.last_scan_backup is not None:
        if st.button("↩️ Undo lần scan", use_container_width=True):
            undo_last_scan()
            st.success("Đã hoàn tác lần scan.")
            st.rerun()


sample_text = """
Modern societies face significant environmental and social challenges.
Sustainable development requires resilience, adaptation, innovation, and
efficient approaches to resource management. Governments can implement
policies that mitigate the consequences of climate change while protecting
biodiversity. However, rapid urbanization may increase inequality if public
services cannot adapt to changing conditions.

Long-term sustainability depends on evidence-based decisions. Communities
need resilience because unexpected events can disrupt infrastructure,
education, healthcare, and employment. Effective adaptation can reduce risk,
while innovation can enhance efficiency and create new opportunities.
"""

text = st.text_area(
    "📖 Dán bài đọc tiếng Anh",
    value=sample_text.strip(),
    height=280,
)

col1, col2, col3 = st.columns([1.2, 1, 1])

with col1:
    scan_button = st.button(
        "🔎 Scan All" if mode == "Scan All" else "🔎 Scan",
        type="primary",
        use_container_width=True,
    )

with col2:
    if st.button(
        "🧹 Xóa kết quả",
        use_container_width=True,
    ):
        st.session_state.scan_results = []
        st.session_state.scan_preview = False
        st.rerun()

with col3:
    if st.button(
        "📚 Xem Sổ Tay",
        use_container_width=True,
    ):
        st.session_state["show_notebook"] = not st.session_state.get(
            "show_notebook",
            False,
        )

if scan_button:
    if not text.strip():
        st.warning("Hãy nhập bài đọc trước.")
    else:
        with st.spinner(
            "Scan All đang chia bài đọc thành nhiều chunk và xử lý..."
        ):
            session_id, results = perform_scan(
                text=text,
                mode=mode,
                limit=limit,
            )

        st.session_state.scan_session_id = session_id
        st.session_state.scan_results = results
        st.session_state.scan_preview = True

        st.rerun()


# ----------------------------
# Preview
# ----------------------------

if st.session_state.scan_preview:

    results = st.session_state.scan_results

    st.divider()
    st.subheader("🔍 Preview trước khi thêm vào Sổ Tay")

    total = len(results)
    selected = sum(
        1 for x in results if x.get("selected")
    )
    exact_duplicates = sum(
        1 for x in results if x.get("exact_duplicate")
    )
    existing_words = sum(
        1 for x in results if x.get("already_exists")
    )

    m1, m2, m3, m4 = st.columns(4)

    m1.metric("Ứng viên", total)
    m2.metric("Đang chọn", selected)
    m3.metric("Đã có trong Sổ Tay", existing_words)
    m4.metric("Duplicate chính xác", exact_duplicates)

    if mode == "Scan All":
        st.info(
            "🌐 Scan All đã xử lý toàn bộ bài đọc theo từng chunk. "
            "Kết quả đã được gộp trước khi hiển thị."
        )

    if not results:
        st.warning("Không tìm thấy từ phù hợp.")
    else:
        st.write("### Các từ tìm được")

        # Global controls
        c1, c2, c3 = st.columns(3)

        with c1:
            if st.button(
                "☑️ Chọn tất cả từ mới",
                use_container_width=True,
            ):
                for item in st.session_state.scan_results:
                    if not item.get("exact_duplicate"):
                        item["selected"] = True
                st.rerun()

        with c2:
            if st.button(
                "☐ Bỏ chọn tất cả",
                use_container_width=True,
            ):
                for item in st.session_state.scan_results:
                    item["selected"] = False
                st.rerun()

        with c3:
            if st.button(
                "⭐ Chỉ chọn từ ưu tiên",
                use_container_width=True,
            ):
                for item in st.session_state.scan_results:
                    item["selected"] = (
                        not item.get("exact_duplicate")
                        and item.get("score", 0) >= 20
                    )
                st.rerun()

        st.divider()

        # Individual candidates
        for idx, item in enumerate(
            st.session_state.scan_results
        ):
            word = item["word"]

            if item.get("exact_duplicate"):
                status = "🔴 Duplicate chính xác"
            elif item.get("already_exists"):
                status = "🟡 Đã có từ này — khác nghĩa/context"
            else:
                status = "🟢 Từ mới"

            cols = st.columns([0.55, 1.25, 2.2, 2.8, 1])

            with cols[0]:
                new_value = st.checkbox(
                    "Chọn",
                    value=item.get("selected", False),
                    key=f"candidate_{item['id']}",
                    disabled=item.get("exact_duplicate", False),
                    label_visibility="collapsed",
                )

                item["selected"] = new_value

            with cols[1]:
                st.markdown(f"**{word}**")
                st.caption(status)

            with cols[2]:
                st.write(item.get("meaning", ""))
                if item.get("phonetic"):
                    st.caption(item["phonetic"])

            with cols[3]:
                contexts = item.get("contexts", [])
                if contexts:
                    st.caption(
                        "Context: "
                        + contexts[0][:180]
                    )

                    if len(contexts) > 1:
                        st.caption(
                            f"📚 Xuất hiện trong "
                            f"{len(contexts)} context"
                        )

            with cols[4]:
                st.metric(
                    "Score",
                    item.get("score", 0),
                )

        st.divider()

        selected_count = sum(
            1
            for x in st.session_state.scan_results
            if x.get("selected")
        )

        save_col1, save_col2 = st.columns([2, 1])

        with save_col1:
            if st.button(
                f"📥 Thêm {selected_count} từ vào Sổ Tay",
                type="primary",
                disabled=(selected_count == 0),
                use_container_width=True,
            ):
                count = save_selected_candidates()

                if count:
                    st.success(
                        f"Đã thêm {count} từ. "
                        "Các từ này đã được đánh dấu pending AI example."
                    )
                else:
                    st.warning(
                        "Không có từ mới hợp lệ để thêm."
                    )

                st.rerun()

        with save_col2:
            st.caption(
                "💡 Duplicate chính xác sẽ không được thêm "
                "lại vào Sổ Tay."
            )


# ----------------------------
# Notebook
# ----------------------------

if st.session_state.get("show_notebook", False):

    st.divider()
    st.subheader("📚 Sổ Tay")

    search = st.text_input(
        "🔎 Tìm trong Sổ Tay",
        key="notebook_search",
    )

    filtered = st.session_state.notebook

    if search.strip():
        q = search.strip().lower()
        filtered = [
            x
            for x in filtered
            if q in x.get("word", "").lower()
            or q in x.get("meaning", "").lower()
        ]

    st.write(
        f"Hiển thị **{len(filtered)} / "
        f"{len(st.session_state.notebook)}** từ."
    )

    for item in filtered:
        with st.expander(
            f"{item.get('word', '')} — "
            f"{item.get('meaning', '')}"
        ):
            st.write(
                f"**IPA:** {item.get('phonetic', '')}"
            )

            st.write(
                f"**Example:** {item.get('example', '')}"
            )

            contexts = item.get("source_contexts", [])

            if contexts:
                st.write("**Context từ bài đọc:**")
                for context in contexts[:5]:
                    st.caption("• " + context)

            st.caption(
                f"Level: {item.get('level', 0)} | "
                f"Hook: {item.get('hook', 1)} | "
                f"Reviews: {item.get('review_count', 0)}"
            )

            if item.get("pending_ai_example"):
                st.info(
                    "🤖 Example đang chờ AI adaptive generation."
                )


# ----------------------------
# Architecture notes
# ----------------------------

with st.expander("🧠 Kiến trúc production nên dùng"):
    st.markdown(
        """
### Scan All

```text
Reading
   ↓
Normalize
   ↓
Chunk
   ↓
AI extraction từng chunk
   ↓
Validate JSON
   ↓
Merge/Deduplicate
   ↓
Compare Notebook
   ├── Exact duplicate → bỏ chọn
   ├── Same word / different meaning → cảnh báo
   └── New word → chọn mặc định
   ↓
Preview
   ↓
User approve
   ↓
Save batch
   ↓
scan_session_id
   ↓
Undo
