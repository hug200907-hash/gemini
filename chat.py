import os
import json
import sqlite3
import random
import re
import html
import base64
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from io import BytesIO
import requests
import streamlit as st
from gtts import gTTS

# ==============================================================================
# CONFIG & CONSTANTS
# ==============================================================================
CONFIG = {
    "OPENROUTER_MODEL": "minimax/minimax-m3:free",
    "OPENROUTER_API_URL": "https://openrouter.ai/api/v1/chat/completions",
    "DB_PATH": "vocab_app.db",
    "SESSION_SIZE": 5,
    "MIN_READING_WORDS": 10,
}

TOPICS = [
    "General", "Technology", "Work", "Education", "Travel",
    "Science", "Daily life", "IELTS", "Business", "Environment", "Society"
]

# ==============================================================================
# DATABASE FUNCTIONS
# ==============================================================================
def get_db_connection():
    conn = sqlite3.connect(CONFIG["DB_PATH"], check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vocabulary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT UNIQUE NOT NULL,
            lemma TEXT,
            pos TEXT,
            vi_meaning TEXT NOT NULL,
            en_definition TEXT,
            ipa TEXT,
            topic TEXT DEFAULT 'General',
            example TEXT,
            source_sentence TEXT,
            difficulty INTEGER DEFAULT 15,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            first_reviewed_at TIMESTAMP,
            last_reviewed_at TIMESTAMP,
            next_review_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            review_count INTEGER DEFAULT 0,
            correct_count INTEGER DEFAULT 0,
            wrong_count INTEGER DEFAULT 0,
            consecutive_correct INTEGER DEFAULT 0,
            consecutive_wrong INTEGER DEFAULT 0,
            is_new INTEGER DEFAULT 1
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS review_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vocab_id INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            question_type INTEGER,
            correct INTEGER,
            difficulty_before INTEGER,
            difficulty_after INTEGER,
            FOREIGN KEY (vocab_id) REFERENCES vocabulary(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reading (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            passage TEXT NOT NULL,
            difficulty INTEGER DEFAULT 20,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_reviewed_at TIMESTAMP,
            next_review_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            review_count INTEGER DEFAULT 0,
            last_accuracy INTEGER DEFAULT 0,
            last_comprehension INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_stats (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            xp INTEGER DEFAULT 0,
            streak INTEGER DEFAULT 0,
            last_active_date TEXT
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO user_stats (id, xp, streak) VALUES (1, 0, 0)")
    conn.commit()
    conn.close()

# ==============================================================================
# OPENROUTER AI CLIENT
# ==============================================================================
def call_openrouter(prompt: str, json_mode: bool = True) -> str:
    api_key = st.secrets.get("OPENROUTER_API_KEY", "")
    if not api_key:
        api_key = os.environ.get("OPENROUTER_API_KEY", "")

    if not api_key:
        raise ValueError("Chưa cấu hình API Key trong Streamlit Secrets (OPENROUTER_API_KEY).")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://streamlit.io",
        "X-Title": "Vocab Master App"
    }

    payload = {
        "model": CONFIG["OPENROUTER_MODEL"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3
    }

    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    for _ in range(2):
        try:
            resp = requests.post(CONFIG["OPENROUTER_API_URL"], headers=headers, json=payload, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return content
        except Exception:
            continue
    raise Exception("Lỗi kết nối API OpenRouter. Vui lòng thử lại sau.")

def clean_and_parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise ValueError("Dữ liệu phản hồi từ AI không hợp lệ.")

# ==============================================================================
# TTS AUDIO UTILS
# ==============================================================================
def get_audio_base64(text: str) -> str:
    try:
        tts = gTTS(text=text, lang='en')
        fp = BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        b64 = base64.b64encode(fp.read()).decode('utf-8')
        return b64
    except Exception:
        return ""

def play_audio_html(text: str, autoplay: bool = True):
    b64 = get_audio_base64(text)
    if not b64:
        st.warning("Không thể phát âm thanh TTS lúc này.")
        return
    
    autoplay_attr = "autoplay" if autoplay else ""
    audio_html = f"""
        <audio {autoplay_attr} controls style="width: 100%; height: 35px; margin-top: 10px;">
            <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
            Your browser does not support HTML audio.
        </audio>
    """
    st.markdown(audio_html, unsafe_allow_html=True)

# ==============================================================================
# HINT GENERATION ALGORITHM
# ==============================================================================
def generate_letter_hint(word: str, difficulty: int) -> str:
    word_len = len(word)
    if word_len <= 2:
        return word

    vowels = set("aeiouAEIOU")
    indices = list(range(word_len))
    
    # Logic revealing count based on difficulty
    if difficulty <= 25:
        reveal_ratio = 0.6
    elif difficulty <= 50:
        reveal_ratio = 0.4
    elif difficulty <= 75:
        reveal_ratio = 0.3
    else:
        reveal_ratio = 0.2

    num_to_reveal = max(1, int(word_len * reveal_ratio))
    
    # Priority: Vowels first
    vowel_indices = [i for i in indices if word[i] in vowels]
    consonant_indices = [i for i in indices if word[i] not in vowels and word[i].isalpha()]

    revealed = set()
    
    # Reveal first letter if applicable
    revealed.add(0)
    
    for idx in vowel_indices:
        if len(revealed) < num_to_reveal:
            revealed.add(idx)
            
    for idx in consonant_indices:
        if len(revealed) < num_to_reveal:
            revealed.add(idx)
            
    result = []
    for i, ch in enumerate(word):
        if not ch.isalpha():
            result.append(ch)
        elif i in revealed:
            result.append(ch)
        else:
            result.append("_")
            
    return " ".join(result)

# ==============================================================================
# SPACED REPETITION SCHEDULER
# ==============================================================================
def calculate_next_review(vocab: dict, correct: bool) -> tuple[int, datetime]:
    diff = vocab["difficulty"]
    c_correct = vocab["consecutive_correct"]
    c_wrong = vocab["consecutive_wrong"]

    if correct:
        c_correct += 1
        c_wrong = 0
        diff = max(0, diff - 3)
        if c_correct == 1:
            minutes = 20
        elif c_correct == 2:
            minutes = 60 * 4      # 4h
        elif c_correct == 3:
            minutes = 60 * 12     # 12h
        elif c_correct == 4:
            minutes = 60 * 24     # 1 day
        elif c_correct == 5:
            minutes = 60 * 24 * 3 # 3 days
        else:
            minutes = 60 * 24 * 7 # 7 days
    else:
        c_wrong += 1
        c_correct = 0
        diff = min(100, diff + 8)
        if c_wrong == 1:
            minutes = 5
        elif c_wrong == 2:
            minutes = 15
        else:
            minutes = 60          # 1h

    next_time = datetime.now() + timedelta(minutes=minutes)
    return diff, next_time, c_correct, c_wrong

def update_user_stats(xp_earned: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT xp, streak, last_active_date FROM user_stats WHERE id = 1")
    row = cursor.fetchone()
    
    xp = row["xp"] + xp_earned
    streak = row["streak"]
    last_date_str = row["last_active_date"]
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    if last_date_str != today_str:
        if last_date_str:
            last_date = datetime.strptime(last_date_str, "%Y-%m-%d").date()
            today = datetime.now().date()
            if (today - last_date).days == 1:
                streak += 1
            elif (today - last_date).days > 1:
                streak = 1
        else:
            streak = 1
        last_date_str = today_str
        
    cursor.execute("""
        UPDATE user_stats 
        SET xp = ?, streak = ?, last_active_date = ?
        WHERE id = 1
    """, (xp, streak, last_date_str))
    conn.commit()
    conn.close()

# ==============================================================================
# QUESTION GENERATION ENGINE
# ==============================================================================
def get_distractors(target_word: dict, field: str, limit: int = 3) -> list:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT {} FROM vocabulary 
        WHERE id != ? AND {} IS NOT NULL AND {} != ''
        ORDER BY RANDOM() LIMIT ?
    """.format(field, field, field), (target_word["id"], limit))
    rows = cursor.fetchall()
    conn.close()
    results = [r[field] for r in rows]
    
    # Fallback default distractors if not enough DB items
    defaults = {
        "vi_meaning": ["quan trọng", "phát triển", "thay đổi", "cơ hội", "thách thức"],
        "word": ["reluctant", "ambiguous", "consequence", "foster", "profound"],
        "ipa": ["/rɪˈlʌktənt/", "/æmˈbɪɡjuəs/", "/ˈkɒnsɪkwəns/", "/ˈfɒstər/"]
    }
    while len(results) < limit:
        opt = random.choice(defaults.get(field, ["N/A"]))
        if opt not in results and opt != target_word.get(field):
            results.append(opt)
    return results[:limit]

def generate_question_data(vocab: dict) -> dict:
    q_type = random.choice([1, 2, 3, 4, 5])
    word = vocab["word"]
    vi = vocab["vi_meaning"]
    difficulty = vocab["difficulty"]

    if q_type == 1: # Context fill
        prompt = f"""Create a clear English sentence using the word '{word}' (Meaning: {vi}).
Constraint: Context must fit a learner level with difficulty {difficulty}/100.
Return JSON ONLY:
{{"sentence": "Sentence with {word} in it.", "blank_sentence": "Sentence with _____ instead of {word}."}}"""
        try:
            res = clean_and_parse_json(call_openrouter(prompt))
            blank_sentence = res.get("blank_sentence", f"She felt _____ about it. ({vi})")
        except Exception:
            blank_sentence = f"Example context: _____ means '{vi}'."

        hint = generate_letter_hint(word, difficulty)
        return {
            "type": 1,
            "title": "Fill in the blank from context",
            "prompt": f"Điền từ còn thiếu vào câu dưới đây:\n\n**{blank_sentence}**",
            "hint": f"Gợi ý: `{hint}`",
            "answer": word,
            "vocab": vocab
        }

    elif q_type == 2: # EN meaning of VI
        distractors = get_distractors(vocab, "word", 3)
        options = distractors + [word]
        random.shuffle(options)
        return {
            "type": 2,
            "title": "Choose English Word",
            "prompt": f"Chọn từ tiếng Anh phù hợp với nghĩa:\n### **\"{vi}\"**",
            "options": options,
            "answer": word,
            "vocab": vocab
        }

    elif q_type == 3: # VI meaning of EN
        distractors = get_distractors(vocab, "vi_meaning", 3)
        options = distractors + [vi]
        random.shuffle(options)
        return {
            "type": 3,
            "title": "Choose Vietnamese Meaning",
            "prompt": f"Chọn nghĩa tiếng Việt đúng của từ:\n### **\"{word}\"**",
            "options": options,
            "answer": vi,
            "vocab": vocab
        }

    elif q_type == 4: # Spelling
        sentence = vocab.get("example") or f"Word meaning: {vi}"
        blank_sentence = sentence.replace(word, "_____")
        hint = generate_letter_hint(word, difficulty)
        return {
            "type": 4,
            "title": "Spelling Challenge",
            "prompt": f"Viết lại từ tiếng Anh đúng chính tả:\n\nNghĩa: **{vi}**\n\nContext: *{blank_sentence}*",
            "hint": f"Gợi ý: `{hint}`",
            "answer": word,
            "vocab": vocab
        }

    else: # IPA / Pronunciation
        target_ipa = vocab.get("ipa") or f"/{word}/"
        distractors = get_distractors(vocab, "ipa", 3)
        options = distractors + [target_ipa]
        random.shuffle(options)
        return {
            "type": 5,
            "title": "Pronunciation / IPA",
            "prompt": f"Chọn phiên âm IPA đúng cho từ **\"{word}\"** ({vi}):",
            "options": options,
            "answer": target_ipa,
            "vocab": vocab
        }

# ==============================================================================
# UI COMPONENTS & TABS
# ==============================================================================
def render_header():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT xp, streak FROM user_stats WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    
    xp = row["xp"] if row else 0
    streak = row["streak"] if row else 0
    level = (xp // 100) + 1
    xp_in_level = xp % 100

    st.markdown(f"""
        <div style="background: linear-gradient(135deg, #1e293b, #0f172a); padding: 15px 25px; border-radius: 12px; color: white; margin-bottom: 20px;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <h2 style="margin:0; color:#38bdf8;">⚡ Vocab Master</h2>
                <div style="display: flex; gap: 20px; font-weight: bold; font-size: 16px;">
                    <span>🔥 Streak: <span style="color:#f59e0b;">{streak} days</span></span>
                    <span>⭐ Level {level}</span>
                    <span>💎 XP: <span style="color:#a855f7;">{xp}</span></span>
                </div>
            </div>
        </div>
    """, unsafe_allow_html=True)
    st.progress(xp_in_level / 100.0)

def tab_scan_and_learn():
    st.header("📖 Scan & Learn")
    st.caption("Dán đoạn văn tiếng Anh bên dưới để AI quét các từ vựng đáng học nhất!")
    
    input_text = st.text_area(
        "Nhập đoạn văn tiếng Anh:",
        height=140,
        placeholder="I was reluctant to accept the offer because the consequences seemed ambiguous..."
    )
    
    if st.button("🔍 Scan vocabulary", type="primary"):
        if not input_text.strip():
            st.warning("Vui lòng nhập đoạn văn tiếng Anh.")
            return

        with st.spinner("AI đang phân tích và trích xuất từ vựng..."):
            prompt = f"""Analyze this text and extract key vocabulary (useful academic words, phrasal verbs, idioms) for an English learner.
Do NOT extract basic words (e.g., the, a, is, are, of, to, and).

Text: "{input_text}"

Return JSON object format:
{{
    "items": [
        {{
            "word": "word",
            "lemma": "lemma",
            "part_of_speech": "noun/verb/adj",
            "vietnamese_meaning": "nghĩa ngắn gọn",
            "english_definition": "short English definition",
            "example_sentence": "example sentence using word",
            "ipa": "/.../",
            "topic": "General/Technology/Work/...",
            "difficulty": 15,
            "source_sentence": "sentence from input where word appeared"
        }}
    ]
}}"""
            try:
                raw_res = call_openrouter(prompt)
                parsed = clean_and_parse_json(raw_res)
                items = parsed.get("items", [])
                st.session_state["scanned_items"] = items
                st.success(f"Tìm thấy {len(items)} từ vựng hữu ích!")
            except Exception as e:
                st.error(f"Lỗi phân tích: {str(e)}")

    if "scanned_items" in st.session_state and st.session_state["scanned_items"]:
        items = st.session_state["scanned_items"]
        st.subheader("Danh sách từ vựng trích xuất")
        
        selected_words = []
        for idx, item in enumerate(items):
            with st.expander(f"📌 **{item['word']}** ({item.get('part_of_speech', 'n/a')}) - {item['vietnamese_meaning']}", expanded=True):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"**IPA:** {item.get('ipa', '')}")
                    st.write(f"**English:** {item.get('english_definition', '')}")
                    st.write(f"**Ví dụ:** {item.get('example_sentence', '')}")
                    st.write(f"**Topic:** `{item.get('topic', 'General')}`")
                with col2:
                    chk = st.checkbox("Chọn lưu từ này", value=True, key=f"chk_{idx}_{item['word']}")
                    if chk:
                        selected_words.append(item)

        if st.button("💾 Save Selected Words", type="primary"):
            if not selected_words:
                st.warning("Vui lòng chọn ít nhất một từ để lưu.")
                return
                
            conn = get_db_connection()
            cursor = conn.cursor()
            saved_count = 0
            
            for item in selected_words:
                cursor.execute("""
                    INSERT INTO vocabulary 
                    (word, lemma, pos, vi_meaning, en_definition, ipa, topic, example, source_sentence, difficulty, is_new)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                    ON CONFLICT(word) DO UPDATE SET
                        vi_meaning=excluded.vi_meaning,
                        en_definition=excluded.en_definition,
                        ipa=excluded.ipa,
                        topic=excluded.topic,
                        source_sentence=excluded.source_sentence
                """, (
                    item['word'].strip().lower(),
                    item.get('lemma', ''),
                    item.get('part_of_speech', ''),
                    item['vietnamese_meaning'],
                    item.get('english_definition', ''),
                    item.get('ipa', ''),
                    item.get('topic', 'General'),
                    item.get('example_sentence', ''),
                    item.get('source_sentence', ''),
                    int(item.get('difficulty', 15))
                ))
                saved_count += 1
                
            conn.commit()
            conn.close()
            st.balloons()
            st.success(f"Đã lưu thành công {saved_count} từ vựng vào Notebook!")
            st.session_state["scanned_items"] = []

def tab_review():
    st.header("🧠 Review Session")
    
    # Init review state
    if "review_session" not in st.session_state:
        st.session_state["review_session"] = None
    if "current_q_idx" not in st.session_state:
        st.session_state["current_q_idx"] = 0
    if "session_results" not in st.session_state:
        st.session_state["session_results"] = []
    if "answered" not in st.session_state:
        st.session_state["answered"] = False

    # Start button if no session active
    if st.session_state["review_session"] is None:
        st.info("Mỗi lượt ôn tập gồm 5–6 từ vựng được chọn tối ưu theo lịch Spaced Repetition.")
        if st.button("🚀 Start Review Session", type="primary"):
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Fetch candidates logic: Priority Wrong/New/Due
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                SELECT * FROM vocabulary 
                WHERE consecutive_wrong > 0 OR is_new = 1 OR next_review_at <= ?
                ORDER BY consecutive_wrong DESC, is_new DESC, next_review_at ASC
                LIMIT ?
            """, (now_str, CONFIG["SESSION_SIZE"]))
            vocabs = [dict(r) for r in cursor.fetchall()]
            
            # Fallback if no due words: pick random least reviewed
            if len(vocabs) < CONFIG["SESSION_SIZE"]:
                existing_ids = [v["id"] for v in vocabs]
                placeholders = ",".join(["?"] * len(existing_ids)) if existing_ids else "-1"
                cursor.execute(f"""
                    SELECT * FROM vocabulary 
                    WHERE id NOT IN ({placeholders})
                    ORDER BY last_reviewed_at ASC LIMIT ?
                """, (CONFIG["SESSION_SIZE"] - len(vocabs)))
                vocabs.extend([dict(r) for r in cursor.fetchall()])
                
            conn.close()
            
            if not vocabs:
                st.warning("Bạn chưa có từ vựng nào trong Notebook. Hãy sang tab Scan & Learn để thêm từ mới!")
                return
                
            # Build question list (Only 1 Q per vocab per session)
            questions = [generate_question_data(v) for v in vocabs]
            st.session_state["review_session"] = questions
            st.session_state["current_q_idx"] = 0
            st.session_state["session_results"] = []
            st.session_state["answered"] = False
            st.rerun()
        return

    # Session active flow
    questions = st.session_state["review_session"]
    idx = st.session_state["current_q_idx"]

    # Summary screen at session end
    if idx >= len(questions):
        st.balloons()
        results = st.session_state["session_results"]
        correct_count = sum(1 for r in results if r["correct"])
        total = len(results)
        acc = int((correct_count / total) * 100) if total > 0 else 0
        xp_gained = (correct_count * 10) + ((total - correct_count) * 5) + 15
        
        update_user_stats(xp_gained)

        st.markdown(f"""
            <div style="background-color: #1e293b; padding: 20px; border-radius: 12px; text-align: center; color: white;">
                <h2>🎉 Session Complete!</h2>
                <h3>Kết quả: {correct_count}/{total} đúng ({acc}%)</h3>
                <h4 style="color: #a855f7;">+ {xp_gained} XP EARNED!</h4>
            </div>
        """, unsafe_allow_html=True)
        
        if st.button("🔄 Bắt đầu session mới"):
            st.session_state["review_session"] = None
            st.rerun()
        return

    # Render Current Question
    q = questions[idx]
    vocab = q["vocab"]

    st.progress((idx) / len(questions))
    st.caption(f"Question {idx + 1} of {len(questions)}")
    st.subheader(q["title"])
    st.markdown(q["prompt"])
    if "hint" in q:
        st.info(q["hint"])

    user_answer = None

    if q["type"] in [2, 3, 5]: # MCQ
        user_answer = st.radio("Chọn đáp án đúng:", q["options"], key=f"q_{idx}_mcq", disabled=st.session_state["answered"])
    else: # Text Input (Type 1 & 4)
        user_answer = st.text_input("Nhập câu trả lời của bạn:", key=f"q_{idx}_input", disabled=st.session_state["answered"])

    if not st.session_state["answered"]:
        if st.button("Submit Answer", type="primary"):
            if not user_answer or not str(user_answer).strip():
                st.warning("Vui lòng chọn hoặc nhập đáp án.")
                return
            st.session_state["answered"] = True
            st.rerun()
    else:
        # Check correctness
        is_correct = False
        target = str(q["answer"]).strip().lower()
        given = str(user_answer).strip().lower()

        if q["type"] in [1, 4]:
            is_correct = (given == target)
        else:
            is_correct = (str(user_answer) == str(q["answer"]))

        # Play Audio TTS automatically
        play_audio_html(vocab["word"], autoplay=True)

        if is_correct:
            st.success(f"🎉 Correct! Từ vựng: **{vocab['word']}** phát âm là `{vocab.get('ipa','')}`")
        else:
            st.error(f"❌ Not quite! Đáp án đúng là: **{q['answer']}**")

        st.markdown(f"""
        **Chi tiết từ vựng:**
        - **Từ:** {vocab['word']} ({vocab.get('pos','')})
        - **Nghĩa:** {vocab['vi_meaning']}
        - **Ví dụ:** *{vocab.get('example','N/A')}*
        """)

        if st.button("➡️ Next Question", type="primary"):
            # Update DB Spaced Repetition stats
            conn = get_db_connection()
            cursor = conn.cursor()
            diff_after, next_review, c_corr, c_wrong = calculate_next_review(vocab, is_correct)
            
            cursor.execute("""
                UPDATE vocabulary
                SET difficulty = ?,
                    next_review_at = ?,
                    last_reviewed_at = CURRENT_TIMESTAMP,
                    review_count = review_count + 1,
                    correct_count = correct_count + ?,
                    wrong_count = wrong_count + ?,
                    consecutive_correct = ?,
                    consecutive_wrong = ?,
                    is_new = 0
                WHERE id = ?
            """, (diff_after, next_review.strftime("%Y-%m-%d %H:%M:%S"), 1 if is_correct else 0, 0 if is_correct else 1, c_corr, c_wrong, vocab["id"]))
            
            cursor.execute("""
                INSERT INTO review_history (vocab_id, question_type, correct, difficulty_before, difficulty_after)
                VALUES (?, ?, ?, ?, ?)
            """, (vocab["id"], q["type"], 1 if is_correct else 0, vocab["difficulty"], diff_after))
            
            conn.commit()
            conn.close()

            # Record session log & move next
            st.session_state["session_results"].append({"vocab_id": vocab["id"], "correct": is_correct})
            st.session_state["current_q_idx"] += 1
            st.session_state["answered"] = False
            st.rerun()

def tab_notebook():
    st.header("📚 Vocabulary Notebook & Reading")
    
    tab_words, tab_reading = st.tabs(["🗂️ Từ vựng đã lưu", "📖 Reading Challenge"])
    
    with tab_words:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        search_query = st.text_input("🔍 Tìm kiếm từ vựng hoặc nghĩa:")
        topic_filter = st.selectbox("Lọc theo Topic:", ["All"] + TOPICS)
        
        sql = "SELECT * FROM vocabulary WHERE 1=1"
        params = []
        if search_query:
            sql += " AND (word LIKE ? OR vi_meaning LIKE ?)"
            params.extend([f"%{search_query}%", f"%{search_query}%"])
        if topic_filter != "All":
            sql += " AND topic = ?"
            params.append(topic_filter)
            
        sql += " ORDER BY id DESC"
        cursor.execute(sql, params)
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()

        st.caption(f"Tổng số: {len(rows)} từ vựng")
        
        for v in rows:
            acc = int((v["correct_count"] / v["review_count"]) * 100) if v["review_count"] > 0 else 0
            with st.expander(f"**{v['word']}** - {v['vi_meaning']} | `{v['topic']}`"):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"**IPA:** {v.get('ipa','')}")
                    st.write(f"**English Def:** {v.get('en_definition','')}")
                    st.write(f"**Ví dụ:** {v.get('example','')}")
                    st.write(f"**Độ khó (Difficulty):** `{v['difficulty']}/100`")
                with col2:
                    st.write(f"**Review:** {v['review_count']} lần")
                    st.write(f"**Độ chính xác:** {acc}%")
                    if st.button("🔊 Nghe", key=f"audio_nb_{v['id']}"):
                        play_audio_html(v['word'], autoplay=True)

    with tab_reading:
        st.subheader("IELTS-Style Reading Practice")
        st.caption("Tự động tạo bài đọc khi có từ 10 từ vựng cùng Topic trở lên.")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT topic, COUNT(*) as cnt FROM vocabulary GROUP BY topic HAVING cnt >= ?", (CONFIG["MIN_READING_WORDS"],))
        ready_topics = cursor.fetchall()
        
        if not ready_topics:
            st.info(f"Cần tối thiểu {CONFIG['MIN_READING_WORDS']} từ vựng trong cùng 1 Topic để mở khóa Reading Challenge.")
            conn.close()
            return

        topic_names = [r["topic"] for r in ready_topics]
        sel_topic = st.selectbox("Chọn Topic để tạo bài đọc:", topic_names)
        
        if st.button("✨ Generate New Passage", type="primary"):
            cursor.execute("SELECT word, vi_meaning, difficulty FROM vocabulary WHERE topic = ?", (sel_topic,))
            words_data = [dict(r) for r in cursor.fetchall()]
            min_diff = min(w["difficulty"] for w in words_data)
            words_str = ", ".join([w["word"] for w in words_data])
            
            prompt = f"""Create a short, cohesive IELTS-style reading passage (120-180 words) using naturally these words: {words_str}.
Target reading difficulty level: {min_diff}/100.
Return JSON ONLY:
{{"passage": "The generated English reading passage..."}}"""
            with st.spinner("AI đang soạn bài đọc..."):
                try:
                    res = clean_and_parse_json(call_openrouter(prompt))
                    passage = res["passage"]
                    cursor.execute("INSERT INTO reading (topic, passage, difficulty) VALUES (?, ?, ?)", (sel_topic, passage, min_diff))
                    conn.commit()
                    st.success("Đã khởi tạo bài đọc mới thành công!")
                except Exception as e:
                    st.error(f"Lỗi tạo bài đọc: {str(e)}")

        # Fetch active readings
        cursor.execute("SELECT * FROM reading WHERE topic = ? ORDER BY id DESC LIMIT 1", (sel_topic,))
        reading_item = cursor.fetchone()
        conn.close()

        if reading_item:
            reading_dict = dict(reading_item)
            st.markdown("---")
            st.markdown(f"### Passage ({reading_dict['topic']})")
            st.write(reading_dict["passage"])
            
            user_trans = st.text_area("Dịch bài đọc trên sang tiếng Việt:", height=120)
            if st.button("📝 Nộp bản dịch để AI chấm điểm"):
                if not user_trans.strip():
                    st.warning("Vui lòng nhập bản dịch của bạn.")
                    return
                
                eval_prompt = f"""Evaluate this Vietnamese translation of an English passage.
Original Passage: "{reading_dict['passage']}"
User Translation: "{user_trans}"

Return JSON ONLY:
{{
    "meaning_accuracy": 85,
    "comprehension": 90,
    "overall_feedback": "Nhận xét chi tiết bằng tiếng Việt..."
}}"""
                with st.spinner("AI đang đánh giá bản dịch..."):
                    try:
                        eval_res = clean_and_parse_json(call_openrouter(eval_prompt))
                        acc = eval_res.get("meaning_accuracy", 70)
                        comp = eval_res.get("comprehension", 70)
                        fb = eval_res.get("overall_feedback", "Hoàn thành tốt!")
                        
                        st.markdown(f"""
                        **Kết quả đánh giá:**
                        - 🎯 Độ chính xác nghĩa: **{acc}%**
                        - 🧠 Mức độ hiểu bài: **{comp}%**
                        
                        **Gợi ý & Nhận xét:**
                        {fb}
                        """)
                        update_user_stats(25)
                    except Exception as e:
                        st.error(f"Lỗi chấm điểm: {str(e)}")

# ==============================================================================
# MAIN ENTRYPOINT
# ==============================================================================
def main():
    st.set_page_config(
        page_title="Vocab Master - Academic English",
        page_icon="⚡",
        layout="centered"
    )
    init_db()
    render_header()
    
    t1, t2, t3 = st.tabs(["📖 Scan & Learn", "🧠 Review", "📚 Notebook"])
    
    with t1:
        tab_scan_and_learn()
    with t2:
        tab_review()
    with t3:
        tab_notebook()

if __name__ == "__main__":
    main()
