import sqlite3
import json
import re
import random
import time
import requests
import pandas as pd
from datetime import datetime, timedelta
import streamlit as st
import streamlit.components.v1 as components

# ==========================================
# CONFIG & CONSTANTS
# ==========================================
DB_NAME = "vocab_quest.db"
DEFAULT_MODEL = "minimax/minimax-m3:free"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

st.set_page_config(
    page_title="VocabQuest - Gamified English",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# PHASE 1: DATABASE INITIALIZATION
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Tables
    c.execute('''
        CREATE TABLE IF NOT EXISTS scan_batches (
            scan_id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source_text TEXT,
            topic TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT UNIQUE,
            normalized_word TEXT,
            meaning_vi TEXT,
            meaning_en TEXT,
            part_of_speech TEXT,
            pronunciation TEXT,
            ipa TEXT,
            topic TEXT,
            example_sentence TEXT,
            difficulty REAL DEFAULT 15.0,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_review TIMESTAMP,
            next_review TIMESTAMP,
            review_count INTEGER DEFAULT 0,
            correct_count INTEGER DEFAULT 0,
            wrong_count INTEGER DEFAULT 0,
            streak INTEGER DEFAULT 0,
            status TEXT DEFAULT 'new',
            scan_id INTEGER,
            last_review_difficulty REAL,
            last_result INTEGER,
            last_question_type TEXT,
            FOREIGN KEY (scan_id) REFERENCES scan_batches (scan_id)
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS review_history (
            review_id INTEGER PRIMARY KEY AUTOINCREMENT,
            word_id INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            question_type TEXT,
            difficulty_before REAL,
            difficulty_after REAL,
            correct INTEGER,
            context TEXT,
            FOREIGN KEY (word_id) REFERENCES words (id)
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS profile (
            user_id TEXT PRIMARY KEY,
            xp INTEGER DEFAULT 0,
            daily_streak INTEGER DEFAULT 0,
            last_active_date TEXT,
            daily_goal INTEGER DEFAULT 10,
            words_learned_today INTEGER DEFAULT 0
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS readings (
            reading_id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT,
            words_used TEXT,
            difficulty REAL,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_review TIMESTAMP,
            next_review TIMESTAMP,
            review_count INTEGER DEFAULT 0
        )
    ''')
    
    # Init default user
    c.execute("INSERT OR IGNORE INTO profile (user_id, xp, daily_streak) VALUES ('default_user', 0, 0)")
    
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

# ==========================================
# PHASE 2: OPENROUTER API WRAPPER
# ==========================================
def call_ai(prompt, system_prompt="You are a helpful language learning assistant. Return raw valid JSON only."):
    api_key = st.secrets.get("OPENROUTER_API_KEY") if "OPENROUTER_API_KEY" in st.secrets else ""
    if not api_key:
        st.error("⚠️ OpenAI / OpenRouter API Key missing! Add OPENROUTER_API_KEY in Streamlit Secrets.")
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://vocabquest.streamlit.app",
        "X-Title": "VocabQuest"
    }
    
    payload = {
        "model": DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3
    }
    
    for attempt in range(3):
        try:
            res = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=20)
            if res.status_code == 200:
                content = res.json()["choices"][0]["message"]["content"].strip()
                # Clean Markdown JSON blocks if present
                content = re.sub(r"^```json\s*", "", content, flags=re.MULTILINE)
                content = re.sub(r"^```\s*", "", content, flags=re.MULTILINE)
                content = re.sub(r"```$", "", content, flags=re.MULTILINE).strip()
                return content
            elif res.status_code == 429:
                time.sleep(2)
            else:
                st.warning(f"API returned status {res.status_code}. Retrying...")
                time.sleep(1)
        except Exception as e:
            time.sleep(1)
            
    st.error("❌ Failed to contact AI API. Check network or OpenRouter service.")
    return None

# ==========================================
# AUDIO HELPER (Web Speech API via Component)
# ==========================================
def speak_text_js(text):
    clean_text = text.replace("'", "\\'").replace('"', '\\"')
    js_code = f"""
    <script>
        function speak() {{
            if ('speechSynthesis' in window) {{
                window.speechSynthesis.cancel();
                var msg = new SpeechSynthesisUtterance('{clean_text}');
                msg.lang = 'en-US';
                msg.rate = 0.9;
                window.speechSynthesis.speak(msg);
            }}
        }}
        speak();
    </script>
    <button onclick="speak()" style="
        background-color: #2e7d32; 
        color: white; 
        border: none; 
        padding: 6px 14px; 
        border-radius: 6px; 
        cursor: pointer;
        font-weight: bold;
        margin-top: 5px;
    ">🔊 Listen: {text}</button>
    """
    components.html(js_code, height=45)

# ==========================================
# PHASE 35: DETERMINISTIC HINT ALGORITHM
# ==========================================
def generate_hint(word, difficulty):
    word = word.strip()
    length = len(word)
    if length <= 2:
        return word[0] + "_" * (length - 1)
        
    # Reveal percentage based on difficulty
    if difficulty <= 20:
        ratio = 0.6
    elif difficulty <= 50:
        ratio = 0.4
    elif difficulty <= 80:
        ratio = 0.25
    else:
        ratio = 0.15

    num_to_reveal = max(1, min(length - 1, int(length * ratio)))
    revealed_indices = set()
    vowels = "aeiouyAEIOUY"

    # Rule 1: Reveal vowels first
    vowel_indices = [i for i, char in enumerate(word) if char in vowels and char.isalpha()]
    for idx in vowel_indices:
        if len(revealed_indices) < num_to_reveal:
            revealed_indices.add(idx)

    # Rule 2: Pick consonants near vowels
    if len(revealed_indices) < num_to_reveal:
        for v_idx in vowel_indices:
            for delta in [-1, 1, -2, 2]:
                c_idx = v_idx + delta
                if 0 <= c_idx < length and word[c_idx].isalpha() and c_idx not in revealed_indices:
                    # Avoid adjacent reveals if possible
                    if not (c_idx - 1 in revealed_indices or c_idx + 1 in revealed_indices):
                        revealed_indices.add(c_idx)
                        if len(revealed_indices) >= num_to_reveal:
                            break
            if len(revealed_indices) >= num_to_reveal:
                break

    # Fallback: Pick remaining letters
    if len(revealed_indices) < num_to_reveal:
        for i in range(length):
            if word[i].isalpha() and i not in revealed_indices:
                revealed_indices.add(i)
                if len(revealed_indices) >= num_to_reveal:
                    break

    hint_chars = []
    for i, char in enumerate(word):
        if not char.isalpha():
            hint_chars.append(char)
        elif i in revealed_indices:
            hint_chars.append(char)
        else:
            hint_chars.append("_")

    return " ".join(hint_chars)

# ==========================================
# PHASE 8 & 11: SPACED REPETITION LOGIC
# ==========================================
def calculate_next_review(difficulty, correct, review_count, streak):
    now = datetime.now()
    if not correct:
        # Short retry interval for incorrect words: 5 min - 30 min (Max 24h)
        minutes = min(1440, max(5, int(15 / max(1, streak + 1))))
        return now + timedelta(minutes=minutes), "learning"
    else:
        # Hyper-compressed intervals (1/10th traditional)
        # 1st success: 15m, 2nd: 1h, 3rd: 4h, 4th: 12h, 5th+: 1-3 days max
        if review_count <= 1:
            mins = 15
        elif review_count == 2:
            mins = 60
        elif review_count == 3:
            mins = 240
        elif review_count == 4:
            mins = 720
        else:
            mins = min(4320, 1440 * (streak)) # Max 3 days
            
        status = "mastered" if review_count >= 5 and difficulty >= 70 else "review"
        return now + timedelta(minutes=mins), status

def update_word_after_review(word_id, correct, q_type, current_diff):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM words WHERE id = ?", (word_id,))
    w = c.fetchone()
    
    if not w:
        conn.close()
        return

    c_count = w['correct_count'] + (1 if correct else 0)
    w_count = w['wrong_count'] + (0 if correct else 1)
    r_count = w['review_count'] + 1
    new_streak = (w['streak'] + 1) if correct else 0

    # Difficulty adjustment
    if correct:
        diff_delta = random.uniform(8.0, 12.0) + (new_streak * 0.5)
        new_diff = min(100.0, current_diff + diff_delta)
    else:
        diff_delta = random.uniform(10.0, 18.0)
        new_diff = max(0.0, current_diff - diff_delta)

    next_rev, new_status = calculate_next_review(new_diff, correct, r_count, new_streak)

    c.execute('''
        UPDATE words SET
            difficulty = ?,
            last_review = ?,
            next_review = ?,
            review_count = ?,
            correct_count = ?,
            wrong_count = ?,
            streak = ?,
            status = ?,
            last_review_difficulty = ?,
            last_result = ?,
            last_question_type = ?
        WHERE id = ?
    ''', (
        new_diff, datetime.now(), next_rev, r_count, c_count, w_count,
        new_streak, new_status, current_diff, 1 if correct else 0, q_type, word_id
    ))

    c.execute('''
        INSERT INTO review_history (word_id, question_type, difficulty_before, difficulty_after, correct, context)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (word_id, q_type, current_diff, new_diff, 1 if correct else 0, ""))

    # Update Profile XP
    xp_gain = (10 if correct else 2) + (new_streak * 2 if correct else 0)
    c.execute("UPDATE profile SET xp = xp + ? WHERE user_id = 'default_user'", (xp_gain,))

    conn.commit()
    conn.close()

# ==========================================
# PHASE 40: REVIEW PRIORITY ALGORITHM
# ==========================================
def select_review_words(limit=6):
    conn = get_db()
    c = conn.cursor()
    now = datetime.now()

    # Priority 1: Words failed previously due for review
    c.execute('''
        SELECT * FROM words 
        WHERE last_result = 0 AND (next_review <= ? OR next_review IS NULL)
        ORDER BY difficulty ASC LIMIT ?
    ''', (now, limit))
    failed_words = c.fetchall()

    selected = list(failed_words)
    selected_ids = {w['id'] for w in selected}

    # Priority 2: New words never reviewed
    if len(selected) < limit:
        rem = limit - len(selected)
        c.execute(f'''
            SELECT * FROM words 
            WHERE status = 'new' AND id NOT IN ({','.join(['?']*len(selected_ids)) if selected_ids else '0'})
            ORDER BY id ASC LIMIT ?
        ''', list(selected_ids) + [rem] if selected_ids else [rem])
        new_words = c.fetchall()
        selected.extend(new_words)
        selected_ids.update({w['id'] for w in new_words})

    # Priority 3: Due review words
    if len(selected) < limit:
        rem = limit - len(selected)
        c.execute(f'''
            SELECT * FROM words 
            WHERE next_review <= ? AND id NOT IN ({','.join(['?']*len(selected_ids)) if selected_ids else '0'})
            ORDER BY next_review ASC LIMIT ?
        ''', [now] + list(selected_ids) + [rem] if selected_ids else [now, rem])
        due_words = c.fetchall()
        selected.extend(due_words)

    conn.close()
    return selected

# ==========================================
# PHASE 5 & 6: AI QUESTION GENERATION
# ==========================================
def generate_question_for_word(word_row):
    q_type = random.choice(["type_1", "type_2", "type_3", "type_4", "type_5"])
    word = word_row['word']
    meaning_vi = word_row['meaning_vi']
    diff = word_row['difficulty']

    # Context simplicity instruction
    if diff < 25:
        level_desc = "SUPER EASY and simple sentence for beginner. Common words only."
    elif diff < 65:
        level_desc = "Intermediate level sentence, clear context."
    else:
        level_desc = "Advanced level sentence, rich vocabulary."

    system_p = "You are a language teacher. Generate a single exercise JSON for a word. Return JSON ONLY."
    
    # TYPE 1 & 4 (Fill blank / Spelling)
    if q_type in ["type_1", "type_4"]:
        prompt = f"""
Word: "{word}" (Meaning: {meaning_vi}).
Difficulty: {diff}/100 ({level_desc}).
Task: Create a sentence missing the word "{word}". Replace "{word}" with "___".
Return JSON format:
{{
    "question_type": "{q_type}",
    "word": "{word}",
    "meaning_vi": "{meaning_vi}",
    "context": "Sentence with ___",
    "answer": "{word}"
}}
        """
        raw = call_ai(prompt, system_p)
        try:
            data = json.loads(raw)
            data["hint"] = generate_hint(word, diff)
            return data
        except:
            return {
                "question_type": q_type,
                "word": word,
                "meaning_vi": meaning_vi,
                "context": f"I want to ___ this (Nghĩa: {meaning_vi}).",
                "answer": word,
                "hint": generate_hint(word, diff)
            }

    # TYPE 2 (VN -> EN MCQ)
    elif q_type == "type_2":
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT word FROM words WHERE word != ? ORDER BY RANDOM() LIMIT 3", (word,))
        distractors = [r['word'] for r in c.fetchall()]
        conn.close()
        
        while len(distractors) < 3:
            distractors.append(f"option_{len(distractors)+1}")
            
        options = distractors + [word]
        random.shuffle(options)
        
        return {
            "question_type": "type_2",
            "word": word,
            "meaning_vi": meaning_vi,
            "prompt": f"Chọn từ tiếng Anh có nghĩa: '{meaning_vi}'",
            "options": options,
            "answer": word
        }

    # TYPE 3 (Listening MCQ)
    elif q_type == "type_3":
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT word FROM words WHERE word != ? ORDER BY RANDOM() LIMIT 3", (word,))
        distractors = [r['word'] for r in c.fetchall()]
        conn.close()
        
        while len(distractors) < 3:
            distractors.append(f"fake_{len(distractors)+1}")
            
        options = distractors + [word]
        random.shuffle(options)
        
        return {
            "question_type": "type_3",
            "word": word,
            "meaning_vi": meaning_vi,
            "prompt": f"Nghe audio và chọn từ đúng cho nghĩa: '{meaning_vi}'",
            "options": options,
            "answer": word
        }

    # TYPE 5 (IPA MCQ)
    elif q_type == "type_5":
        correct_ipa = word_row['ipa'] or "/.../"
        options = [correct_ipa, "/fəˈnɛtɪk/", "/sæmpəl/", "/ˈɒptɪməl/"]
        random.shuffle(options)
        
        return {
            "question_type": "type_5",
            "word": word,
            "meaning_vi": meaning_vi,
            "prompt": f"Chọn phiên âm IPA đúng cho từ: '{word}' ({meaning_vi})",
            "options": options,
            "answer": correct_ipa
        }

# ==========================================
# TAB 1: SCAN TEXT & CREATE WORDS
# ==========================================
def render_scan_tab():
    st.subheader("📥 Scan New English Text")
    st.write("Dán đoạn văn tiếng Anh vào đây. AI sẽ tự động lọc các từ vựng đáng học và không trùng với từ đã học.")

    text_input = st.text_area("Paste English text here...", height=180)
    
    if st.button("SCAN & CREATE WORDS", type="primary"):
        if not text_input.strip():
            st.warning("Vui lòng nhập văn bản tiếng Anh.")
            return

        with st.spinner("AI đang phân tích và trích xuất từ vựng..."):
            # Get existing words to prevent duplicates
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT word FROM words")
            existing_words = [r['word'].lower() for r in c.fetchall()]
            conn.close()

            prompt = f"""
Text: "{text_input}"

Existing learned words to EXCLUDE: {json.dumps(existing_words[:100])}

Task: Extract 5-10 useful English words/phrases from the text worth learning.
Rules:
1. Ignore basic words, proper nouns, and words already in the exclude list.
2. Contextual Vietnamese meaning.
3. Keep example sentences EXTREMELY SIMPLE (beginner level).
4. Assign relative difficulty 0-100 (default ~15 for new words).

Return RAW JSON list ONLY:
[
  {{
    "word": "example",
    "meaning_vi": "ví dụ",
    "meaning_en": "a representative form",
    "part_of_speech": "noun",
    "ipa": "/ɪɡˈzɑːm.pəl/",
    "topic": "General",
    "example_sentence": "This is a simple example.",
    "difficulty": 15
  }}
]
            """
            
            res_json = call_ai(prompt)
            if not res_json:
                return

            try:
                extracted = json.loads(res_json)
            except Exception as e:
                st.error("Lỗi khi đọc kết quả từ AI. Hãy thử lại!")
                return

            if not isinstance(extracted, list) or len(extracted) == 0:
                st.info("Không tìm thấy từ mới phù hợp trong đoạn văn này.")
                return

            # Save Batch & Words
            conn = get_db()
            c = conn.cursor()
            
            topic = extracted[0].get("topic", "General") if extracted else "General"
            c.execute("INSERT INTO scan_batches (source_text, topic) VALUES (?, ?)", (text_input, topic))
            scan_id = c.lastrowid

            saved_count = 0
            for item in extracted:
                w_str = item.get("word", "").strip()
                if not w_str:
                    continue
                try:
                    c.execute('''
                        INSERT INTO words (
                            word, normalized_word, meaning_vi, meaning_en, part_of_speech, 
                            ipa, topic, example_sentence, difficulty, status, scan_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?)
                    ''', (
                        w_str, w_str.lower(), item.get("meaning_vi", ""),
                        item.get("meaning_en", ""), item.get("part_of_speech", ""),
                        item.get("ipa", ""), item.get("topic", topic),
                        item.get("example_sentence", ""), item.get("difficulty", 15.0),
                        scan_id
                    ))
                    saved_count += 1
                except sqlite3.IntegrityError:
                    pass # Skip duplicates

            conn.commit()
            conn.close()

            st.success(f"🎉 Đã tìm thấy và lưu {saved_count} từ mới vào Notebook!")
            st.dataframe(pd.DataFrame(extracted)[["word", "meaning_vi", "part_of_speech", "ipa", "difficulty"]])

            # Trigger Check Reading
            check_and_generate_reading(topic)

# ==========================================
# PHASE 19 & 20: READING GENERATION & REVIEW
# ==========================================
def check_and_generate_reading(topic):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM words WHERE topic = ?", (topic,))
    topic_words = c.fetchall()
    
    if len(topic_words) >= 10:
        c.execute("SELECT * FROM readings WHERE topic = ?", (topic,))
        if not c.fetchone():
            word_list = [w['word'] for w in topic_words]
            min_diff = min([w['difficulty'] for w in topic_words])
            
            prompt = f"""
Topic: {topic}
Words to include: {', '.join(word_list)}
Target Difficulty: {min_diff}/100 (Keep reading text very easy to match lowest word difficulty).

Task: Generate a short 4-6 sentence English reading paragraph incorporating these words naturally.
Return JSON ONLY:
{{
   "content": "Short English passage..."
}}
            """
            res = call_ai(prompt)
            try:
                data = json.loads(res)
                c.execute('''
                    INSERT INTO readings (topic, words_used, difficulty, content, next_review)
                    VALUES (?, ?, ?, ?, ?)
                ''', (topic, json.dumps(word_list), min_diff, data['content'], datetime.now()))
                conn.commit()
            except:
                pass
    conn.close()

def render_reading_section():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM readings WHERE next_review <= ? OR next_review IS NULL LIMIT 1", (datetime.now(),))
    reading = c.fetchone()
    conn.close()

    if reading:
        st.write("---")
        st.subheader("📖 Reading Challenge (Luyện Dịch Bài Đọc)")
        st.info(f"Chủ đề: **{reading['topic']}** | Độ khó bài: **{int(reading['difficulty'])}/100**")
        st.markdown(f"> *{reading['content']}*")

        user_trans = st.text_area("Nhập bản dịch tiếng Việt của bạn vào đây:", key=f"read_{reading['reading_id']}")
        if st.button("Nộp bài dịch", key=f"btn_read_{reading['reading_id']}"):
            if user_trans.strip():
                with st.spinner("AI đang chấm điểm bản dịch..."):
                    prompt = f"""
Original English: "{reading['content']}"
User Vietnamese Translation: "{user_trans}"

Grade the translation. Return JSON ONLY:
{{
  "meaning_accuracy": 85,
  "comprehension": 90,
  "feedback": "Nhận xét chi tiết..."
}}
                    """
                    res = call_ai(prompt)
                    try:
                        result = json.loads(res)
                        acc = result.get('meaning_accuracy', 70)
                        comp = result.get('comprehension', 70)
                        score = 0.6 * acc + 0.4 * comp
                        
                        st.write(f"**Kết quả
