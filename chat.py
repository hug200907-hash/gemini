import streamlit as st
import json
import os
import re
import random
import time
import base64
from datetime import datetime, timedelta
import requests

# ==========================================
# 0. STREAMLIT CONFIG & CONSTANTS
# ==========================================
st.set_page_config(page_title="Vocab Master", page_icon="🔥", layout="wide")

DATA_FILE = "vocabulary_data.json"
MODEL_NAME = "minimax/minimax-m3:free"
# API Key được lấy từ st.secrets
try:
    OPENROUTER_API_KEY = st.secrets["OPENROUTER_API_KEY"]
except:
    OPENROUTER_API_KEY = ""

# ==========================================
# 1. CORE DATA MANAGEMENT
# ==========================================
def get_default_data():
    return {
        "words": {},
        "stats": {
            "xp": 0,
            "level": 1,
            "streak": 0,
            "last_active": str(datetime.now().date()),
            "perfect_sessions": 0,
            "total_mastered": 0
        },
        "readings": [],
        "topics": {}
    }

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data
        except Exception as e:
            st.error(f"Lỗi đọc dữ liệu: {e}")
            return get_default_data()
    else:
        return get_default_data()

def save_data():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(st.session_state.db, f, ensure_ascii=False, indent=4)
    except Exception as e:
        st.error(f"Lỗi lưu dữ liệu: {e}")

if "db" not in st.session_state:
    st.session_state.db = load_data()

# Khởi tạo các biến session state cần thiết
if "review_state" not in st.session_state:
    st.session_state.review_state = {
        "phase": "idle", # idle, question, feedback
        "session_words": [],
        "current_index": 0,
        "wrong_temp": [],
        "correct_temp": [],
        "current_question": None,
        "last_answer_correct": None,
        "last_user_answer": "",
        "session_score": 0
    }

# ==========================================
# 2. HELPER FUNCTIONS & GAMIFICATION
# ==========================================
def check_daily_streak():
    today = str(datetime.now().date())
    last_active = st.session_state.db["stats"].get("last_active", today)
    if last_active != today:
        last_date = datetime.strptime(last_active, "%Y-%m-%d").date()
        current_date = datetime.strptime(today, "%Y-%m-%d").date()
        if (current_date - last_date).days == 1:
            st.session_state.db["stats"]["streak"] += 1
        else:
            st.session_state.db["stats"]["streak"] = 1 # Reset streak
        st.session_state.db["stats"]["last_active"] = today
        save_data()

def add_xp(amount):
    st.session_state.db["stats"]["xp"] += amount
    current_xp = st.session_state.db["stats"]["xp"]
    # Logic Level: Level N cần N * 100 XP
    current_level = st.session_state.db["stats"]["level"]
    next_level_xp = current_level * 100
    if current_xp >= next_level_xp:
        st.session_state.db["stats"]["level"] += 1
        st.session_state.db["stats"]["xp"] = current_xp - next_level_xp
        st.toast(f"🎉 Lên cấp! Bạn đã đạt Level {st.session_state.db['stats']['level']}", icon="🌟")
    save_data()

def play_audio(word_en, word_vi):
    """
    Sử dụng trình duyệt SpeechSynthesis API bọc trong IFrame để phát âm thanh.
    Đảm bảo Streamlit không bị reload hoặc xung đột.
    """
    html_code = f"""
    <html>
    <body>
        <script>
            function playSound() {{
                window.speechSynthesis.cancel();
                let en = new SpeechSynthesisUtterance("{word_en}");
                en.lang = "en-US";
                en.rate = 1.1;
                let vi = new SpeechSynthesisUtterance("{word_vi}");
                vi.lang = "vi-VN";
                vi.rate = 1.2;
                
                en.onend = function() {{
                    window.speechSynthesis.speak(vi);
                }};
                window.speechSynthesis.speak(en);
            }}
            playSound();
        </script>
    </body>
    </html>
    """
    b64 = base64.b64encode(html_code.encode()).decode()
    # Tuân thủ: Dùng st.markdown iframe thay vì components.v1.html
    st.markdown(f'<iframe src="data:text/html;base64,{b64}" width="0" height="0" style="border:none; display:none;" allow="autoplay"></iframe>', unsafe_allow_html=True)

def play_audio_en_only(word_en):
    html_code = f"""
    <html>
    <body>
        <script>
            window.speechSynthesis.cancel();
            let en = new SpeechSynthesisUtterance("{word_en}");
            en.lang = "en-US";
            en.rate = 1.0;
            window.speechSynthesis.speak(en);
        </script>
    </body>
    </html>
    """
    b64 = base64.b64encode(html_code.encode()).decode()
    st.markdown(f'<iframe src="data:text/html;base64,{b64}" width="0" height="0" style="border:none; display:none;" allow="autoplay"></iframe>', unsafe_allow_html=True)

# ==========================================
# 3. AI & OPENROUTER LOGIC
# ==========================================
def extract_json(text):
    try:
        # Thử parse trực tiếp
        return json.loads(text)
    except:
        pass
    # Dùng regex tìm block JSON
    match = re.search(r'\{.*\}|\[.*\]', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except:
            pass
    return None

def call_ai(prompt, system_prompt="You are a helpful AI JSON generator.", retries=2):
    if not OPENROUTER_API_KEY:
        st.error("Chưa cấu hình OPENROUTER_API_KEY trong st.secrets!")
        return None
        
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://vocabmaster.streamlit.app",
        "X-Title": "VocabMaster"
    }
    
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt + "\nIMPORTANT: ONLY OUTPUT VALID JSON. NO MARKDOWN, NO EXPLANATION, NO CHINESE."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3
    }
    
    for attempt in range(retries):
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            json_data = extract_json(content)
            if json_data:
                return json_data
        except Exception as e:
            time.sleep(2) # Đợi trước khi retry
    
    return None

# ==========================================
# 4. SPACED REPETITION & SCHEDULING
# ==========================================
def calculate_next_review(word_data, result_type):
    """
    result_type: 'correct', 'wrong', 'not_remember', 'not_understand'
    Interval rất ngắn theo yêu cầu: phút -> giờ -> vài ngày.
    """
    now = datetime.now()
    diff = word_data.get("difficulty", 50)
    rev_count = word_data.get("review_count", 0)
    
    if result_type == "correct":
        word_data["correct_count"] = word_data.get("correct_count", 0) + 1
        word_data["difficulty"] = min(100, diff + random.randint(5, 10))
        word_data["status"] = "learning" if rev_count < 5 else "mastered"
        
        # Tăng interval mạnh nếu từ dễ, nhẹ nếu từ khó
        base_minutes = 30 if rev_count == 0 else (60 * (rev_count ** 1.5))
        factor = (100 - diff) / 50.0  # diff cao -> factor thấp -> chờ ít hơn
        interval_minutes = base_minutes * max(0.5, factor)
        
        # Max interval khoảng 5 ngày (7200 phút) để ôn liên tục
        interval_minutes = min(interval_minutes, 7200)
        
    elif result_type == "wrong":
        word_data["wrong_count"] = word_data.get("wrong_count", 0) + 1
        word_data["difficulty"] = max(0, diff - random.randint(5, 15))
        word_data["status"] = "learning"
        interval_minutes = 15 # Sai -> ôn lại sau 15 phút
        
    elif result_type == "not_remember":
        word_data["difficulty"] = max(0, diff - 8)
        word_data["status"] = "learning"
        interval_minutes = 30 # Không thuộc -> 30 phút
        
    elif result_type == "not_understand":
        word_data["difficulty"] = max(0, diff - 15)
        word_data["status"] = "learning"
        interval_minutes = 5 # Không hiểu -> 5 phút
        
    word_data["review_count"] = rev_count + 1
    word_data["last_review"] = now.isoformat()
    word_data["next_review"] = (now + timedelta(minutes=interval_minutes)).isoformat()
    
    return word_data

def get_due_words():
    now = datetime.now()
    due = []
    new = []
    
    for w_id, w_data in st.session_state.db["words"].items():
        if w_data["status"] == "new":
            new.append(w_data)
        elif w_data.get("next_review"):
            next_rev = datetime.fromisoformat(w_data["next_review"])
            if next_rev <= now:
                due.append(w_data)
                
    return due, new

def build_session(max_words=6):
    wrong_temp = st.session_state.review_state["wrong_temp"]
    due_words, new_words = get_due_words()
    
    session = []
    added_ids = set()
    
    # 1. Ưu tiên từ sai ở session trước
    for w in wrong_temp:
        if w["word"] not in added_ids and len(session) < max_words:
            session.append(w)
            added_ids.add(w["word"])
            
    # Xóa wrong_temp vì đã lấy vào session
    st.session_state.review_state["wrong_temp"] = []
    
    # 2. Lấy từ đến hạn
    random.shuffle(due_words)
    for w in due_words:
        if w["word"] not in added_ids and len(session) < max_words:
            session.append(w)
            added_ids.add(w["word"])
            
    # 3. Lấy từ mới
    random.shuffle(new_words)
    for w in new_words:
        if w["word"] not in added_ids and len(session) < max_words:
            session.append(w)
            added_ids.add(w["word"])
            
    random.shuffle(session)
    return session

# ==========================================
# 5. QUESTION GENERATION
# ==========================================
def generate_hint(word, difficulty):
    """
    Ưu tiên nguyên âm, tránh dính sát nhau nếu có thể.
    Độ khó cao -> ít gợi ý.
    """
    vowels = "aeiouAEIOU"
    word_len = len(word)
    
    # Tỷ lệ hiển thị chữ dựa trên độ khó
    if difficulty < 30: show_ratio = 0.5
    elif difficulty < 60: show_ratio = 0.3
    elif difficulty < 85: show_ratio = 0.15
    else: show_ratio = 0.0 # Không gợi ý
    
    num_hints = int(word_len * show_ratio)
    if num_hints == 0 and show_ratio > 0: num_hints = 1
    
    if num_hints == 0:
        return "_ " * word_len
        
    indices_to_show = set()
    
    # 1. Ưu tiên nguyên âm
    vowel_indices = [i for i, c in enumerate(word) if c in vowels]
    random.shuffle(vowel_indices)
    
    for idx in vowel_indices:
        if len(indices_to_show) < num_hints:
            # Check tránh sát nhau nếu có thể
            if not any(abs(idx - shown) == 1 for shown in indices_to_show):
                indices_to_show.add(idx)
            elif random.random() < 0.3: # Thỉnh thoảng vẫn cho sát nhau nếu hết chỗ
                indices_to_show.add(idx)
                
    # 2. Nếu thiếu thì thêm phụ âm
    consonant_indices = [i for i, c in enumerate(word) if c not in vowels]
    random.shuffle(consonant_indices)
    for idx in consonant_indices:
        if len(indices_to_show) < num_hints:
            indices_to_show.add(idx)
            
    hint_str = ""
    for i, c in enumerate(word):
        if i in indices_to_show or c in [' ', '-']:
            hint_str += c + " "
        else:
            hint_str += "_ "
            
    return hint_str.strip()

def get_random_distractors(target_word, target_key, count=3):
    words_db = st.session_state.db["words"]
    all_words = [w for w in words_db.values() if w["word"] != target_word]
    if len(all_words) < count:
        # Fallback cứng nếu chưa đủ từ trong DB
        fallbacks = [
            {"word": "confident", "vietnamese_meaning": "tự tin", "pronunciation": "/ˈkɒnfɪdənt/"},
            {"word": "generous", "vietnamese_meaning": "hào phóng", "pronunciation": "/ˈdʒɛnərəs/"},
            {"word": "curious", "vietnamese_meaning": "tò mò", "pronunciation": "/ˈkjʊəriəs/"},
            {"word": "stubborn", "vietnamese_meaning": "bướng bỉnh", "pronunciation": "/ˈstʌbən/"}
        ]
        return random.sample(fallbacks, count)
    return random.sample(all_words, count)

def create_question(word_data):
    """
    Tạo 1 trong 5 dạng câu hỏi ngẫu nhiên.
    Giảm khả năng lặp lại dạng cũ.
    """
    types = [1, 2, 3, 4, 5]
    last_type = word_data.get("last_question_type")
    
    if last_type in types:
        # Giảm trọng số của last_type
        weights = [10 if t != last_type else 2 for t in types]
        q_type = random.choices(types, weights=weights, k=1)[0]
    else:
        q_type = random.choice(types)
        
    word_data["last_question_type"] = q_type
    w_eng = word_data["word"]
    w_vi = word_data["vietnamese_meaning"]
    diff = word_data.get("difficulty", 50)
    
    q_data = {
        "type": q_type,
        "word_data": word_data,
        "target": w_eng
    }
    
    if q_type == 1 or q_type == 4:
        # 1: Điền từ, 4: Viết chính tả (giống 1 nhưng UI nhập text)
        ex = word_data["example_sentence"]
        # Hide the target word (case insensitive replace)
        pattern = re.compile(re.escape(w_eng), re.IGNORECASE)
        hint = generate_hint(w_eng, diff)
        blanked = pattern.sub("______", ex)
        if blanked == ex: # Fallback if lemma mismatch
            blanked = f"______ (Gợi ý: {w_vi})"
            
        q_data["question_text"] = blanked
        q_data["hint"] = hint
        
    elif q_type == 2:
        # 2: Chọn nghĩa tiếng Anh (MCQ)
        distractors = get_random_distractors(w_eng, "word", 3)
        options = [w_eng] + [d["word"] for d in distractors]
        random.shuffle(options)
        q_data["question_text"] = f"Nghĩa tiếng Việt: **{w_vi}**"
        q_data["options"] = options
        
    elif q_type == 3:
        # 3: Chọn tiếng Anh qua Audio
        distractors = get_random_distractors(w_eng, "word", 3)
        options = [w_eng] + [d["word"] for d in distractors]
        random.shuffle(options)
        q_data["question_text"] = f"Nghĩa tiếng Việt: **{w_vi}** (Nghe và chọn)"
        q_data["options"] = options
        
    elif q_type == 5:
        # 5: Chọn phiên âm
        distractors = get_random_distractors(w_eng, "pronunciation", 3)
        target_ipa = word_data.get("pronunciation", "/.../")
        options = [target_ipa] + [d.get("pronunciation", "/.../") for d in distractors]
        random.shuffle(options)
        q_data["question_text"] = f"Phiên âm của từ có nghĩa: **{w_vi}**"
        q_data["options"] = options
        q_data["target_option"] = target_ipa
        
    return q_data

# ==========================================
# 6. TAB 1: SCAN TỪ VỰNG
# ==========================================
def render_scan_tab():
    st.header("🔍 Quét Từ Vựng Mới")
    st.markdown("Dán đoạn văn bản tiếng Anh vào đây, AI sẽ quét và trích xuất những từ vựng đáng học nhất.")
    
    text_input = st.text_area("Văn bản tiếng Anh", height=200, placeholder="Paste your English text here...")
    
    if st.button("SCAN ALL", type="primary"):
        if not text_input.strip():
            st.warning("Vui lòng nhập văn bản!")
            return
            
        with st.spinner("AI đang phân tích và quét từ vựng..."):
            sys_prompt = """
            You are a senior English teacher. Extract useful vocabulary words/phrases from the given text.
            Ignore basic articles, simple prepositions, extremely common words, and punctuation.
            Output ONLY a JSON array of objects.
            Format:
            {
                "words": [
                    {
                        "word": "original word",
                        "lemma": "base form",
                        "vietnamese_meaning": "natural Vietnamese translation",
                        "english_definition": "simple English explanation",
                        "example_sentence": "Extremely simple example. MUST be 100% understandable for beginners.",
                        "topic": "General topic category",
                        "pronunciation": "IPA if possible",
                        "difficulty": a number between 10 (very easy) and 90 (hard) based on CEFR level
                    }
                ]
            }
            """
            
            result = call_ai(text_input, sys_prompt)
            
            if result and "words" in result:
                added_count = 0
                for w in result["words"]:
                    w_key = w["word"].strip().lower()
                    if w_key not in st.session_state.db["words"]:
                        w["status"] = "new"
                        w["correct_count"] = 0
                        w["wrong_count"] = 0
                        w["review_count"] = 0
                        w["next_review"] = datetime.now().isoformat()
                        w["streak"] = 0
                        st.session_state.db["words"][w_key] = w
                        added_count += 1
                        
                save_data()
                st.success(f"Đã thêm {added_count} từ mới vào Sổ tay! 🎉")
            else:
                st.error("AI không trả về đúng định dạng hoặc bị lỗi. Thử lại sau nhé 😅.")

# ==========================================
# 7. TAB 2: ÔN TẬP (CORE SYSTEM)
# ==========================================
def render_review_tab():
    st.header("🔥 Vòng Lặp Học Tập")
    
    check_daily_streak()
    
    # Hiển thị HUD
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("XP", st.session_state.db["stats"]["xp"])
    col2.metric("Level", st.session_state.db["stats"]["level"])
    col3.metric("Streak 🔥", f"{st.session_state.db['stats']['streak']} ngày")
    col4.metric("Từ Đã Thuộc", st.session_state.db["stats"]["total_mastered"])
    st.divider()

    state = st.session_state.review_state
    
    if state["phase"] == "idle":
        due_words, new_words = get_due_words()
        total_waiting = len(state["wrong_temp"]) + len(due_words) + len(new_words)
        
        if total_waiting == 0:
            st.markdown("<h2 style='text-align: center; color: #888;'>Chưa tới giờ ôn 😴</h2>", unsafe_allow_html=True)
            
            # Tìm thời gian ôn gần nhất
            next_times = [datetime.fromisoformat(w["next_review"]) for w in st.session_state.db["words"].values() if w.get("next_review")]
            if next_times:
                closest = min(next_times)
                now = datetime.now()
                if closest > now:
                    delta = closest - now
                    hours, remainder = divmod(delta.seconds, 3600)
                    minutes, seconds = divmod(remainder, 60)
                    time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                    st.markdown(f"<h1 style='text-align: center; font-size: 3rem;'>⏳ {time_str}</h1>", unsafe_allow_html=True)
                    time.sleep(1) # Hack nhỏ để UI reload từ từ, Streamlit-native cách duy nhất là st_autorefresh nhưng ko dùng lib ngoài
                    st.rerun()
            return
            
        st.info(f"Có **{total_waiting}** từ đang chờ bạn chinh phục!")
        if st.button("🚀 BẮT ĐẦU ÔN TẬP", use_container_width=True, type="primary"):
            state["session_words"] = build_session(6)
            state["current_index"] = 0
            state["phase"] = "question"
            state["session_score"] = 0
            state["correct_temp"] = []
            st.rerun()
            
    elif state["phase"] == "question":
        if state["current_index"] >= len(state["session_words"]):
            st.balloons()
            st.success(f"Hoàn thành session! Điểm Session: {state['session_score']} XP")
            if len(state["correct_temp"]) == len(state["session_words"]) and len(state["session_words"]) > 0:
                st.toast("PERFECT SESSION! +30 XP Bonus 🌟")
                add_xp(30)
                st.session_state.db["stats"]["perfect_sessions"] += 1
                save_data()
                
            state["phase"] = "idle"
            st.button("Về trang chính")
            return
            
        # Hiển thị Progress
        progress = state["current_index"] / len(state["session_words"])
        st.progress(progress, text=f"Từ {state['current_index'] + 1} / {len(state['session_words'])}")
        
        word_data = state["session_words"][state["current_index"]]
        
        if not state["current_question"]:
            state["current_question"] = create_question(word_data)
            
        q = state["current_question"]
        
        st.markdown(f"### Dịch/Ngữ cảnh: {q['question_text']}")
        
        if q["type"] == 1:
            st.markdown(f"**Gợi ý:** `{q['hint']}`")
            ans = st.text_input("Nhập từ tiếng Anh:", key="ans_type1").strip().lower()
            if st.button("NỘP BÀI"):
                state["last_user_answer"] = ans
                state["last_answer_correct"] = (ans == q["target"].lower())
                state["phase"] = "feedback"
                st.rerun()
                
        elif q["type"] == 2:
            cols = st.columns(2)
            for i, opt in enumerate(q["options"]):
                if cols[i%2].button(opt, key=f"opt2_{i}", use_container_width=True):
                    state["last_user_answer"] = opt
                    state["last_answer_correct"] = (opt == q["target"])
                    state["phase"] = "feedback"
                    st.rerun()
                    
        elif q["type"] == 3:
            st.write("Nghe và chọn từ đúng:")
            cols = st.columns(4)
            for i, opt in enumerate(q["options"]):
                with cols[i]:
                    if st.button(f"🔊 Option {i+1}", key=f"play3_{i}", use_container_width=True):
                        play_audio_en_only(opt)
                    if st.button(f"Chọn {i+1}", key=f"opt3_{i}", type="primary", use_container_width=True):
                        state["last_user_answer"] = opt
                        state["last_answer_correct"] = (opt == q["target"])
                        state["phase"] = "feedback"
                        st.rerun()
                        
        elif q["type"] == 4:
            st.markdown(f"**Gợi ý:** `{q['hint']}`")
            ans = st.text_input("Viết chính tả:", key="ans_type4").strip().lower()
            if st.button("NỘP BÀI"):
                state["last_user_answer"] = ans
                state["last_answer_correct"] = (ans == q["target"].lower())
                state["phase"] = "feedback"
                st.rerun()
                
        elif q["type"] == 5:
            cols = st.columns(2)
            for i, opt in enumerate(q["options"]):
                if cols[i%2].button(opt, key=f"opt5_{i}", use_container_width=True):
                    state["last_user_answer"] = opt
                    state["last_answer_correct"] = (opt == q["target_option"])
                    state["phase"] = "feedback"
                    st.rerun()

    elif state["phase"] == "feedback":
        word_data = state["session_words"][state["current_index"]]
        q = state["current_question"]
        
        # PLAY AUDIO NGAY LẬP TỨC
        play_audio(word_data["word"], word_data["vietnamese_meaning"])
        
        st.markdown(f"<h1 style='text-align:center; color:#2e86c1;'>{word_data['word']}</h1>", unsafe_allow_html=True)
        st.markdown(f"<h3 style='text-align:center; color:#888;'>{word_data['vietnamese_meaning']}</h3>", unsafe_allow_html=True)
        st.markdown(f"<p style='text-align:center; font-style:italic;'>Ví dụ: {word_data['example_sentence']}</p>", unsafe_allow_html=True)
        
        if state["last_answer_correct"]:
            st.success("✓ CHÍNH XÁC")
            if "xp_awarded" not in state:
                xp_gain = 10 + (15 if word_data.get("difficulty", 0) > 60 else 0)
                add_xp(xp_gain)
                state["session_score"] += xp_gain
                state["xp_awarded"] = True
        else:
            st.error("✗ SAI RỒI")
            st.markdown(f"**Đáp án đúng:** {q['target'] if q['type'] != 5 else q.get('target_option')}")
            if "xp_awarded" not in state:
                add_xp(2) # Sai vẫn được 2 XP động viên
                state["session_score"] += 2
                state["xp_awarded"] = True

        col1, col2, col3 = st.columns(3)
        
        def handle_next(result_type):
            # Tính toán difficulty & interval
            db_key = word_data["word"].lower()
            old_status = st.session_state.db["words"][db_key].get("status", "new")
            
            st.session_state.db["words"][db_key] = calculate_next_review(st.session_state.db["words"][db_key], result_type)
            new_status = st.session_state.db["words"][db_key]["status"]
            
            if old_status != "mastered" and new_status == "mastered":
                st.session_state.db["stats"]["total_mastered"] += 1
            elif old_status == "mastered" and new_status != "mastered":
                st.session_state.db["stats"]["total_mastered"] -= 1
                
            if result_type in ["wrong", "not_remember", "not_understand"]:
                state["wrong_temp"].append(st.session_state.db["words"][db_key])
            else:
                state["correct_temp"].append(st.session_state.db["words"][db_key])
                
            save_data()
            state["current_index"] += 1
            state["current_question"] = None
            if "xp_awarded" in state: del state["xp_awarded"]
            state["phase"] = "question"
        
        if col1.button("TIẾP TỤC", type="primary", use_container_width=True):
            res = "correct" if state["last_answer_correct"] else "wrong"
            handle_next(res)
            st.rerun()
            
        if col2.button("KHÔNG THUỘC 😕", use_container_width=True):
            handle_next("not_remember")
            st.rerun()
            
        if col3.button("KHÔNG HIỂU ❓", use_container_width=True):
            handle_next("not_understand")
            st.rerun()

# ==========================================
# 8. TAB 3: SỔ TAY (NOTEBOOK)
# ==========================================
def render_notebook_tab():
    st.header("📔 Sổ Tay Từ Vựng")
    
    db_words = st.session_state.db["words"]
    
    col1, col2 = st.columns([3, 1])
    search_q = col1.text_input("🔍 Tìm từ...", placeholder="Nhập từ, nghĩa tiếng Việt, hoặc topic")
    
    # Tự động gom Topic
    all_topics = set(w.get("topic", "General") for w in db_words.values())
    filter_topic = col2.selectbox("Topic", ["All"] + list(all_topics))
    
    if st.button("🤖 SỬA ALL BẰNG AI"):
        st.warning("Tính năng này sẽ gọi AI để chuẩn hóa dữ liệu. Tuân thủ yêu cầu: AI xử lý batch để tối ưu.")
        # Lấy tối đa 10 từ đang lỗi form hoặc rỗng để sửa batch
        words_to_fix = [w for w in db_words.values() if not w.get("topic") or len(w.get("example_sentence", "")) < 5][:10]
        if not words_to_fix:
            st.success("Tất cả từ vựng đều đã đầy đủ thông tin!")
        else:
            with st.spinner("AI đang sửa dữ liệu..."):
                words_list_str = json.dumps([{"word": w["word"]} for w in words_to_fix])
                sys_p = "Provide missing fields for these words: topic, simple example_sentence, pronunciation. Output strictly JSON array."
                res = call_ai(words_list_str, sys_p)
                if res and isinstance(res, list):
                    for r in res:
                        key = r.get("word", "").lower()
                        if key in db_words:
                            if "topic" in r: db_words[key]["topic"] = r["topic"]
                            if "example_sentence" in r: db_words[key]["example_sentence"] = r["example_sentence"]
                            if "pronunciation" in r: db_words[key]["pronunciation"] = r["pronunciation"]
                    save_data()
                    st.success("Cập nhật thành công!")
                    st.rerun()
    
    st.divider()
    
    filtered_words = []
    for w in db_words.values():
        match_search = search_q.lower() in w["word"].lower() or search_q.lower() in w["vietnamese_meaning"].lower() or search_q.lower() in w.get("topic","").lower()
        match_topic = (filter_topic == "All") or (w.get("topic") == filter_topic)
        if match_search and match_topic:
            filtered_words.append(w)
            
    st.write(f"Hiển thị **{len(filtered_words)}** từ.")
    
    for w in filtered_words:
        with st.expander(f"{w['word']} - {w['vietnamese_meaning']} [{w['status']}]"):
            c1, c2 = st.columns(2)
            c1.markdown(f"**Định nghĩa Anh:** {w.get('english_definition', '')}")
            c1.markdown(f"**Phiên âm:** {w.get('pronunciation', '')}")
            c1.markdown(f"**Ví dụ:** {w.get('example_sentence', '')}")
            c1.markdown(f"**Chủ đề:** {w.get('topic', '')}")
            
            c2.markdown(f"**Level / Diff:** {w.get('difficulty', 50)}")
            c2.markdown(f"**Ôn tập lần tới:** {w.get('next_review', 'N/A')[:16].replace('T', ' ')}")
            acc = 0
            total = w.get("correct_count",0) + w.get("wrong_count",0)
            if total > 0: acc = int((w.get("correct_count",0) / total) * 100)
            c2.markdown(f"**Độ chính xác:** {acc}%")
            
            # Tính năng SỬA
            if c2.button("Sửa thủ công", key=f"edit_{w['word']}"):
                st.session_state.edit_word = w["word"]
                
            if st.session_state.get("edit_word") == w["word"]:
                with st.form(key=f"form_{w['word']}"):
                    new_mean = st.text_input("Nghĩa VN", w['vietnamese_meaning'])
                    new_ex = st.text_input("Ví dụ", w['example_sentence'])
                    new_diff = st.number_input("Độ khó (0-100)", 0, 100, w.get('difficulty', 50))
                    if st.form_submit_button("Lưu"):
                        db_words[w['word'].lower()]["vietnamese_meaning"] = new_mean
                        db_words[w['word'].lower()]["example_sentence"] = new_ex
                        db_words[w['word'].lower()]["difficulty"] = new_diff
                        save_data()
                        st.session_state.edit_word = None
                        st.rerun()

# ==========================================
# 9. TAB 4: READING
# ==========================================
def render_reading_tab():
    st.header("📚 Reading & Comprehension")
    
    db_words = st.session_state.db["words"]
    topics = {}
    for w in db_words.values():
        t = w.get("topic", "General")
        if t not in topics: topics[t] = []
        topics[t].append(w)
        
    st.markdown("Hệ thống sẽ tự động mở khóa bài Reading khi một chủ đề có đủ **10 từ vựng**.")
    
    for t, words in topics.items():
        if len(words) >= 10:
            st.success(f"**{t}** — {len(words)} từ vựng. Đủ điều kiện tạo Reading!")
            if st.button(f"TẠO READING: {t}", key=f"gen_read_{t}"):
                with st.spinner("AI đang viết một đoạn reading xịn xò..."):
                    # Độ khó = min(difficulty)
                    min_diff = min([w.get("difficulty", 50) for w in words])
                    word_list_str = ", ".join([w["word"] for w in words[:15]]) # Max 15 từ
                    
                    sys_p = f"""
                    Write a SHORT, interesting reading passage (IELTS style but shorter).
                    Topic: {t}.
                    Target vocabulary to naturally include: {word_list_str}.
                    The reading difficulty MUST match the weakest word's level. Assume difficulty score {min_diff}/100.
                    Output JSON format:
                    {{
                        "topic": "{t}",
                        "difficulty": {min_diff},
                        "passage": "the text here...",
                        "target_words_used": ["word1", "word2"]
                    }}
                    """
                    res = call_ai("Generate reading passage", sys_p)
                    if res and "passage" in res:
                        st.session_state.db["readings"].append({
                            "topic": t,
                            "difficulty": min_diff,
                            "passage": res["passage"],
                            "words": res["target_words_used"],
                            "date": str(datetime.now().date()),
                            "score": None
                        })
                        save_data()
                        st.rerun()
        else:
            st.info(f"**{t}** — {len(words)}/10 từ. Hãy quét thêm từ vựng!")
            
    st.divider()
    st.subheader("Các bài Reading đang chờ")
    
    for i, r in enumerate(st.session_state.db["readings"]):
        if r.get("score") is None:
            with st.expander(f"📖 {r['topic']} (Độ khó: {r['difficulty']})"):
                st.markdown(r["passage"])
                
                user_trans = st.text_area("Dịch đoạn văn này sang tiếng Việt để AI chấm:", key=f"trans_{i}")
                if st.button("NỘP BÀI DỊCH", key=f"sub_{i}"):
                    with st.spinner("AI đang chấm điểm..."):
                        sys_p = """
                        You are a grader. Grade the user's Vietnamese translation of the English passage.
                        Return JSON:
                        {
                            "translation_accuracy": 0-100,
                            "comprehension": 0-100,
                            "meaning_accuracy": 0-100,
                            "feedback": "short helpful feedback in Vietnamese"
                        }
                        """
                        prompt = f"Original: {r['passage']}\nUser Translation: {user_trans}"
                        eval_res = call_ai(prompt, sys_p)
                        
                        if eval_res:
                            st.session_state.db["readings"][i]["score"] = eval_res
                            # Thưởng XP lớn
                            avg_score = (eval_res["translation_accuracy"] + eval_res["comprehension"] + eval_res["meaning_accuracy"]) / 3
                            add_xp(int(avg_score))
                            save_data()
                            st.rerun()
        else:
            with st.expander(f"✅ {r['topic']} - Đã hoàn thành ({r['date']})"):
                st.markdown(r["passage"])
                sc = r["score"]
                st.success(f"Translation Accuracy: {sc.get('translation_accuracy')}% | Comprehension: {sc.get('comprehension')}%")
                st.markdown(f"**Feedback:** {sc.get('feedback')}")

# ==========================================
# 10. MAIN APP SHELL
# ==========================================
def main():
    st.title("Vocab Master 🚀")
    
    tab1, tab2, tab3, tab4 = st.tabs(["🔍 SCAN", "🔥 ÔN TẬP", "📔 SỔ TAY", "📚 READING"])
    
    with tab1: render_scan_tab()
    with tab2: render_review_tab()
    with tab3: render_notebook_tab()
    with tab4: render_reading_tab()

if __name__ == "__main__":
    main()
