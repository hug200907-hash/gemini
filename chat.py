import streamlit as st
import sqlite3
import json
import random
import re
import requests
from datetime import datetime, timedelta
import math

# ==============================================================================
# CONFIG & CONSTANTS
# ==============================================================================
DB_FILE = "vocab.db"
DEFAULT_MODEL = "minimax/minimax-m3:free"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

st.set_page_config(
    page_title="Vocab Conquest - Game-based SRS",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS cho Dark Mode UI & Gamification
st.markdown("""
<style>
    .stApp {
        background-color: #121214;
        color: #e1e1e6;
    }
    .main-card {
        background-color: #202024;
        border-radius: 12px;
        padding: 24px;
        border: 1px solid #323238;
        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        margin-bottom: 20px;
    }
    .stat-badge {
        background: linear-gradient(135deg, #2b2b36 0%, #1e1e24 100%);
        border: 1px solid #4d4d57;
        padding: 12px;
        border-radius: 10px;
        text-align: center;
    }
    .xp-bar {
        background-color: #29292e;
        border-radius: 8px;
        height: 12px;
        width: 100%;
        overflow: hidden;
    }
    .xp-fill {
        background: linear-gradient(90deg, #00b4d8 0%, #7209b7 100%);
        height: 100%;
        transition: width 0.3s ease;
    }
    .correct-box {
        background-color: #1b382b;
        border: 1px solid #2ecc71;
        padding: 16px;
        border-radius: 8px;
        margin-top: 10px;
    }
    .wrong-box {
        background-color: #3d1e24;
        border: 1px solid #e74c3c;
        padding: 16px;
        border-radius: 8px;
        margin-top: 10px;
    }
    .stButton>button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.2s ease;
    }
    .stButton>button:hover {
        transform: translateY(-2px);
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# DATABASE LAYER
# ==============================================================================
def get_db_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS words (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        word TEXT UNIQUE NOT NULL,
        normalized_word TEXT NOT NULL,
        vietnamese_meaning TEXT,
        english_definition TEXT,
        example_sentence TEXT,
        pronunciation TEXT,
        phonetic TEXT,
        topic TEXT DEFAULT 'General',
        difficulty INTEGER DEFAULT 20,
        first_learned_at DATETIME,
        last_review_at DATETIME,
        next_review_at DATETIME,
        correct_count INTEGER DEFAULT 0,
        wrong_count INTEGER DEFAULT 0,
        total_reviews INTEGER DEFAULT 0,
        last_question_type TEXT,
        current_streak INTEGER DEFAULT 0,
        learning_state TEXT DEFAULT 'NEW'
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        word_id INTEGER,
        question_type TEXT,
        user_answer TEXT,
        is_correct INTEGER,
        difficulty_before INTEGER,
        difficulty_after INTEGER,
        reviewed_at DATETIME
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reading_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        topic TEXT,
        passage TEXT,
        user_translation TEXT,
        accuracy INTEGER,
        comprehension INTEGER,
        feedback TEXT,
        reviewed_at DATETIME,
        next_review_at DATETIME
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        word_id INTEGER,
        question_type TEXT,
        reason TEXT,
        details TEXT,
        created_at DATETIME
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_stats (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        xp INTEGER DEFAULT 0,
        streak INTEGER DEFAULT 0,
        last_activity_date TEXT,
        level INTEGER DEFAULT 1
    )
    """)
    
    cursor.execute("INSERT OR IGNORE INTO user_stats (id, xp, streak, level) VALUES (1, 0, 0, 1)")
    conn.commit()
    conn.close()

init_db()

# ==============================================================================
# OPENROUTER AI LAYER
# ==============================================================================
def call_ai(prompt: str, system_prompt: str = "You are a helpful AI language expert.", json_mode: bool = True) -> dict | str:
    api_key = st.secrets.get("OPENROUTER_API_KEY", "")
    if not api_key:
        st.error("⚠️ Chưa tìm thấy OPENROUTER_API_KEY trong Streamlit Secrets!")
        return {} if json_mode else "Lỗi API Key"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://streamlit.io",
        "X-Title": "VocabConquest"
    }

    payload = {
        "model": DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3
    }
    
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    for attempt in range(2):
        try:
            res = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=25)
            if res.status_code == 200:
                content = res.json()["choices"][0]["message"]["content"].strip()
                if json_mode:
                    # Clean potential markdown wrapping
                    if content.startswith("```json"):
                        content = re.sub(r"^```json\s*", "", content)
                        content = re.sub(r"\s*```$", "", content)
                    return json.loads(content)
                return content
        except Exception as e:
            if attempt == 1:
                st.warning(f"AI Connection error: {str(e)}")
    
    return {} if json_mode else "AI Service Unreachable"

# ==============================================================================
# ALGORITHMS: HINT, SRS, GAMIFICATION
# ==============================================================================
def generate_smart_hint(word: str, difficulty: int) -> str:
    """Reveals vowels first, then consonants near long vowels, scaled by difficulty (0-100)."""
    n = len(word)
    if n <= 2:
        return "_ " * n
    
    # Reveal percentage: low difficulty = more visible letters (up to 70%), high = less (min 20%)
    reveal_pct = max(0.2, min(0.7, 1.0 - (difficulty / 100.0)))
    reveal_count = max(1, math.ceil(n * reveal_pct))
    
    vowels = set("aeiouAEIOU")
    indices = list(range(n))
    
    # Priority score: Vowels get priority 2, adjacent to vowels get 1, rest 0
    scores = []
    for idx in indices:
        char = word[idx]
        if char.lower() in vowels:
            scores.append((2, idx))
        elif (idx > 0 and word[idx-1].lower() in vowels) or (idx < n-1 and word[idx+1].lower() in vowels):
            scores.append((1, idx))
        else:
            scores.append((0, idx))
            
    # Sort indices by score descending
    scores.sort(key=lambda x: x[0], reverse=True)
    revealed_indices = set(x[1] for x in scores[:reveal_count])
    
    hint_chars = []
    for i, char in enumerate(word):
        if i in revealed_indices or not char.isalpha():
            hint_chars.append(char)
        else:
            hint_chars.append("_")
            
    return " ".join(hint_chars)

def update_word_srs(word_id: int, is_correct: bool):
    """Custom fast-paced Short-Term Spaced Repetition (Intervals ~1/10th of traditional Anki)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM words WHERE id = ?", (word_id,))
    word = cursor.fetchone()
    if not word:
        conn.close()
        return

    diff = word["difficulty"]
    streak = word["current_streak"]
    now = datetime.now()

    if is_correct:
        new_diff = min(100, diff + 7)
        new_streak = streak + 1
        # Short intervals (minutes): 10m -> 30m -> 2h -> 8h -> 24h -> 3 days
        base_mins = 10 * (2.5 ** min(new_streak, 5))
    else:
        new_diff = max(5, diff - 10)
        new_streak = 0
        base_mins = 8  # Wrong words come back in ~8 mins

    # 10% jitter to prevent block predictabilities
    jitter = random.uniform(0.9, 1.1)
    final_mins = max(5, int(base_mins * jitter))
    next_review = now + timedelta(minutes=final_mins)

    # Determine State
    if new_streak >= 5 and new_diff > 70:
        state = "MASTERED"
    elif new_streak >= 1:
        state = "REVIEW"
    else:
        state = "LEARNING"

    cursor.execute("""
        UPDATE words SET
            difficulty = ?,
            current_streak = ?,
            correct_count = correct_count + ?,
            wrong_count = wrong_count + ?,
            total_reviews = total_reviews + 1,
            last_review_at = ?,
            next_review_at = ?,
            learning_state = ?
        WHERE id = ?
    """, (
        new_diff,
        new_streak,
        1 if is_correct else 0,
        0 if is_correct else 1,
        now.strftime("%Y-%m-%d %H:%M:%S"),
        next_review.strftime("%Y-%m-%d %H:%M:%S"),
        state,
        word_id
    ))
    
    # Record Review
    cursor.execute("""
        INSERT INTO reviews (word_id, question_type, user_answer, is_correct, difficulty_before, difficulty_after, reviewed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (word_id, word["last_question_type"] or "quiz", "submitted", 1 if is_correct else 0, diff, new_diff, now.strftime("%Y-%m-%d %H:%M:%S")))

    # Update Gamification XP
    xp_gain = 15 if (is_correct and diff > 50) else (10 if is_correct else 2)
    cursor.execute("UPDATE user_stats SET xp = xp + ? WHERE id = 1", (xp_gain,))

    conn.commit()
    conn.close()

def text_to_speech_html(en_word: str, vn_meaning: str = "", autoplay: bool = True):
    """HTML JS Web Speech API wrapper for low-latency browser audio playback."""
    clean_en = en_word.replace("'", "\\'").replace('"', '\\"')
    clean_vn = vn_meaning.replace("'", "\\'").replace('"', '\\"')
    
    js_code = f"""
    <script>
    function speakVocab() {{
        if ('speechSynthesis' in window) {{
            window.speechSynthesis.cancel();
            
            let msgEn = new SpeechSynthesisUtterance("{clean_en}");
            msgEn.lang = 'en-US';
            msgEn.rate = 0.9;
            
            msgEn.onend = function() {{
                if ("{clean_vn}".length > 0) {{
                    setTimeout(() => {{
                        let msgVn = new SpeechSynthesisUtterance("{clean_vn}");
                        msgVn.lang = 'vi-VN';
                        msgVn.rate = 1.0;
                        window.speechSynthesis.speak(msgVn);
                    }}, 200);
                }}
            }};
            
            window.speechSynthesis.speak(msgEn);
        }}
    }}
    {'speakVocab();' if autoplay else ''}
    </script>
    <button onclick="speakVocab()" style="
        background: #2b2b36; border: 1px solid #4d4d57; color: #fff;
        padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 14px;">
        🔊 Nghe phát âm ({clean_en})
    </button>
    """
    st.components.v1.html(js_code, height=50)

# ==============================================================================
# TAB 1 — SCAN TEXT
# ==============================================================================
def render_tab_scan():
    st.markdown("### 📥 Quét văn bản & Trích xuất từ mới")
    text_input = st.text_area("Dán đoạn văn tiếng Anh bạn muốn đọc/học tại đây:", height=180, placeholder="Paste English text here...")
    
    if st.button("🔎 SCAN TỪ MỚI", type="primary"):
        if not text_input.strip():
            st.warning("Vui lòng nhập đoạn văn bản.")
            return

        with st.spinner("🤖 AI đang phân tích ngữ cảnh và lọc từ mới..."):
            # Fetch existing words to exclude
            conn = get_db_connection()
            existing = set(r["word"].lower() for r in conn.execute("SELECT word FROM words").fetchall())
            conn.close()

            prompt = f"""
            Analyze the following text and extract potential new vocabulary words for an English learner.
            Filter OUT:
            1. Commonly known basic words (is, are, the, apple, run, simple words).
            2. Words already in this list: {list(existing)[:100]}
            
            Text: "{text_input}"

            Return JSON format:
            {{
                "extracted_words": [
                    {{
                        "word": "canonical form of word",
                        "vietnamese_meaning": "accurate context meaning in Vietnamese",
                        "english_definition": "simple 1-sentence English definition",
                        "phonetic": "/IPA/",
                        "example_sentence": "Very simple sentence for beginner",
                        "topic": "General/Tech/Business etc."
                    }}
                ]
            }}
            """
            
            res = call_ai(prompt, system_prompt="You are an expert lexicographer making easy-to-understand flashcards.")
            words_data = res.get("extracted_words", [])

            if not words_data:
                st.info("Không tìm thấy từ mới phù hợp hoặc tất cả các từ đã có trong sổ tay!")
                return

            conn = get_db_connection()
            cursor = conn.cursor()
            added_count = 0
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            for item in words_data:
                w = item["word"].strip()
                if not w or w.lower() in existing:
                    continue
                
                cursor.execute("""
                    INSERT OR IGNORE INTO words 
                    (word, normalized_word, vietnamese_meaning, english_definition, example_sentence, phonetic, topic, difficulty, first_learned_at, next_review_at, learning_state)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 15, ?, ?, 'NEW')
                """, (
                    w, w.lower(),
                    item.get("vietnamese_meaning", ""),
                    item.get("english_definition", ""),
                    item.get("example_sentence", f"I use {w} every day."),
                    item.get("phonetic", ""),
                    item.get("topic", "General"),
                    now_str, now_str
                ))
                added_count += 1
            
            conn.commit()
            conn.close()
            st.success(f"🎉 Đã quét xong! Thêm thành công {added_count} từ mới vào sổ tay học.")
            
            st.markdown("#### 📋 Danh sách từ vừa nạp:")
            for item in words_data:
                with st.expander(f"✨ **{item['word']}** `{item.get('phonetic', '')}` — {item.get('vietnamese_meaning', '')}"):
                    st.write(f"**Định nghĩa:** {item.get('english_definition')}")
                    st.write(f"**Ví dụ dễ:** *{item.get('example_sentence')}*")
                    st.caption(f"Topic: {item.get('topic')} | initial difficulty: 15/100")

# ==============================================================================
# TAB 2 — ÔN TẬP (CORE GAMIFIED SRS)
# ==============================================================================
def render_tab_review():
    conn = get_db_connection()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Metrics Overview
    due_count = conn.execute("SELECT COUNT(*) FROM words WHERE next_review_at <= ? OR learning_state = 'NEW'", (now_str,)).fetchone()[0]
    total_count = conn.execute("SELECT COUNT(*) FROM words").fetchone()[0]
    stats = conn.execute("SELECT * FROM user_stats WHERE id = 1").fetchone()
    conn.close()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f"<div class='stat-badge'>🔥 <b>Streak:</b> {stats['streak']} ngày</div>", unsafe_allow_html=True)
    with col2:
        st.markdown(f"<div class='stat-badge'>⚡ <b>XP:</b> {stats['xp']}</div>", unsafe_allow_html=True)
    with col3:
        st.markdown(f"<div class='stat-badge'>⏳ <b>Đến hạn ôn:</b> {due_count} từ</div>", unsafe_allow_html=True)
    with col4:
        st.markdown(f"<div class='stat-badge'>📚 <b>Tổng số từ:</b> {total_count}</div>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Initialize Session State Variables
    if "review_session_active" not in st.session_state:
        st.session_state.review_session_active = False
        st.session_state.session_words = []
        st.session_state.session_idx = 0
        st.session_state.current_q = None
        st.session_state.answer_submitted = False
        st.session_state.session_results = []

    # START SCREEN OR ACTIVE SESSION
    if not st.session_state.review_session_active:
        st.markdown("<div class='main-card' style='text-align: center;'>", unsafe_allow_html=True)
        if due_count > 0:
            st.markdown("## 🎯 Sẵn sàng chinh phục bài ôn tập ngắn?")
            st.write("Mỗi lượt chỉ 5 từ — nhanh chóng, vừa sức, khắc sâu trí nhớ!")
            if st.button("🔥 BẮT ĐẦU ÔN (5 TỪ)", type="primary", use_container_width=True):
                # Fetch 5 words prioritizing wrong/due words
                conn = get_db_connection()
                words = conn.execute("""
                    SELECT * FROM words 
                    WHERE next_review_at <= ? OR learning_state = 'NEW'
                    ORDER BY 
                        CASE WHEN wrong_count > correct_count THEN 1 ELSE 2 END,
                        next_review_at ASC
                    LIMIT 5
                """, (now_str,)).fetchall()
                conn.close()

                if words:
                    st.session_state.session_words = [dict(w) for w in words]
                    st.session_state.session_idx = 0
                    st.session_state.review_session_active = True
                    st.session_state.session_results = []
                    st.session_state.answer_submitted = False
                    st.session_state.current_q = None
                    st.rerun()
        else:
            # Countdown view when no reviews are due
            conn = get_db_connection()
            next_word = conn.execute("SELECT next_review_at FROM words WHERE next_review_at > ? ORDER BY next_review_at ASC LIMIT 1", (now_str,)).fetchone()
            conn.close()
            
            st.markdown("🎉 **Bạn đã hoàn thiện tất cả các lượt ôn tới thời điểm này!**")
            if next_word and next_word["next_review_at"]:
                st.info(f"⏳ Lượt ôn tiếp theo sẵn sàng vào lúc: `{next_word['next_review_at']}`")
            else:
                st.write("Hãy sang Tab **📥 Scan từ mới** để nạp thêm từ!")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    # ACTIVE QUESTION SESSION
    session_words = st.session_state.session_words
    idx = st.session_state.session_idx

    if idx >= len(session_words):
        # SESSION FINISHED SCREEN
        st.markdown("<div class='main-card' style='text-align: center;'>", unsafe_allow_html=True)
        st.balloons()
        st.markdown("## 🎉 SESSION COMPLETE!")
        st.write(f"Bạn đã vượt qua **{len(session_words)}/{len(session_words)}** từ trong lượt này!")
        
        corrects = sum(1 for r in st.session_state.session_results if r['is_correct'])
        wrongs = len(session_words) - corrects
        acc = int((corrects / len(session_words)) * 100) if session_words else 0
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Đúng", f"{corrects} từ")
        c2.metric("Sai / Quên", f"{wrongs} từ")
        c3.metric("Chính xác", f"{acc}%")

        if st.button("🚀 XÁC NHẬN & QUAY VỀ", type="primary"):
            st.session_state.review_session_active = False
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
        return

    # Render Current Question
    current_word = session_words[idx]
    
    # Generate question object once per index
    if st.session_state.current_q is None:
        q_types = ["context_fill", "mcq_vn_to_en", "listening_meaning", "spelling", "phonetic_mcq"]
        q_type = random.choice(q_types)
        
        # Save last question type in DB
        conn = get_db_connection()
        conn.execute("UPDATE words SET last_question_type = ? WHERE id = ?", (q_type, current_word["id"]))
        conn.commit()
        conn.close()

        # Build distractor options if needed
        conn = get_db_connection()
        other_words = [r["word"] for r in conn.execute("SELECT word FROM words WHERE id != ? ORDER BY RANDOM() LIMIT 3", (current_word["id"],)).fetchall()]
        other_phonetics = [r["phonetic"] for r in conn.execute("SELECT phonetic FROM words WHERE id != ? AND phonetic != '' ORDER BY RANDOM() LIMIT 3", (current_word["id"],)).fetchall()]
        conn.close()

        while len(other_words) < 3:
            other_words.append("sample")
        while len(other_phonetics) < 3:
            other_phonetics.append("/ˈsæmpəl/")

        st.session_state.current_q = {
            "type": q_type,
            "word": current_word,
            "other_words": other_words,
            "other_phonetics": other_phonetics,
            "hint": generate_smart_hint(current_word["word"], current_word["difficulty"])
        }

    q = st.session_state.current_q
    w_obj = q["word"]

    st.markdown(f"#### 🎯 Câu {idx + 1} / {len(session_words)} — [Chế độ: {q['type'].upper()}]")
    st.progress((idx + 1) / len(session_words))

    st.markdown("<div class='main-card'>", unsafe_allow_html=True)
    
    user_answer = ""
    is_correct = False

    # Render 5 Specific Question Types
    if q["type"] == "context_fill":
        st.write(f"**Điền từ còn thiếu vào câu:**")
        sentence = w_obj["example_sentence"]
        # Replace target word with blank
        pattern = re.compile(re.escape(w_obj["word"]), re.IGNORECASE)
        blanked_sentence = pattern.sub("_______", sentence)
        
        st.markdown(f"### *\"{blanked_sentence}\"*")
        st.caption(f"💡 Gợi ý chữ: `{q['hint']}`")
        user_answer = st.text_input("Nhập từ tiếng Anh:", key=f"q_{idx}")

    elif q["type"] == "mcq_vn_to_en":
        st.write("**Chọn từ tiếng Anh phù hợp với nghĩa:**")
        st.markdown(f"## 🇻🇳 **\"{w_obj['vietnamese_meaning']}\"**")
        options = [w_obj["word"]] + q["other_words"]
        random.seed(w_obj["id"])
        random.shuffle(options)
        user_answer = st.radio("Lựa chọn của bạn:", options, key=f"q_{idx}")

    elif q["type"] == "listening_meaning":
        st.write("**Nghe âm thanh và chọn đúng nghĩa tiếng Việt:**")
        text_to_speech_html(w_obj["word"], autoplay=False)
        st.markdown(f"### 🔊 Từ vừa nghe có nghĩa là gì?")
        
        # Distractor meanings
        conn = get_db_connection()
        other_means = [r["vietnamese_meaning"] for r in conn.execute("SELECT vietnamese_meaning FROM words WHERE id != ? LIMIT 3", (w_obj["id"],)).fetchall()]
        conn.close()
        while len(other_means) < 3: other_means.append("Khác")
        
        options = [w_obj["vietnamese_meaning"]] + other_means
        random.shuffle(options)
        user_answer = st.radio("Chọn nghĩa đúng:", options, key=f"q_{idx}")

    elif q["type"] == "spelling":
        st.write("**Nghe từ và viết lại chính tả chính xác:**")
        text_to_speech_html(w_obj["word"], autoplay=True)
        st.caption(f"💡 Gợi ý chữ: `{q['hint']}`")
        user_answer = st.text_input("Viết chính tả từ bạn nghe được:", key=f"q_{idx}")

    elif q["type"] == "phonetic_mcq":
        st.write(f"**Chọn phiên âm đúng (IPA) cho từ:**")
        st.markdown(f"## **{w_obj['word']}** *(Nghĩa: {w_obj['vietnamese_meaning']})*")
        
        correct_ipa = w_obj["phonetic"] if w_obj["phonetic"] else "/ˈdemo/"
        options = [correct_ipa] + q["other_phonetics"]
        random.shuffle(options)
        user_answer = st.radio("Chọn IPA đúng:", options, key=f"q_{idx}")

    col_btn1, col_btn2, col_btn3 = st.columns([2, 2, 2])

    with col_btn1:
        if st.button("Nộp bài", type="primary", key=f"sub_{idx}", disabled=st.session_state.answer_submitted):
            st.session_state.answer_submitted = True
            
            # Answer Evaluation Logic
            ans_clean = str(user_answer).strip().lower()
            if q["type"] in ["context_fill", "spelling"]:
                is_correct = (ans_clean == w_obj["word"].strip().lower())
            elif q["type"] == "mcq_vn_to_en":
                is_correct = (ans_clean == w_obj["word"].strip().lower())
            elif q["type"] == "listening_meaning":
                is_correct = (ans_clean == w_obj["vietnamese_meaning"].strip().lower())
            elif q["type"] == "phonetic_mcq":
                correct_ipa = w_obj["phonetic"] if w_obj["phonetic"] else "/ˈdemo/"
                is_correct = (ans_clean == correct_ipa.strip().lower())

            update_word_srs(w_obj["id"], is_correct)
            st.session_state.session_results.append({"word": w_obj["word"], "is_correct": is_correct})
            st.rerun()

    with col_btn2:
        if st.button("😵 Quên từ", key=f"forget_{idx}", disabled=st.session_state.answer_submitted):
            st.session_state.answer_submitted = True
            update_word_srs(w_obj["id"], is_correct=False)
            st.session_state.session_results.append({"word": w_obj["word"], "is_correct": False})
            st.rerun()

    with col_btn3:
        with st.popover("💬 Feedback"):
            fb_reason = st.selectbox("Lý do:", ["Câu khó hiểu", "Đáp án sai", "Gợi ý không tốt", "Lỗi khác"])
            fb_detail = st.text_input("Chi tiết:")
            if st.button("Gửi Feedback"):
                conn = get_db_connection()
                conn.execute("INSERT INTO feedback (word_id, question_type, reason, details, created_at) VALUES (?,?,?,?,?)",
                             (w_obj["id"], q["type"], fb_reason, fb_detail, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                conn.commit()
                conn.close()
                st.success("Đã ghi nhận feedback!")

    # SHOW RESULT AFTER SUBMITTED
    if st.session_state.answer_submitted:
        last_res = st.session_state.session_results[-1]
        if last_res["is_correct"]:
            st.markdown(f"<div class='correct-box'>✅ <b>ĐÚNG RỒI! Nice effort!</b></div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='wrong-box'>❌ <b>CHƯA CHÍNH XÁC! Hãy cố gắng ở lượt sau.</b></div>", unsafe_allow_html=True)
        
        st.write("---")
        st.markdown(f"### 🔤 Đáp án: **{w_obj['word']}** `{w_obj['phonetic']}`")
        st.write(f"🇻🇳 **Nghĩa:** {w_obj['vietnamese_meaning']}")
        st.write(f"📝 **Ví dụ:** *{w_obj['example_sentence']}*")
        
        # Audio autoplay post answer
        text_to_speech_html(w_obj["word"], w_obj["vietnamese_meaning"], autoplay=True)

        if st.button("➡️ TIẾP TỤC", type="primary"):
            st.session_state.session_idx += 1
            st.session_state.answer_submitted = False
            st.session_state.current_q = None
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

# ==============================================================================
# TAB 3 — SỔ TAY (FLASHCARDS & AI EDIT)
# ==============================================================================
def render_tab_notebook():
    st.markdown("### 📚 Sổ tay từ vựng Flashcards")
    
    conn = get_db_connection()
    topics = [r["topic"] for r in conn.execute("SELECT DISTINCT topic FROM words").fetchall()]
    conn.close()

    col_f1, col_f2 = st.columns([2, 2])
    with col_f1:
        search = st.text_input("🔎 Tìm kiếm từ...", "")
    with col_f2:
        selected_topic = st.selectbox("Lọc theo Topic:", ["Tất cả"] + topics)

    query = "SELECT * FROM words WHERE 1=1"
    params = []
    if search:
        query += " AND (word LIKE ? OR vietnamese_meaning LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
    if selected_topic != "Tất cả":
        query += " AND topic = ?"
        params.append(selected_topic)
    
    query += " ORDER BY id DESC"
    
    conn = get_db_connection()
    words = conn.execute(query, params).fetchall()
    conn.close()

    st.write(f"Hiển thị **{len(words)}** từ vựng.")

    cols = st.columns(2)
    for i, w in enumerate(words):
        with cols[i % 2]:
            st.markdown("<div class='main-card'>", unsafe_allow_html=True)
            st.markdown(f"### **{w['word']}** `{w['phonetic']}`")
            st.write(f"🇻🇳 **Nghĩa:** {w['vietnamese_meaning']}")
            st.write(f"📖 **Ví dụ:** *{w['example_sentence']}*")
            
            acc = int((w['correct_count'] / w['total_reviews']) * 100) if w['total_reviews'] > 0 else 0
            st.caption(f"Topic: {w['topic']} | Độ khó: {w['difficulty']}/100 | Accuracy: {acc}% | Streak: {w['current_streak']}")
            
            c1, c2 = st.columns(2)
            with c1:
                text_to_speech_html(w['word'], w['vietnamese_meaning'], autoplay=False)
            with c2:
                with st.popover("✏️ Sửa / AI Fix"):
                    new_meaning = st.text_input("Nghĩa Việt mới:", w['vietnamese_meaning'], key=f"edit_m_{w['id']}")
                    new_ex = st.text_input("Ví dụ mới:", w['example_sentence'], key=f"edit_e_{w['id']}")
                    if st.button("Lưu thay đổi", key=f"save_edit_{w['id']}"):
                        c = get_db_connection()
                        c.execute("UPDATE words SET vietnamese_meaning = ?, example_sentence = ? WHERE id = ?", (new_meaning, new_ex, w['id']))
                        c.commit()
                        c.close()
                        st.success("Đã lưu!")
                        st.rerun()

                    if st.button("🤖 AI Sửa tự động", key=f"ai_fix_{w['id']}"):
                        res = call_ai(f"Improve explanation for word: '{w['word']}'. Context definition. Return JSON: {{'vietnamese_meaning': '...', 'phonetic': '...', 'example_sentence': '...'}}")
                        if res:
                            c = get_db_connection()
                            c.execute("UPDATE words SET vietnamese_meaning = ?, phonetic = ?, example_sentence = ? WHERE id = ?",
                                      (res.get('vietnamese_meaning', new_meaning), res.get('phonetic', w['phonetic']), res.get('example_sentence', new_ex), w['id']))
                            c.commit()
                            c.close()
                            st.success("AI đã tối ưu thông tin từ!")
                            st.rerun()

            st.markdown("</div>", unsafe_allow_html=True)

# ==============================================================================
# TAB 4 — READING (AI PASSAGE & GRADED TRANSLATION)
# ==============================================================================
def render_tab_reading():
    st.markdown("### 📖 Reading Practice (Luyện đọc ngữ cảnh)")
    
    conn = get_db_connection()
    topics = [r["topic"] for r in conn.execute("SELECT topic, COUNT(*) as c FROM words GROUP BY topic HAVING c >= 3").fetchall()]
    conn.close()

    if not topics:
        st.info("Cần tối thiểu 3-5 từ thuộc cùng một Topic trong Sổ tay để AI sinh bài đọc!")
        return

    selected_topic = st.selectbox("Chọn Topic để làm bài Reading:", topics)

    if st.button("⚡ TẠO BÀI READING MỚI", type="primary"):
        conn = get_db_connection()
        words = conn.execute("SELECT * FROM words WHERE topic = ? ORDER BY difficulty ASC LIMIT 10", (selected_topic,)).fetchall()
        conn.close()
        
        target_vocab = [w["word"] for w in words]
        min_diff = min([w["difficulty"] for w in words]) if words else 20

        prompt = f"""
        Generate a short, coherent reading passage (100-150 words) suitable for English learners.
        Target topic: {selected_topic}
        Required difficulty level: {min_diff}/100 (Keep vocabulary simple enough for this level).
        You MUST naturally embed these target words: {target_vocab}

        Return JSON format:
        {{
            "title": "Passage Title",
            "passage": "Full English passage text...",
            "target_words_used": {json.dumps(target_vocab)}
        }}
        """
        
        with st.spinner("🤖 AI đang biên soạn bài đọc phù hợp trình độ..."):
            res = call_ai(prompt)
            if res:
                st.session_state.current_reading = res

    if "current_reading" in st.session_state and st.session_state.current_reading:
        rd = st.session_state.current_reading
        st.markdown("<div class='main-card'>", unsafe_allow_html=True)
        st.markdown(f"## 📜 {rd.get('title', 'Reading Passage')}")
        st.markdown(f"*{rd.get('passage')}*")
        st.caption(f"Từ vựng mục tiêu: {', '.join(rd.get('target_words_used', []))}")
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("#### 🇻🇳 Hãy dịch đoạn văn trên sang tiếng Việt:")
        user_translation = st.text_area("Bản dịch của bạn:", height=150)

        if st.button("📝 NỘP BÀI DỊCH & CHẤM ĐIỂM", type="primary"):
            if not user_translation.strip():
                st.warning("Vui lòng nhập bản dịch trước khi nộp.")
                return

            eval_prompt = f"""
            Evaluate this Vietnamese translation for the English reading passage.
            English Passage: "{rd.get('passage')}"
            User Translation: "{user_translation}"

            Return JSON format:
            {{
                "semantic_accuracy": 85,
                "comprehension": 90,
                "feedback": "Detailed constructive feedback on accuracy and mistranslations",
                "suggested_translation": "Smooth Vietnamese translation"
            }}
            """
            with st.spinner("🤖 AI đang chấm điểm bản dịch của bạn..."):
                eval_res = call_ai(eval_prompt)
                if eval_res:
                    st.markdown("<div class='main-card'>", unsafe_allow_html=True)
                    st.markdown("### 📊 ĐÁNH GIÁ CỦA AI")
                    c1, c2 = st.columns(2)
                    c1.metric("Độ chính xác nghĩa", f"{eval_res.get('semantic_accuracy', 0)}%")
                    c2.metric("Độ hiểu bài", f"{eval_res.get('comprehension', 0)}%")

                    st.markdown(f"**💬 Nhận xét:** {eval_res.get('feedback')}")
                    st.markdown(f"**💡 Bản dịch gợi ý chuẩn:**\n*{eval_res.get('suggested_translation')}*")
                    st.markdown("</div>", unsafe_allow_html=True)

                    # Record reading session in SQLite
                    conn = get_db_connection()
                    conn.execute("""
                        INSERT INTO reading_sessions (topic, passage, user_translation, accuracy, comprehension, feedback, reviewed_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (selected_topic, rd.get('passage'), user_translation, eval_res.get('semantic_accuracy', 0),
                          eval_res.get('comprehension', 0), eval_res.get('feedback'), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                    conn.commit()
                    conn.close()

# ==============================================================================
# MAIN ROUTER
# ==============================================================================
def main():
    st.title("⚡ Vocab Conquest — Gamified SRS Learning")
    
    tab1, tab2, tab3, tab4 = st.tabs([
        "📥 Scan từ mới", 
        "🎯 Ôn tập", 
        "📚 Sổ tay", 
        "📖 Reading"
    ])

    with tab1:
        render_tab_scan()
    with tab2:
        render_tab_review()
    with tab3:
        render_tab_notebook()
    with tab4:
        render_tab_reading()

if __name__ == "__main__":
    main()
