import streamlit as st
import json
import os
import random
import re
import time
from datetime import datetime, timedelta

# ==========================================
# CONFIG & CONSTANTS
# ==========================================
DATA_FILE = "vocab_data.json"
DEFAULT_MODEL = "minimax/minimax-m3:free"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

TYPE_FILL_BLANK = "FILL_IN_THE_BLANK"
TYPE_MEANING_MC = "MEANING_MULTIPLE_CHOICE"
TYPE_LISTENING_MC = "LISTENING_MULTIPLE_CHOICE"
TYPE_SPELLING = "SPELLING"
TYPE_PHONETIC_MC = "PHONETIC_MULTIPLE_CHOICE"

ALL_TOPICS = [
    "Daily life", "Work", "Technology", "Education", 
    "Environment", "Travel", "Business", "Health", "Science"
]

# ==========================================
# PAGE SETUP & CSS
# ==========================================
st.set_page_config(
    page_title="VocabLingo - Gamified Vocab",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling for Gamified UX
st.markdown("""
<style>
    .stApp {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 15px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        text-align: center;
        border: 1px solid #e9ecef;
    }
    .metric-val {
        font-size: 24px;
        font-weight: bold;
        color: #2b2d42;
    }
    .metric-lbl {
        font-size: 13px;
        color: #6c757d;
        text-transform: uppercase;
    }
    .success-box {
        background-color: #d4edda;
        color: #155724;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 10px;
        border-left: 5px solid #28a745;
    }
    .error-box {
        background-color: #f8d7da;
        color: #721c24;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 10px;
        border-left: 5px solid #dc3545;
    }
    .hint-text {
        font-family: monospace;
        font-size: 22px;
        letter-spacing: 4px;
        color: #0d6efd;
        background: #f1f3f5;
        padding: 6px 12px;
        border-radius: 6px;
    }
</style>
""", unsafe_allow_html=True)


# ==========================================
# PERSISTENCE & DATA MANAGEMENT
# ==========================================
def load_data():
    """Tải dữ liệu từ local file JSON. Nếu chưa có, tạo cấu trúc rỗng."""
    default_structure = {
        "vocabulary": [],
        "stats": {
            "xp": 0,
            "streak": 1,
            "last_active": datetime.now().strftime("%Y-%m-%d"),
            "total_reviews": 0,
            "correct_reviews": 0
        },
        "readings": []
    }
    if not os.path.exists(DATA_FILE):
        save_data(default_structure)
        return default_structure
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Ensure keys exist
            if "vocabulary" not in data: data["vocabulary"] = []
            if "stats" not in data: data["stats"] = default_structure["stats"]
            if "readings" not in data: data["readings"] = []
            return data
    except Exception as e:
        st.error(f"Error loading data file: {e}")
        return default_structure

def save_data(data):
    """Lưu dữ liệu ra local file JSON."""
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error(f"Error saving data file: {e}")

# ==========================================
# OPENROUTER AI HELPER
# ==========================================
def call_openrouter(prompt, system_prompt="You are a helpful language learning assistant. Response MUST be strict valid JSON only, without Markdown code blocks or extra explanations."):
    """Gọi OpenRouter API với retry và fallback xử lý JSON an toàn."""
    try:
        api_key = st.secrets["OPENROUTER_API_KEY"]
    except KeyError:
        st.error("⚠️ Missing OPENROUTER_API_KEY in Streamlit Secrets!")
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://streamlit.io",
        "X-Title": "VocabLingo App"
    }

    payload = {
        "model": DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.4
    }

    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=25)
            if response.status_code == 200:
                result = response.json()
                content = result["choices"][0]["message"]["content"].strip()
                
                # Cleanup potential Markdown block
                if content.startswith("```"):
                    content = re.sub(r"^```[a-zA-Z]*\n?", "", content)
                    content = re.sub(r"\n?```$", "", content)
                content = content.strip()
                
                return json.loads(content)
            else:
                st.warning(f"AI API returned status {response.status_code}. Retrying...")
        except (requests.RequestException, json.JSONDecodeError) as e:
            if attempt == max_retries:
                st.error(f"AI API Call failed after retries: {e}")
                return None
            time.sleep(1)
    return None

import requests # Import at top level needed

# ==========================================
# AUDIO PLAYER (BROWSER WEB SPEECH API)
# ==========================================
def play_audio(word):
    """Sử dụng HTML/JS Web Speech API để phát âm ngay trên trình duyệt."""
    clean_word = word.replace("'", "\\'").replace('"', '\\"')
    js_code = f"""
    <script>
        (function() {{
            if ('speechSynthesis' in window) {{
                window.speechSynthesis.cancel();
                var msg = new SpeechSynthesisUtterance('{clean_word}');
                msg.lang = 'en-US';
                msg.rate = 0.85;
                window.speechSynthesis.speak(msg);
            }}
        }})();
    </script>
    """
    st.components.v1.html(js_code, height=0, width=0)

# ==========================================
# ALGORITHM: HINT GENERATION (DẠNG 1 & 4)
# ==========================================
def calculate_hint(word, difficulty):
    """
    Tạo hint thông minh:
    1. Ưu tiên tiết lộ nguyên âm (a, e, i, o, u)
    2. Tiếp theo ưu tiên phụ âm gần nguyên âm
    3. Tránh reveal các chữ đứng sát nhau nếu có thể
    4. Difficulty càng cao (0-100) -> tiết lộ càng ít chữ
    """
    word_len = len(word)
    if word_len <= 2:
        return word[0] + "_" * (word_len - 1)

    # Xác định số lượng chữ cái được tiết lộ dựa trên difficulty
    if difficulty < 30:
        reveal_ratio = 0.6
    elif difficulty < 70:
        reveal_ratio = 0.4
    else:
        reveal_ratio = 0.25

    target_reveal_count = max(1, min(word_len - 1, int(word_len * reveal_ratio)))

    vowels = set("aeiouAEIOU")
    word_indices = list(range(word_len))
    
    # Phân loại chỉ số chữ cái
    vowel_indices = [i for i in word_indices if word[i] in vowels]
    
    # Phụ âm kề nguyên âm
    adj_consonant_indices = []
    for i in word_indices:
        if word[i] not in vowels:
            has_adj_vowel = (i > 0 and word[i-1] in vowels) or (i < word_len - 1 and word[i+1] in vowels)
            if has_adj_vowel:
                adj_consonant_indices.append(i)
                
    other_consonant_indices = [i for i in word_indices if i not in vowel_indices and i not in adj_consonant_indices]

    # Thứ tự ưu tiên
    random.shuffle(vowel_indices)
    random.shuffle(adj_consonant_indices)
    random.shuffle(other_consonant_indices)
    
    candidate_order = vowel_indices + adj_consonant_indices + other_consonant_indices
    
    # Lựa chọn chỉ số sao cho ít bị dính liền nhau nhất
    revealed_indices = []
    for idx in candidate_order:
        if len(revealed_indices) >= target_reveal_count:
            break
        # Ưu tiên không kề sát chữ đã chọn nếu còn khoảng trống
        if not any(abs(idx - r) == 1 for r in revealed_indices) or len(revealed_indices) < 1:
            revealed_indices.append(idx)
            
    # Nếu chưa đủ số lượng reveal target, chấp nhận chọn kề sát
    if len(revealed_indices) < target_reveal_count:
        for idx in candidate_order:
            if idx not in revealed_indices:
                revealed_indices.append(idx)
                if len(revealed_indices) >= target_reveal_count:
                    break

    # Dựng chuỗi hint
    hint_chars = []
    for i in range(word_len):
        if i in revealed_indices or word[i] in " -'":
            hint_chars.append(word[i])
        else:
            hint_chars.append("_")
            
    return " ".join(hint_chars)

# ==========================================
# ALGORITHM: SPACED REPETITION (SHORT INTERVAL)
# ==========================================
def calculate_next_review(word_item, is_correct):
    """
    Short Spaced Repetition Logic:
    - new -> 5-15 phút
    - correct lần lượt: 30m -> 2h -> 8h -> 1 ngày -> max 3-5 ngày
    - wrong -> 10-20 phút, max khoảng 1 ngày
    - Thay đổi difficulty: +5 nếu đúng, -8 nếu sai
    """
    now = datetime.now()
    rev_count = word_item.get("review_count", 0) + 1
    word_item["review_count"] = rev_count
    
    if is_correct:
        word_item["correct_count"] = word_item.get("correct_count", 0) + 1
        word_item["difficulty"] = min(100, word_item.get("difficulty", 20) + 5)
        
        # Interval ladder (minutes)
        if rev_count == 1:
            delta_min = 30
        elif rev_count == 2:
            delta_min = 120 # 2 hours
        elif rev_count == 3:
            delta_min = 480 # 8 hours
        elif rev_count == 4:
            delta_min = 1440 # 1 day
        else:
            delta_min = min(7200, 1440 * (1.5 ** (rev_count - 4))) # Max ~5 days
            
        if word_item.get("correct_count", 0) >= 4 and word_item.get("difficulty", 0) >= 50:
            word_item["status"] = "mastered"
        else:
            word_item["status"] = "learning"
    else:
        word_item["wrong_count"] = word_item.get("wrong_count", 0) + 1
        word_item["difficulty"] = max(0, word_item.get("difficulty", 20) - 8)
        word_item["status"] = "learning"
        # Reset interval về ngắn khi trả lời sai
        delta_min = random.randint(10, 20)

    next_time = now + timedelta(minutes=delta_min)
    word_item["last_review"] = now.strftime("%Y-%m-%d %H:%M")
    word_item["next_review"] = next_time.strftime("%Y-%m-%d %H:%M")
    return word_item

# ==========================================
# REVIEW SESSION GENERATOR
# ==========================================
def select_review_words(all_vocab, max_words=6):
    """Lựa chọn tối đa 6 từ ưu tiên theo thứ tự: 1. Sai trước đó, 2. new, 3. Đã đến hạn"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    due_wrong = []
    due_words = []
    new_words = []
    others = []
    
    for v in all_vocab:
        next_rev = v.get("next_review", "")
        if v.get("status") == "new":
            new_words.append(v)
        elif next_rev and next_rev <= now_str:
            if v.get("wrong_count", 0) > v.get("correct_count", 0):
                due_wrong.append(v)
            else:
                due_words.append(v)
        else:
            others.append(v)
            
    random.shuffle(due_wrong)
    random.shuffle(due_words)
    random.shuffle(new_words)
    random.shuffle(others)
    
    selected = (due_wrong + due_words + new_words + others)[:max_words]
    return selected

# ==========================================
# QUESTION BUILDERS WITH AI / FALLBACK
# ==========================================
def generate_question_data(word_item, all_vocab):
    """Tạo dữ liệu câu hỏi ngẫu nhiên 1 trong 5 dạng."""
    q_type = random.choice([
        TYPE_FILL_BLANK,
        TYPE_MEANING_MC,
        TYPE_LISTENING_MC,
        TYPE_SPELLING,
        TYPE_PHONETIC_MC
    ])
    
    target_word = word_item["word"]
    meaning = word_item["meaning_vi"]
    diff = word_item.get("difficulty", 20)
    
    # Chuẩn bị Distractors từ vocab hiện có hoặc fallback
    other_words = [v["word"] for v in all_vocab if v["word"].lower() != target_word.lower()]
    random.shuffle(other_words)
    
    distractors_en = other_words[:3]
    while len(distractors_en) < 3:
        distractors_en.append(random.choice(["confident", "generous", "curious", "relevant", "remarkable", "subsequent"]))
        
    other_phonetics = [v["phonetic"] for v in all_vocab if v.get("phonetic") and v["word"].lower() != target_word.lower()]
    random.shuffle(other_phonetics)
    distractors_ipa = other_phonetics[:3]
    while len(distractors_ipa) < 3:
        distractors_ipa.append(random.choice(["/ˈrelevənt/", "/rɪˈzɪstənt/", "/ˈriːmɑːrkəbəl/", "/kənˈsɪdərət/"]))

    # Yêu cầu AI tạo câu ví dụ mới phù hợp với difficulty
    prompt = f"""
    Create a sentence in simple English for the word '{target_word}' (meaning: {meaning}).
    Target Difficulty Level (0-100): {diff}.
    Constraint: If difficulty is low (<40), use extremely simple grammar and obvious context.
    Do NOT make complex sentences.
    Return JSON format:
    {{
        "sentence": "Sentence with the word {target_word} included",
        "blank_sentence": "Sentence with '______' replacing {target_word}"
    }}
    """
    
    ai_res = call_openrouter(prompt)
    if ai_res and "sentence" in ai_res and "blank_sentence" in ai_res:
        sentence = ai_res["sentence"]
        blank_sentence = ai_res["blank_sentence"]
    else:
        # Fallback if AI fails
        sentence = word_item.get("example") or f"She was very {target_word} about the decision."
        blank_sentence = sentence.replace(target_word, "______").replace(target_word.capitalize(), "______")

    hint = calculate_hint(target_word, diff)
    
    # Chuẩn bị lựa chọn trắc nghiệm
    mc_options = distractors_en + [target_word]
    random.shuffle(mc_options)
    
    ipa_options = distractors_ipa + [word_item.get("phonetic", "/.../")]
    random.shuffle(ipa_options)

    return {
        "word_item": word_item,
        "q_type": q_type,
        "target_word": target_word,
        "meaning": meaning,
        "sentence": sentence,
        "blank_sentence": blank_sentence,
        "hint": hint,
        "mc_options": mc_options,
        "ipa_options": ipa_options
    }

# ==========================================
# MAIN APP FLOW
# ==========================================
def main():
    data = load_data()
    
    # Initialize Session State Variables
    if "session_active" not in st.session_state:
        st.session_state.session_active = False
    if "review_queue" not in st.session_state:
        st.session_state.review_queue = []
    if "current_index" not in st.session_state:
        st.session_state.current_index = 0
    if "current_q_data" not in st.session_state:
        st.session_state.current_q_data = None
    if "answered" not in st.session_state:
        st.session_state.answered = False
    if "last_is_correct" not in st.session_state:
        st.session_state.last_is_correct = False
    if "session_correct_list" not in st.session_state:
        st.session_state.session_correct_list = []
    if "session_wrong_list" not in st.session_state:
        st.session_state.session_wrong_list = []
    if "session_xp_gained" not in st.session_state:
        st.session_state.session_xp_gained = 0
    if "combo_count" not in st.session_state:
        st.session_state.combo_count = 0

    # Sidebar Header & Gamification Stats
    st.sidebar.title("⚡ VocabLingo")
    st.sidebar.caption("Short-Spaced Repetition & Gamified Learning")
    
    stats = data["stats"]
    st.sidebar.markdown(f"""
    <div style="background-color:#f0f2f6; padding:12px; border-radius:10px; margin-bottom:15px;">
        🔥 <b>Streak:</b> {stats.get('streak', 1)} ngày<br>
        ⭐ <b>XP:</b> {stats.get('xp', 0)}<br>
        📚 <b>Tổng từ:</b> {len(data['vocabulary'])} từ
    </div>
    """, unsafe_allow_html=True)

    # Top Tabs
    tab1, tab2, tab3 = st.tabs(["📥 TAB 1 — SCAN / ADD", "🎮 TAB 2 — REVIEW", "📖 TAB 3 — NOTEBOOK & READING"])

    # ==========================================
    # TAB 1: SCAN TEXT
    # ==========================================
    with tab1:
        st.header("Scan Text to Extract Vocabulary")
        st.write("Dán một đoạn văn tiếng Anh bên dưới. AI sẽ tự động phân tích, loại bỏ từ đã học và trích xuất các từ mới đáng học.")
        
        sample_input = st.text_area("Nhập đoạn văn tiếng Anh:", height=120, placeholder="I was reluctant to accept the offer because the circumstances were rather complicated.")
        
        if st.button("🔍 SCAN TEXT", type="primary"):
            if not sample_input.strip():
                st.warning("Vui lòng nhập văn bản trước khi scan!")
            else:
                with st.spinner("AI đang phân tích văn bản và lọc từ vựng..."):
                    existing_words = [v["word"].lower() for v in data["vocabulary"]]
                    
                    prompt = f"""
                    Analyze this text and extract useful English vocabulary/phrases to learn:
                    "{sample_input}"
                    
                    Rules:
                    1. Skip basic words (e.g. 'is', 'the', 'because', 'accept', 'offer') unless they have high learning value.
                    2. Exclude these existing words completely: {existing_words}.
                    3. Provide Vietnamese meaning, part of speech, IPA phonetic, single main topic from {ALL_TOPICS}, and a short simple example.
                    
                    Return STRICT JSON array of objects:
                    [
                      {{
                        "word": "reluctant",
                        "meaning_vi": "miễn cưỡng, ngần ngại",
                        "part_of_speech": "adjective",
                        "phonetic": "/rɪˈlʌktənt/",
                        "example": "She was reluctant to leave the house in heavy rain.",
                        "topic": "Daily life"
                      }}
                    ]
                    """
                    
                    res = call_openrouter(prompt)
                    if res and isinstance(res, list):
                        added_count = 0
                        for item in res:
                            w = item.get("word", "").strip()
                            if w and w.lower() not in existing_words:
                                new_vocab = {
                                    "id": str(int(time.time() * 1000)) + str(random.randint(100, 999)),
                                    "word": w,
                                    "meaning_vi": item.get("meaning_vi", ""),
                                    "part_of_speech": item.get("part_of_speech", ""),
                                    "phonetic": item.get("phonetic", "/.../"),
                                    "example": item.get("example", ""),
                                    "topic": item.get("topic", "Daily life"),
                                    "difficulty": 20, # Default initial easy difficulty
                                    "status": "new",
                                    "created_at": datetime.now().strftime("%Y-%m-%d"),
                                    "last_review": None,
                                    "next_review": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                    "review_count": 0,
                                    "correct_count": 0,
                                    "wrong_count": 0
                                }
                                data["vocabulary"].append(new_vocab)
                                existing_words.append(w.lower())
                                added_count += 1
                        
                        save_data(data)
                        if added_count > 0:
                            st.success(f"🎉 Đã thêm thành công {added_count} từ mới vào Vocabulary Notebook!")
                        else:
                            st.info("Không tìm thấy từ mới phù hợp hoặc tất cả từ đã có trong bộ sưu tập.")
                    else:
                        st.error("Không thể phân tích đoạn văn hoặc AI trả về sai định dạng. Vui lòng thử lại!")

    # ==========================================
    # TAB 2: REVIEW (GAMIFIED SESSION)
    # ==========================================
    with tab2:
        # Dashboard Overview
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        acc_rate = int((stats.get('correct_reviews', 0) / max(1, stats.get('total_reviews', 0))) * 100)
        
        with col_m1: st.markdown(f"<div class='metric-card'><div class='metric-val'>🔥 {stats.get('streak', 1)}</div><div class='metric-lbl'>Streak Days</div></div>", unsafe_allow_html=True)
        with col_m2: st.markdown(f"<div class='metric-card'><div class='metric-val'>⭐ {stats.get('xp', 0)}</div><div class='metric-lbl'>Total XP</div></div>", unsafe_allow_html=True)
        with col_m3: st.markdown(f"<div class='metric-card'><div class='metric-val'>📚 {len(data['vocabulary'])}</div><div class='metric-lbl'>Words Learned</div></div>", unsafe_allow_html=True)
        with col_m4: st.markdown(f"<div class='metric-card'><div class='metric-val'>🎯 {acc_rate}%</div><div class='metric-lbl'>Accuracy</div></div>", unsafe_allow_html=True)

        st.divider()

        # START SESSION BUTTON
        if not st.session_state.session_active:
            st.subheader("Ready for a quick 6-word session?")
            st.write("Mỗi lượt ôn tập chỉ gồm 5-6 từ, phản hồi lập tức, giúp tạo đà học tập mà không gây ngợp.")
            
            if st.button("🚀 START REVIEW (6 WORDS)", type="primary", use_container_width=True):
                review_list = select_review_words(data["vocabulary"], max_words=6)
                if not review_list:
                    st.info("🎉 Tất cả các từ đều đã ôn xong! Hãy dán thêm đoạn văn ở TAB 1 để nạp từ mới.")
                else:
                    st.session_state.session_active = True
                    st.session_state.review_queue = review_list
                    st.session_state.current_index = 0
                    st.session_state.answered = False
                    st.session_state.session_correct_list = []
                    st.session_state.session_wrong_list = []
                    st.session_state.session_xp_gained = 0
                    st.session_state.combo_count = 0
                    st.session_state.current_q_data = generate_question_data(review_list[0], data["vocabulary"])
                    st.rerun()

        else:
            # ACTIVE SESSION FLOW
            queue = st.session_state.review_queue
            idx = st.session_state.current_index
            total_q = len(queue)

            if idx >= total_q:
                # SESSION COMPLETE SUMMARY
                st.balloons()
                st.markdown(f"""
                <div class='success-box' style='text-align:center;'>
                    <h2>🎉 Session Complete!</h2>
                    <p style='font-size: 18px;'>Bạn vừa hoàn thành lượt ôn tập <b>{total_q} từ</b>!</p>
                </div>
                """, unsafe_allow_html=True)
                
                c_len = len(st.session_state.session_correct_list)
                w_len = len(st.session_state.session_wrong_list)
                acc = int((c_len / max(1, total_q)) * 100)
                
                col_r1, col_r2, col_r3 = st.columns(3)
                col_r1.metric("Đúng", f"{c_len} từ")
                col_r2.metric("Chưa nhớ", f"{w_len} từ")
                col_r3.metric("XP Nhận được", f"+{st.session_state.session_xp_gained} XP")

                # Cập nhật global stats
                stats["xp"] += st.session_state.session_xp_gained
                stats["total_reviews"] += total_q
                stats["correct_reviews"] += c_len
                save_data(data)

                if st.button("Trở về Dashboard", type="primary"):
                    st.session_state.session_active = False
                    st.rerun()

            else:
                # RENDERING INDIVIDUAL QUESTION
                q_data = st.session_state.current_q_data
                w_item = q_data["word_item"]

                # Progress Bar & Combo
                st.progress((idx) / total_q, text=f"Câu hỏi {idx + 1} / {total_q}")
                if st.session_state.combo_count > 1:
                    st.caption(f"🔥 Combo Streak: x{st.session_state.combo_count} (+XP Multiplier!)")

                q_type = q_data["q_type"]

                # --- RENDER QUESTION TYPES ---
                st.markdown(f"### Dạng bài: {q_type.replace('_', ' ')}")

                user_answer = None

                if q_type == TYPE_FILL_BLANK:
                    st.write(f"Điền từ thích hợp vào chỗ trống:")
                    st.markdown(f"#### *\"{q_data['blank_sentence']}\"*")
                    st.caption(f"Nghĩa: {q_data['meaning']}")
                    st.markdown(f"Hint: <span class='hint-text'>{q_data['hint']}</span>", unsafe_allow_html=True)
                    user_answer = st.text_input("Nhập từ tiếng Anh:", key=f"ans_{idx}").strip()

                elif q_type == TYPE_MEANING_MC:
                    st.write(f"Chọn từ tiếng Anh phù hợp với nghĩa:")
                    st.markdown(f"### 🇻🇳 **\"{q_data['meaning']}\"**")
                    user_answer = st.radio("Các lựa chọn:", q_data["mc_options"], key=f"ans_{idx}")

                elif q_type == TYPE_LISTENING_MC:
                    st.write(f"Nghe và chọn từ đúng cho nghĩa:")
                    st.markdown(f"### 🇻🇳 **\"{q_data['meaning']}\"**")
                    if st.button("🔊 Phát âm từ target", key=f"listen_btn_{idx}"):
                        play_audio(q_data["target_word"])
                    user_answer = st.radio("Các lựa chọn:", q_data["mc_options"], key=f"ans_{idx}")

                elif q_type == TYPE_SPELLING:
                    st.write(f"Viết lại chính xác từ tiếng Anh cho ngữ cảnh:")
                    st.caption(f"Nghĩa: {q_data['meaning']}")
                    st.markdown(f"Hint: <span class='hint-text'>{q_data['hint']}</span>", unsafe_allow_html=True)
                    user_answer = st.text_input("Nhập chính xác spelling:", key=f"ans_{idx}").strip()

                elif q_type == TYPE_PHONETIC_MC:
                    st.write(f"Chọn IPA Phiên âm đúng cho từ có nghĩa:")
                    st.markdown(f"### 🇻🇳 **\"{q_data['meaning']}\"** ({q_data['target_word']})")
                    user_answer = st.radio("Các phiên âm IPA:", q_data["ipa_options"], key=f"ans_{idx}")

                # --- SUBMISSION LOGIC ---
                if not st.session_state.answered:
                    if st.button("SUBMIT ANSWER", type="primary"):
                        if not user_answer:
                            st.warning("Vui lòng chọn hoặc nhập đáp án!")
                        else:
                            st.session_state.answered = True
                            target = q_data["target_word"].lower()
                            
                            # Check Correctness
                            if q_type == TYPE_PHONETIC_MC:
                                is_correct = (user_answer == w_item.get("phonetic"))
                            else:
                                is_correct = (user_answer.lower() == target)

                            st.session_state.last_is_correct = is_correct

                            # Apply Spaced Repetition Logic & Update Word Data
                            updated_w = calculate_next_review(w_item, is_correct)
                            # Sync back to master vocabulary list
                            for i, v in enumerate(data["vocabulary"]):
                                if v["id"] == updated_w["id"]:
                                    data["vocabulary"][i] = updated_w
                                    break
                            save_data(data)

                            if is_correct:
                                st.session_state.combo_count += 1
                                xp_gain = 10 * min(3, st.session_state.combo_count)
                                st.session_state.session_xp_gained += xp_gain
                                st.session_state.session_correct_list.append(target)
                            else:
                                st.session_state.combo_count = 0
                                st.session_state.session_wrong_list.append(target)

                            st.rerun()

                else:
                    # FEEDBACK DISPLAY AFTER SUBMISSION
                    is_corr = st.session_state.last_is_correct
                    
                    # MANDATORY SPEECH AUDIO PLAYBACK AFTER EACH ANSWER (RIGHT OR WRONG)
                    play_audio(q_data["target_word"])

                    if is_corr:
                        st.markdown(f"""
                        <div class='success-box'>
                            ✅ <b>CHÍNH XÁC!</b> +10 XP <br>
                            Từ: <b>{q_data['target_word']}</b> ({w_item.get('phonetic', '')}) — {q_data['meaning']}
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.markdown(f"""
                        <div class='error-box'>
                            ❌ <b>CHƯA CHÍNH XÁC!</b><br>
                            Đáp án đúng: <b>{q_data['target_word']}</b> ({w_item.get('phonetic', '')})<br>
                            Nghĩa: {q_data['meaning']}<br>
                            <i>Ví dụ: {q_data['sentence']}</i>
                        </div>
                        """, unsafe_allow_html=True)

                    # NEXT QUESTION BUTTON
                    if st.button("NEXT QUESTION ➡️", type="primary"):
                        st.session_state.current_index += 1
                        st.session_state.answered = False
                        
                        # Generate Next Question Data if not at end
                        if st.session_state.current_index < total_q:
                            next_item = queue[st.session_state.current_index]
                            st.session_state.current_q_data = generate_question_data(next_item, data["vocabulary"])
                        st.rerun()

    # ==========================================
    # TAB 3: VOCABULARY NOTEBOOK & READING GENERATION
    # ==========================================
    with tab3:
        st.header("Vocabulary Notebook & Adaptive Reading")
        
        sub_tab_notebook, sub_tab_reading = st.tabs(["📚 Notebook List", "📖 Adaptive Reading Test"])

        # SUB-TAB 1: NOTEBOOK LIST
        with sub_tab_notebook:
            col_s1, col_s2 = st.columns([2, 1])
            search_query = col_s1.text_input("🔍 Tìm kiếm từ vựng:", "")
            filter_status = col_s2.selectbox("Filter Status:", ["All", "new", "learning", "mastered"])

            filtered_vocab = data["vocabulary"]
            if search_query:
                filtered_vocab = [v for v in filtered_vocab if search_query.lower() in v["word"].lower() or search_query.lower() in v["meaning_vi"].lower()]
            if filter_status != "All":
                filtered_vocab = [v for v in filtered_vocab if v.get("status") == filter_status]

            st.write(f"Hiển thị {len(filtered_vocab)} từ vựng:")

            for v in filtered_vocab:
                with st.expander(f"**{v['word']}** ({v.get('part_of_speech', 'n/a')}) — {v['meaning_vi']}"):
                    c1, c2 = st.columns(2)
                    c1.write(f"🔊 **IPA:** {v.get('phonetic', '/.../')}")
                    c1.write(f"🏷️ **Topic:** {v.get('topic', 'General')}")
                    c1.write(f"📈 **Difficulty:** {v.get('difficulty', 20)}/100")
                    c2.write(f"🔄 **Reviews:** {v.get('review_count', 0)} (Đúng: {v.get('correct_count', 0)} | Sai: {v.get('wrong_count', 0)})")
                    c2.write(f"⏳ **Next Review:** {v.get('next_review', 'N/A')}")
                    c2.write(f"📌 **Status:** {v.get('status', 'new')}")
                    st.caption(f"Ví dụ: {v.get('example', 'N/A')}")

        # SUB-TAB 2: READING GENERATION & TRANSLATION
        with sub_tab_reading:
            st.subheader("IELTS-Style Reading Challenge")
            st.write("Tự động gom các từ trong cùng Topic để tạo bài đọc ngắn. Độ khó được căn chỉnh theo từ dễ nhất nhóm.")

            selected_topic = st.selectbox("Chọn Topic để làm Reading:", ALL_TOPICS)
            topic_words = [v for v in data["vocabulary"] if v.get("topic") == selected_topic]

            if len(topic_words) < 3:
                st.info(f"Cần ít nhất 3 từ thuộc Topic '{selected_topic}' để tạo bài đọc. Hiện có: {len(topic_words)} từ.")
            else:
                lowest_diff = min([v.get("difficulty", 20) for v in topic_words])
                words_str = ", ".join([v["word"] for v in topic_words])

                if st.button("📖 GENERATE READING PASSAGE", type="primary"):
                    with st.spinner("AI đang tạo bài đọc thích ứng..."):
                        prompt = f"""
                        Create a short reading passage (100-200 words) in English about topic '{selected_topic}'.
                        Target Difficulty Level: {lowest_diff} (Keep it simple if difficulty is low).
                        Must naturally incorporate some of these vocabulary words: {words_str}.
                        
                        Return JSON:
                        {{
                            "title": "Title of passage",
                            "passage": "Full English passage text...",
                            "vocab_used": ["word1", "word2"]
                        }}
                        """
                        res = call_openrouter(prompt)
                        if res and "passage" in res:
                            st.session_state.current_reading = res
                        else:
                            st.error("Không thể tạo bài đọc lúc này. Vui lòng thử lại!")

                if "current_reading" in st.session_state:
                    rd = st.session_state.current_reading
                    st.markdown(f"### {rd.get('title', 'Reading Passage')}")
                    st.info(rd.get("passage"))
                    st.caption(f"Từ vựng sử dụng: {', '.join(rd.get('vocab_used', []))}")

                    user_trans = st.text_area("Nhập bản dịch tiếng Việt của bạn:", height=120)
                    if st.button("CHẤM BẢN DỊCH", type="primary"):
                        if not user_trans.strip():
                            st.warning("Vui lòng nhập bản dịch!")
                        else:
                            with st.spinner("AI đang đánh giá bản dịch..."):
                                grade_prompt = f"""
                                Grade this Vietnamese translation of the English passage.
                                English: "{rd.get('passage')}"
                                User Translation: "{user_trans}"
                                
                                Return JSON:
                                {{
                                    "semantic_accuracy": 85,
                                    "comprehension": 90,
                                    "feedback": "Short constructive feedback in Vietnamese..."
                                }}
                                """
                                g_res = call_openrouter(grade_prompt)
                                if g_res:
                                    st.success(f"🎯 Accuracy: {g_res.get('semantic_accuracy', 0)}% | Comprehension: {g_res.get('comprehension', 0)}%")
                                    st.write(f"**Feedback AI:** {g_res.get('feedback', '')}")
                                else:
                                    st.error("Lỗi khi chấm bài dịch.")

if __name__ == "__main__":
    main()
