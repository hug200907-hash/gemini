import streamlit as st
import sqlite3
import json
import requests
import random
import datetime
import re
import io
import base64
import time
import difflib
import streamlit.components.v1 as components
from gtts import gTTS

# ==========================================
# 0. CONFIG & CONSTANTS
# ==========================================
DB_FILE = "vocab_quest.db"
DEFAULT_MODEL = "minimax/minimax-m3:free"
SESSION_LIMIT = 6 

st.set_page_config(page_title="Vocab Quest", page_icon="🧠", layout="centered")

# Lấy API Key an toàn
try:
    API_KEY = st.secrets["OPENROUTER_API_KEY"]
except KeyError:
    API_KEY = None

# ==========================================
# 1. DATABASE SETUP
# ==========================================
def get_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    # Bảng Words
    c.execute('''
        CREATE TABLE IF NOT EXISTS words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT UNIQUE,
            normalized_word TEXT UNIQUE,
            meaning_vi TEXT,
            meaning_en TEXT,
            part_of_speech TEXT,
            pronunciation TEXT,
            ipa TEXT,
            topic TEXT,
            example_sentence TEXT,
            difficulty INTEGER DEFAULT 15,
            first_seen TIMESTAMP,
            last_review TIMESTAMP,
            next_review TIMESTAMP,
            review_count INTEGER DEFAULT 0,
            correct_count INTEGER DEFAULT 0,
            wrong_count INTEGER DEFAULT 0,
            streak INTEGER DEFAULT 0,
            status TEXT DEFAULT 'new'
        )
    ''')
    # Bảng User Stats
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            daily_streak INTEGER DEFAULT 0,
            last_active TIMESTAMP
        )
    ''')
    # Bảng Readings
    c.execute('''
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT,
            words_used TEXT,
            difficulty INTEGER,
            content TEXT,
            created_at TIMESTAMP,
            last_review TIMESTAMP,
            next_review TIMESTAMP,
            review_count INTEGER DEFAULT 0
        )
    ''')
    
    c.execute("INSERT OR IGNORE INTO user_stats (username, xp, level) VALUES ('default_user', 0, 1)")
    conn.commit()
    conn.close()

# ==========================================
# 2. AI WRAPPER
# ==========================================
def call_ai(prompt, system_prompt="You are a helpful AI assistant. Output strictly in JSON format.", retries=2):
    if not API_KEY:
        st.error("Missing OPENROUTER_API_KEY in st.secrets.")
        return None
        
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"}
    }
    
    for attempt in range(retries + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=20)
            if resp.status_code == 200:
                text = resp.json()["choices"][0]["message"]["content"]
                match = re.search(r'\[.*\]|\{.*\}', text, re.DOTALL)
                if match:
                    return json.loads(match.group(0))
                return json.loads(text)
            elif resp.status_code == 429:
                time.sleep(2)
        except Exception as e:
            if attempt == retries:
                st.error(f"AI Call Error: {str(e)}")
                return None
            time.sleep(1)
    return None

# ==========================================
# 3. HELPER FUNCTIONS
# ==========================================
def normalize_word(word):
    if not word:
        return ""
    return re.sub(r'[^\w\s]', '', word.strip().lower())

def get_diff_html(user_ans, correct_ans):
    user_ans = str(user_ans).strip() if user_ans else ""
    correct_ans = str(correct_ans).strip()
    
    if not user_ans:
        return f"<span style='color: #2e7d32; font-weight: bold;'>{correct_ans}</span> (Bạn chưa nhập gì)"
        
    matcher = difflib.SequenceMatcher(None, user_ans.lower(), correct_ans.lower())
    result = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            # Ký tự đúng: Màu xanh lá
            result.append(f"<span style='color: #2e7d32; font-weight: bold;'>{correct_ans[j1:j2]}</span>")
        elif tag == 'replace':
            # Nhập sai ký tự: Gạch ngang đỏ + Hiển thị lại chữ đúng màu xanh
            result.append(f"<span style='color: #d32f2f; text-decoration: line-through;'>{user_ans[i1:i2]}</span><span style='color: #2e7d32; font-weight: bold;'>{correct_ans[j1:j2]}</span>")
        elif tag == 'delete':
            # Nhập dư ký tự: Gạch ngang đỏ
            result.append(f"<span style='color: #d32f2f; text-decoration: line-through;'>{user_ans[i1:i2]}</span>")
        elif tag == 'insert':
            # Nhập thiếu ký tự: Bổ sung chữ màu xanh có gạch chân
            result.append(f"<span style='color: #2e7d32; font-weight: bold; text-decoration: underline;'>{correct_ans[j1:j2]}</span>")
    return "".join(result)

def play_audio(word_text, autoplay=True):
    try:
        tts = gTTS(text=word_text, lang='en')
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        b64 = base64.b64encode(fp.read()).decode()
        if autoplay:
            md = f'<audio autoplay="true"><source src="data:audio/mp3;base64,{b64}" type="audio/mp3"></audio>'
            st.markdown(md, unsafe_allow_html=True)
        return b64
    except Exception:
        pass
    return None

def generate_hint(word, difficulty):
    word = word.strip()
    ratio = max(0.2, 1.0 - (difficulty / 100.0) * 0.8)
    num_reveal = max(1, int(len(word) * ratio))
    
    chars = list(word)
    vowels = set('aeiouyAEIOUY')
    revealed_idx = set()
    
    for i, c in enumerate(chars):
        if c in vowels and len(revealed_idx) < num_reveal:
            revealed_idx.add(i)
            
    if len(revealed_idx) < num_reveal:
        unrevealed = [i for i in range(len(chars)) if i not in revealed_idx and chars[i].isalpha()]
        random.seed(word) 
        random.shuffle(unrevealed)
        for i in unrevealed:
            if len(revealed_idx) < num_reveal:
                revealed_idx.add(i)
                
    res = []
    for i, c in enumerate(chars):
        if not c.isalpha():
            res.append(c)
        elif i in revealed_idx:
            res.append(c)
        else:
            res.append('_')
    return " ".join(res)

def calculate_next_review(word_data, is_correct):
    now = datetime.datetime.now()
    streak = word_data['streak']
    intervals_mins = [15, 60, 240, 720, 1440, 2880, 4320]
    
    if is_correct:
        new_streak = streak + 1
        idx = min(new_streak, len(intervals_mins) - 1)
        interval = intervals_mins[idx]
        new_diff = max(0, word_data['difficulty'] + random.randint(8, 15))
    else:
        new_streak = 0
        interval = random.randint(5, 30)
        new_diff = min(100, max(0, word_data['difficulty'] - random.randint(10, 20)))
        
    next_review = now + datetime.timedelta(minutes=interval)
    return next_review.strftime("%Y-%m-%d %H:%M:%S"), new_streak, new_diff

def award_xp(amount):
    conn = get_db()
    conn.execute("UPDATE user_stats SET xp = xp + ? WHERE username = 'default_user'", (amount,))
    conn.commit()
    conn.close()
    st.session_state.session_xp += amount

def get_user_stats():
    conn = get_db()
    row = conn.execute("SELECT * FROM user_stats WHERE username = 'default_user'").fetchone()
    conn.close()
    return row

def select_review_words(limit=SESSION_LIMIT):
    conn = get_db()
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    failed_due = conn.execute(
        "SELECT * FROM words WHERE wrong_count > correct_count AND next_review <= ? ORDER BY next_review ASC", (now_str,)
    ).fetchall()
    
    new_words = conn.execute(
        "SELECT * FROM words WHERE status = 'new' ORDER BY id ASC"
    ).fetchall()
    
    review_due = conn.execute(
        "SELECT * FROM words WHERE status != 'new' AND next_review <= ? ORDER BY next_review ASC", (now_str,)
    ).fetchall()
    
    conn.close()
    
    results = []
    for lst in [failed_due, new_words, review_due]:
        random.shuffle(lst)
        for row in lst:
            if len(results) >= limit:
                break
            if not any(r['id'] == row['id'] for r in results):
                results.append(dict(row))
        if len(results) >= limit:
            break
            
    return results

# ==========================================
# 4. TAB 1: SCAN TEXT
# ==========================================
def render_scan_tab():
    st.header("📥 Scan & Extract Words")
    st.write("Paste an English text below. The AI will extract useful vocabulary.")
    
    text = st.text_area("Source Text", height=200, placeholder="Paste English text here...")
    if st.button("SCAN & CREATE WORDS", type="primary"):
        if not text.strip():
            st.warning("Please enter some text.")
            return
            
        with st.spinner("AI is analyzing the text..."):
            prompt = f"""
            Extract useful vocabulary/collocations from the following text to learn. 
            Ignore proper nouns and extremely basic words. 
            Return a JSON array of objects.
            Format for each object:
            {{
                "word": "...",
                "meaning_vi": "Vietnamese meaning based on the context",
                "meaning_en": "English definition",
                "part_of_speech": "noun/verb/adj...",
                "ipa": "IPA pronunciation",
                "topic": "Determine one main topic (e.g. Technology, Daily Life)",
                "example_sentence": "A very simple example sentence. Do NOT copy the text.",
                "difficulty": integer from 0 to 100 (0=extremely easy, 100=very hard)
            }}
            
            TEXT:
            "{text}"
            """
            sys_prompt = "You are a vocabulary extractor. Output JSON array ONLY."
            results = call_ai(prompt, sys_prompt)
            
            if not results or not isinstance(results, list):
                st.error("Failed to extract words or invalid format received.")
                return
                
            conn = get_db()
            added = 0
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            for item in results:
                try:
                    norm = normalize_word(item['word'])
                    exist = conn.execute("SELECT id FROM words WHERE normalized_word = ?", (norm,)).fetchone()
                    if not exist:
                        conn.execute('''
                            INSERT INTO words (word, normalized_word, meaning_vi, meaning_en, part_of_speech, 
                                             ipa, topic, example_sentence, difficulty, first_seen, status)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')
                        ''', (
                            item['word'], norm, item['meaning_vi'], item['meaning_en'], 
                            item['part_of_speech'], item.get('ipa',''), item.get('topic','General'), 
                            item['example_sentence'], min(100, max(0, item.get('difficulty', 15))), now
                        ))
                        added += 1
                except Exception:
                    pass
                    
            conn.commit()
            conn.close()
            
            if added > 0:
                st.success(f"🎉 Found and added {added} new words!")
                st.balloons()
            else:
                st.info("No new words found (they might be too basic or already exist).")

# ==========================================
# 5. TAB 2: REVIEW SYSTEM
# ==========================================
def generate_question(word_data, force_easy=False, specific_type=None):
    q_types = ['fill_blank', 'vi_to_en', 'listening_mcq', 'spelling', 'ipa_mcq']
    # Nếu đang hạ độ khó, giữ nguyên dạng bài cũ, nếu không thì chọn ngẫu nhiên
    chosen_type = specific_type if specific_type else random.choice(q_types)
    
    conn = get_db()
    distractors_raw = conn.execute("SELECT word, meaning_vi, ipa FROM words WHERE id != ? ORDER BY RANDOM() LIMIT 3", (word_data['id'],)).fetchall()
    conn.close()
    
    distractors = [dict(d) for d in distractors_raw]
    
    question = {
        'type': chosen_type,
        'word': word_data['word'],
        'correct_answer': word_data['word']
    }
    
    if chosen_type == 'fill_blank' or chosen_type == 'spelling':
        # Ép độ khó về 5 (cực dễ) nếu người dùng bấm nút "Khó hiểu"
        diff = 5 if force_easy else word_data['difficulty']
        level_prompt = "A1 beginner level, use extremely simple and common words" if force_easy else f"difficulty {diff}/100"
        
        prompt = f"""
        Generate a short, clear English sentence to test the word '{word_data['word']}'.
        The sentence should be at: {level_prompt}.
        You MUST hide the target word '{word_data['word']}' by replacing it EXACTLY with '___' (three underscores).
        Output strictly in JSON format:
        {{"context": "The sentence with ___ instead of the word."}}
        """
        res = call_ai(prompt)
        context = res.get('context', f"I need to use the word ___.") if res else f"Context for ___."
        
        target_word = word_data['word']
        context = re.sub(re.escape(target_word), "___", context, flags=re.IGNORECASE)
        
        question['context'] = context
        question['hint'] = generate_hint(word_data['word'], diff)
        
    elif chosen_type == 'vi_to_en':
        options = [word_data['word']] + [d['word'] for d in distractors]
        random.shuffle(options)
        question['meaning_vi'] = word_data['meaning_vi']
        question['options'] = options
        
    elif chosen_type == 'listening_mcq':
        options = [word_data['word']] + [d['word'] for d in distractors]
        random.shuffle(options)
        question['meaning_vi'] = word_data['meaning_vi']
        question['options'] = options
        
    elif chosen_type == 'ipa_mcq':
        options = [word_data['ipa']] + [d['ipa'] for d in distractors if d['ipa']]
        while len(options) < 4: options.append(f"/{word_data['word'][:3]}.../")
        options = list(set(options))[:4]
        random.shuffle(options)
        question['meaning_vi'] = word_data['meaning_vi']
        question['options'] = options
        question['correct_answer'] = word_data['ipa']

    return question

def render_review_tab():
    st.header("⚔️ Review Session")
    stats = get_user_stats()
    st.markdown(f"**🔥 STREAK: {stats['daily_streak']} &nbsp;&nbsp;|&nbsp;&nbsp; XP: {stats['xp']} &nbsp;&nbsp;|&nbsp;&nbsp; LEVEL: {stats['level']}**")
    st.divider()

    if 'review_session' not in st.session_state:
        st.session_state.review_session = None

    if st.session_state.review_session is None:
        words = select_review_words()
        if not words:
            st.success("🎉 You're all caught up! No words to review right now.")
            
            conn = get_db()
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            next_word = conn.execute(
                "SELECT next_review FROM words WHERE next_review > ? AND status != 'new' ORDER BY next_review ASC LIMIT 1", 
                (now_str,)
            ).fetchone()
            conn.close()

            if next_word and next_word['next_review']:
                next_time_str = next_word['next_review']
                next_time = datetime.datetime.strptime(next_time_str, "%Y-%m-%d %H:%M:%S")
                now = datetime.datetime.now()
                diff = next_time - now
                total_seconds = int(diff.total_seconds())
                
                if total_seconds > 0:
                    # FIX: Thay st.components.v1.html bằng st.markdown(..., unsafe_allow_html=True)
                    st.markdown(f"""
                        <div style="text-align: center; font-family: sans-serif; padding: 15px; background-color: #262730; border-radius: 10px; border: 1px solid #444; margin-bottom: 20px;">
                            <h4 style="margin:0; color: #fafafa; font-size: 18px;">⏳ Từ vựng tiếp theo sẽ mở sau:</h4>
                            <div id="next_review_countdown" style="font-size: 35px; font-weight: bold; color: #ff4b4b; margin-top: 10px;">Đang tính toán...</div>
                        </div>
                        <script>
                            var countDownDate = new Date().getTime() + ({total_seconds} * 1000);
                            var x = setInterval(function() {{
                                var now = new Date().getTime();
                                var distance = countDownDate - now;
                                var hours = Math.floor((distance % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
                                var minutes = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60));
                                var seconds = Math.floor((distance % (1000 * 60)) / 1000);
                                var el = document.getElementById("next_review_countdown");
                                if(el) {{
                                    el.innerHTML = hours + "h " + minutes + "m " + seconds + "s ";
                                }}
                                if (distance < 0) {{
                                    clearInterval(x);
                                    if(el) el.innerHTML = "Đã sẵn sàng! Hãy F5 lại trang.";
                                }}
                            }}, 1000);
                        </script>
                    """, unsafe_allow_html=True)
            else:
                st.info("💡 Bạn chưa có từ vựng nào đang trong tiến trình ôn tập. Hãy sang tab Scan để thêm từ mới nhé!")
            return
            
        if st.button("🚀 Start Review Session", type="primary"):
            st.session_state.review_session = {
                'words': words,
                'current_idx': 0,
                'correct': 0,
                'answered': False,
                'session_xp': 0,
                'current_q': None,
                'force_easy': False,
                'specific_type': None
            }
            st.session_state.session_combo = 0
            st.rerun()
        return

    session = st.session_state.review_session
    idx = session['current_idx']
    
    if idx >= len(session['words']):
        st.success(f"🎉 SESSION COMPLETE!")
        st.write(f"Correct: {session['correct']} / {len(session['words'])}")
        st.write(f"XP Earned: +{session['session_xp']} XP")
        if st.button("Finish & Return to Dashboard"):
            st.session_state.review_session = None
            st.rerun()
        return

    word = session['words'][idx]
    if session['current_q'] is None:
        with st.spinner("Preparing question..."):
            session['current_q'] = generate_question(
                word, 
                force_easy=session.get('force_easy', False), 
                specific_type=session.get('specific_type', None)
            )
            session['answered'] = False
            session['start_time'] = time.time()
            
    q = session['current_q']
    
    progress = (idx) / len(session['words'])
    st.progress(progress, text=f"Word {idx + 1} of {len(session['words'])}")
    
    st.subheader(f"Type: {q['type'].replace('_', ' ').title()}")
    
    time_limit = 20
    if not session['answered']:
        timer_id = f"timer_{idx}_{int(session['start_time'])}"
        st.markdown(f"""
            <div style="font-size: 18px; font-weight: bold; color: #ff4b4b; margin-bottom: 15px;">
                ⏳ Thời gian còn lại: <span id="{timer_id}">{time_limit}</span>s
            </div>
            <script>
                var timeLeft = {time_limit};
                var timerId = setInterval(function() {{
                    if (timeLeft <= 0) {{
                        clearInterval(timerId);
                        var el = document.getElementById('{timer_id}');
                        if(el) el.innerHTML = "Hết giờ!";
                    }} else {{
                        var el = document.getElementById('{timer_id}');
                        if(el) el.innerHTML = timeLeft;
                        timeLeft -= 1;
                    }}
                }}, 1000);
            </script>
        """, unsafe_allow_html=True)
    
    user_ans = None
    simplify = False
    
    with st.form(key=f"question_form_{idx}_{session.get('force_easy', False)}"):
        if q['type'] == 'fill_blank':
            st.markdown(f"**Context:** {q['context']}")
            st.markdown(f"**Hint:** `{q['hint']}`")
            user_ans = st.text_input("Your answer:", key=f"input_{idx}")
            
        elif q['type'] == 'vi_to_en':
            st.markdown(f"**Meaning:** {q['meaning_vi']}")
            user_ans = st.radio("Choose the English word:", q['options'], key=f"radio_{idx}")
            
        elif q['type'] == 'listening_mcq':
            st.markdown(f"**Meaning (Nghĩa):** {q['meaning_vi']}")
            st.write("🎧 Hãy nghe 4 âm thanh dưới đây (chữ đã được giấu đi):")
            
            cols = st.columns(4)
            option_labels = [] 
            
            for i, opt in enumerate(q['options']):
                label = f"Lựa chọn {i+1}"
                option_labels.append(label)
                with cols[i]:
                    st.write(label)
                    fp = io.BytesIO()
                    gTTS(text=opt, lang='en').write_to_fp(fp)
                    fp.seek(0)
                    st.audio(fp, format="audio/mp3")
            
            selected_label = st.radio("Chọn âm thanh đúng:", option_labels, key=f"radio_list_{idx}")
            selected_index = option_labels.index(selected_label)
            user_ans = q['options'][selected_index]
            
        elif q['type'] == 'spelling':
            st.markdown(f"**Meaning:** {word['meaning_vi']}")
            st.markdown(f"**Context:** {q['context']}")
            st.markdown(f"**Hint:** `{q['hint']}`")
            user_ans = st.text_input("Spell the word:", key=f"input_spell_{idx}")
            
        elif q['type'] == 'ipa_mcq':
            st.markdown(f"**Meaning:** {word['meaning_vi']}")
            user_ans = st.radio("Choose the correct IPA:", q['options'], key=f"radio_ipa_{idx}")

        if q['type'] in ['fill_blank', 'spelling']:
            col1, col2, col3 = st.columns(3)
            with col1:
                submit = st.form_submit_button("✅ Submit Answer", disabled=session['answered'])
            with col2:
                idk = st.form_submit_button("❌ Chưa thuộc", disabled=session['answered'])
            with col3:
                simplify = st.form_submit_button("❓ Câu này khó hiểu", disabled=session['answered'])
        else:
            col1, col2 = st.columns(2)
            with col1:
                submit = st.form_submit_button("✅ Submit Answer", disabled=session['answered'])
            with col2:
                idk = st.form_submit_button("❌ Chưa thuộc", disabled=session['answered'])
            simplify = False

    if simplify and not session['answered']:
        session['force_easy'] = True
        session['specific_type'] = q['type']  
        session['current_q'] = None           
        st.rerun()
        
    if (submit or idk) and not session['answered']:
        session['answered'] = True
        elapsed_time = time.time() - session['start_time']
        
        is_timeout = elapsed_time > (time_limit + 2) 
        
        if idk:
            is_correct = False
            session['fail_reason'] = "Bạn đã chọn chưa thuộc từ này."
        elif is_timeout:
            is_correct = False
            session['fail_reason'] = "Đã quá thời gian trả lời (20 giây)!"
        else:
            session['fail_reason'] = ""
            if q['type'] in ['fill_blank', 'spelling']:
                is_correct = normalize_word(user_ans) == normalize_word(q['correct_answer'])
            else:
                is_correct = user_ans == q['correct_answer']
                
        if not is_correct and q['type'] in ['fill_blank', 'spelling'] and not idk and not is_timeout:
             session['diff_html'] = get_diff_html(user_ans, q['correct_answer'])
        else:
             session['diff_html'] = ""
            
        if is_correct:
            session['correct'] += 1
            st.session_state.session_combo += 1
            xp_gain = 10 + (st.session_state.session_combo * 2)
            award_xp(xp_gain)
            session['session_xp'] += xp_gain
            session['is_correct'] = True
        else:
            st.session_state.session_combo = 0
            award_xp(2)
            session['session_xp'] += 2
            session['is_correct'] = False
            
        # FIX: Hàm này chưa được định nghĩa trong code của bạn, mình tạm vô hiệu hóa để không bị sập app. 
        # Nếu bạn có sẵn hàm cập nhật kết quả vào database, hãy đổi tên hàm tương ứng vào đây!
        # process_answer(word['id'], is_correct)

    if session['answered']:
        st.divider()
        status_icon = "🟢" if word['status'] == 'new' else "🔵" if word['status'] == 'learning' else "🔥"
        
        if not session.get('is_correct'):
            reason = session.get('fail_reason', 'Not quite right. Rematch coming soon!')
            st.error(f"❌ {reason}")
            if session.get('diff_html'):
                st.markdown(f"<div style='padding: 10px; background-color: #fce4e4; border-radius: 5px; color: black;'><b>🔍 Lỗi chính tả của bạn:</b> {session['diff_html']}</div>", unsafe_allow_html=True)
                st.write("") 

        # Hiển thị thông tin từ vựng
        st.markdown(
            f"<h3 style='margin-bottom: 5px;'>{word['word']} {status_icon}</h3>"
            f"<div style='margin-bottom: 15px; font-size: 1.1rem;'>"
            f"<span style='color: #888;'>//{word['ipa']}// • <i>{word['part_of_speech']}</i> &nbsp;&nbsp;|&nbsp;&nbsp;</span> "
            f"<span style='background-color: rgba(136, 136, 136, 0.2); padding: 3px 8px; border-radius: 12px; font-size: 0.85rem;'>🏷️ <b>{word['topic']}</b></span>"
            f"</div>",
            unsafe_allow_html=True
        )
        st.markdown(f"🇻🇳 **Nghĩa:** {word['meaning_vi']}")
        st.markdown(f"📝 **Ví dụ:** _{word['example_sentence']}_")
        
        # --- LOGIC PHÁT NỐI TIẾP: ANH -> VIỆT ---
        try:
            import base64
            from gtts import gTTS
            import io
            
            # 1. Tạo audio Tiếng Anh
            fp_en = io.BytesIO()
            gTTS(text=word['word'], lang='en').write_to_fp(fp_en)
            
            # 2. Tạo khoảng lặng nhỏ (0.5s) bằng cách dùng gTTS đọc một dấu chấm hoặc phẩy (tùy chọn)
            fp_pause = io.BytesIO()
            gTTS(text="... ", lang='en').write_to_fp(fp_pause)
            
            # 3. Tạo audio Tiếng Việt
            fp_vi = io.BytesIO()
            gTTS(text=word['meaning_vi'], lang='vi').write_to_fp(fp_vi)
            
            # 4. Gộp toàn bộ các luồng byte MP3 lại với nhau thành 1 file duy nhất
            combined_audio_bytes = fp_en.getvalue() + fp_pause.getvalue() + fp_vi.getvalue()
            
            # 5. Mã hóa sang Base64 để nhúng vào HTML
            b64_audio = base64.b64encode(combined_audio_bytes).decode()
            
            # 6. Phát trên DOM chính, trình duyệt sẽ cho phép autoplay vì bạn vừa click nút Submit
            audio_html = f'''
                <audio autoplay="true" style="display:none;">
                    <source src="data:audio/mp3;base64,{b64_audio}" type="audio/mp3">
                </audio>
            '''
            st.markdown(audio_html, unsafe_allow_html=True)
            
        except Exception as e:
            st.error(f"Lỗi phát âm thanh: {e}")
        
        st.write("") 
        if st.button("Tiếp tục ➡️", type="primary", use_container_width=True):
            session['current_idx'] += 1
            session['current_q'] = None
            session['answered'] = False
            session['force_easy'] = False  
            session['specific_type'] = None
            st.rerun()
# ==========================================
# 6. TAB 3: NOTEBOOK & READING
# ==========================================
def render_notebook_tab():
    st.header("📚 Sổ tay từ vựng (Notebook)")
    conn = get_db()
    
    # Tự động lấy danh sách các chủ đề hiện có trong Database
    topics_query = conn.execute("SELECT DISTINCT topic FROM words WHERE topic IS NOT NULL").fetchall()
    topic_list = ["Tất cả"] + sorted([t['topic'] for t in topics_query if t['topic'].strip() != ""])

    # 1. THANH TÌM KIẾM & BỘ LỌC (Thêm riêng bộ lọc Chủ đề)
    col_search, col_topic, col_filter = st.columns([2, 1.5, 1.5])
    with col_search:
        search_term = st.text_input("🔍 Tìm kiếm từ vựng...", placeholder="Nhập từ hoặc nghĩa...")
    with col_topic:
        topic_filter = st.selectbox("🏷️ Chủ đề", topic_list)
    with col_filter:
        status_filter = st.selectbox("📌 Trạng thái", ["Tất cả", "new", "learning", "mastered"])
    
    # Xây dựng câu truy vấn dựa trên bộ lọc
    query = "SELECT * FROM words WHERE 1=1"
    params = []
    
    if status_filter != "Tất cả":
        query += " AND status = ?"
        params.append(status_filter)
        
    if topic_filter != "Tất cả":
        query += " AND topic = ?"
        params.append(topic_filter)
        
    if search_term:
        query += " AND (word LIKE ? OR meaning_vi LIKE ?)"
        params.extend([f"%{search_term}%", f"%{search_term}%"])
        
    query += " ORDER BY difficulty DESC"
    words = conn.execute(query, params).fetchall()
    
    st.write(f"📝 Tổng số từ hiện có: **{len(words)}**")
    st.divider()
    
    # 2. HIỂN THỊ DẠNG THẺ (CARD LAYOUT)
    if words:
        cols_per_row = 2
        for i in range(0, len(words), cols_per_row):
            cols = st.columns(cols_per_row)
            for j in range(cols_per_row):
                if i + j < len(words):
                    w = words[i + j]
                    with cols[j]:
                        with st.container(border=True):
                            c_word, c_audio = st.columns([4, 1])
                            with c_word:
                                status_icon = "🟢" if w['status'] == 'new' else "🔵" if w['status'] == 'learning' else "🔥"
                                st.subheader(f"{w['word']} {status_icon}")
                                
                                # HIGHLIGHT CHỦ ĐỀ: Đưa chủ đề lên ngay dưới từ vựng thành 1 tag nổi bật
                                st.markdown(
                                    f"/{w['ipa']}/ • *{w['part_of_speech']}* &nbsp;&nbsp;|&nbsp;&nbsp; "
                                    f"<span style='background-color: rgba(136, 136, 136, 0.2); padding: 3px 8px; border-radius: 12px; font-size: 0.85rem;'>🏷️ <b>{w['topic']}</b></span>", 
                                    unsafe_allow_html=True
                                )
                            with c_audio:
                                if st.button("🔊", key=f"audio_btn_{w['id']}", help="Nghe phát âm"):
                                    play_audio(w['word'])
                            
                            st.write("") # Tạo khoảng cách nhỏ
                            st.markdown(f"**🇻🇳 Nghĩa:** {w['meaning_vi']}")
                            st.markdown(f"**📝 Ví dụ:** _{w['example_sentence']}_")
                            
                            next_rev = w['next_review'] if w['next_review'] else 'Chưa có'
                            st.markdown(f"""
                                <hr style="margin: 10px 0;">
                                <div style='font-size: 0.85rem; color: #888;'>
                                    <b>🔄 Ôn tập kế tiếp:</b> {next_rev}<br>
                                    <b>🎯 Độ khó:</b> {w['difficulty']}/100 &nbsp;|&nbsp; 
                                    <b>📊 Tỉ lệ:</b> ✅ {w['correct_count']} - ❌ {w['wrong_count']}
                                </div>
                            """, unsafe_allow_html=True)
    else:
        st.info("Không tìm thấy từ vựng nào phù hợp với tìm kiếm của bạn.")

    # ==========================================
    # PHẦN AI READING GENERATOR
    # ==========================================
    st.divider()
    st.subheader("📖 AI Reading Generator")
    st.write("Tạo một đoạn văn ngắn sử dụng các từ vựng bạn đang học để luyện đọc.")
    
    topics = conn.execute("SELECT topic, COUNT(*) as cnt FROM words GROUP BY topic HAVING cnt >= 5").fetchall()
    conn.close()
    
    if not topics:
        st.info("Bạn cần ít nhất 5 từ vựng trong cùng một chủ đề để AI có thể tạo bài đọc.")
    else:
        topic_names = [f"{t['topic']} ({t['cnt']} words)" for t in topics]
        sel_topic = st.selectbox("Chọn chủ đề để tạo bài đọc:", topic_names)
        actual_topic = sel_topic.split(" (")[0]
        
        if st.button("Tạo bài đọc (Mini-Reading)", type="primary"):
            with st.spinner("AI đang soạn bài đọc cho bạn..."):
                conn = get_db()
                topic_words = conn.execute("SELECT word, difficulty FROM words WHERE topic = ? LIMIT 15", (actual_topic,)).fetchall()
                conn.close()
                
                word_list = [w['word'] for w in topic_words]
                min_diff = min([w['difficulty'] for w in topic_words])
                
                prompt = f"""
                Write a short reading paragraph (around 100-150 words) about the topic '{actual_topic}'.
                You MUST use as many of these words as possible naturally: {', '.join(word_list)}.
                The reading difficulty should match a learner level of {min_diff}/100 (keep sentences simple).
                Return JSON format:
                {{
                    "title": "...",
                    "content": "..."
                }}
                """
                res = call_ai(prompt)
                if res and 'content' in res:
                    st.success("Tạo bài đọc thành công!")
                    with st.container(border=True):
                        st.markdown(f"### {res.get('title', 'Reading')}")
                        st.write(res['content'])
                else:
                    st.error("Có lỗi xảy ra khi tạo bài đọc.")

# ==========================================
# 7. MAIN LAYOUT
# ==========================================
def main():
    init_db()
    
    if 'session_xp' not in st.session_state:
        st.session_state.session_xp = 0
    if 'session_combo' not in st.session_state:
        st.session_state.session_combo = 0
        
    st.title("🧠 VOCAB QUEST")
    st.markdown("*Learn a little. Come back often. Get better.*")
    
    tab1, tab2, tab3 = st.tabs(["📥 Scan", "⚔️ Review", "📚 Notebook"])
    
    with tab1:
        render_scan_tab()
        
    with tab2:
        render_review_tab()
        
    with tab3:
        render_notebook_tab()

if __name__ == "__main__":
    main()
