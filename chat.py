import streamlit as st
import json
import os
import random
import re
import time
from datetime import datetime, timedelta

# ==============================================================================
# CONFIG & CONSTANTS
# ==============================================================================
st.set_page_config(
    page_title="LingoPulse - Spaced Repetition Vocabulary",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

DEFAULT_MODEL = "minimax/minimax-m3:free"
DATA_FILE = "vocab_data.json"
MAX_SESSION_WORDS = 6

TYPE_FILL_BLANK = "fill_blank"
TYPE_CHOICE_ENG = "choice_eng"
TYPE_LISTENING = "listening"
TYPE_SPELLING = "spelling"
TYPE_PHONETIC = "phonetic"

ALL_TYPES = [
    TYPE_FILL_BLANK,
    TYPE_CHOICE_ENG,
    TYPE_LISTENING,
    TYPE_SPELLING,
    TYPE_PHONETIC
]

# ==============================================================================
# DATA PERSISTENCE
# ==============================================================================
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "vocabulary": [],
        "stats": {
            "xp": 0,
            "streak": 0,
            "last_active": None,
            "total_reviews": 0,
            "correct_reviews": 0
        },
        "readings": []
    }

def save_data(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error(f"Lỗi lưu dữ liệu: {e}")

# ==============================================================================
# OPENROUTER AI HELPER
# ==============================================================================
def call_openrouter(prompt, system_prompt="You are a helpful linguistic assistant."):
    api_key = st.secrets.get("OPENROUTER_API_KEY", None)
    if not api_key:
        st.error("Chưa cấu hình OPENROUTER_API_KEY trong Streamlit Secrets!")
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://streamlit.io",
        "X-Title": "LingoPulse"
    }

    payload = {
        "model": DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 1500
    }

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=25
        )
        if response.status_code == 200:
            res_json = response.json()
            content = res_json['choices'][0]['message']['content'].strip()
            # Clean JSON markdown if present
            if content.startswith("```"):
                content = re.sub(r"^```[a-zA-Z]*\n?", "", content)
                content = re.sub(r"\n?```$", "", content)
            return content.strip()
        else:
            st.error(f"Lỗi API ({response.status_code}): {response.text}")
            return None
    except Exception as e:
        st.error(f"Kết nối AI thất bại: {e}")
        return None

# ==============================================================================
# ALGORITHMS & LOGIC
# ==============================================================================
def calculate_hint(word, difficulty):
    """
    Thuật toán hint thông minh:
    1. Ưu tiên nguyên âm.
    2. Nếu đã hết nguyên âm mới reveal phụ âm.
    3. difficulty càng cao (0-100) -> tỉ lệ chữ reveal càng ít.
    4. Tránh reveal các chữ đứng sát nhau nếu có thể.
    """
    word_len = len(word)
    if word_len <= 3:
        return word[0] + "_" * (word_len - 1)

    # Xác định số ký tự reveal dựa trên difficulty
    # Diff = 0  -> reveal ~ 50-60%
    # Diff = 100 -> reveal ~ 20-30%
    ratio = max(0.2, 0.6 - (difficulty / 200.0))
    target_count = max(1, min(word_len - 1, int(word_len * ratio)))

    vowels = set("aeiouAEIOU")
    vowel_indices = [i for i, ch in enumerate(word) if ch in vowels and ch.isalpha()]
    consonant_indices = [i for i, ch in enumerate(word) if ch not in vowels and ch.isalpha()]

    random.shuffle(vowel_indices)
    random.shuffle(consonant_indices)

    selected_indices = set()
    
    # 1. Chọn nguyên âm trước
    while len(selected_indices) < target_count and vowel_indices:
        selected_indices.add(vowel_indices.pop())

    # 2. Nếu thiếu, chọn phụ âm
    while len(selected_indices) < target_count and consonant_indices:
        selected_indices.add(consonant_indices.pop())

    # Form hint string
    hint_chars = []
    for i, ch in enumerate(word):
        if not ch.isalpha():
            hint_chars.append(ch)
        elif i in selected_indices:
            hint_chars.append(ch)
        else:
            hint_chars.append("_")
            
    return " ".join(hint_chars)

def calculate_next_review(word_item, is_correct):
    now = datetime.now()
    review_count = word_item.get("review_count", 0) + 1
    word_item["review_count"] = review_count

    if is_correct:
        word_item["correct_count"] = word_item.get("correct_count", 0) + 1
        word_item["difficulty"] = min(100, word_item.get("difficulty", 20) + 5)
        
        # Short spaced repetition interval (Minutes)
        if review_count == 1:
            interval = 45 # 45 mins
        elif review_count == 2:
            interval = 240 # 4 hours
        elif review_count == 3:
            interval = 720 # 12 hours
        elif review_count == 4:
            interval = 1440 # 1 day
        else:
            interval = min(5760, 1440 * (1.5 ** (review_count - 4))) # Max ~4 days
    else:
        word_item["wrong_count"] = word_item.get("wrong_count", 0) + 1
        word_item["difficulty"] = max(0, word_item.get("difficulty", 20) - 8)
        interval = 15 # 15 phút ôn lại nếu sai

    word_item["last_review"] = now.isoformat()
    next_time = now + timedelta(minutes=interval)
    word_item["next_review"] = next_time.isoformat()
    
    # Mastered status check
    if word_item["correct_count"] >= 5 and (word_item["correct_count"] / max(1, word_item["review_count"])) >= 0.8:
        word_item["status"] = "mastered"
    else:
        word_item["status"] = "learning"

    return word_item

def select_review_words(vocabulary):
    if not vocabulary:
        return []

    now_str = datetime.now().isoformat()

    # Phân loại từ
    due_wrong = [
        w for w in vocabulary 
        if w.get("status") == "learning" and w.get("wrong_count", 0) > 0 and w.get("next_review", "") <= now_str
    ]
    due_normal = [
        w for w in vocabulary 
        if w.get("next_review", "") <= now_str and w not in due_wrong
    ]
    new_words = [
        w for w in vocabulary 
        if w.get("status") == "new" or w.get("review_count", 0) == 0
    ]
    other_words = [
        w for w in vocabulary 
        if w not in due_wrong and w not in due_normal and w not in new_words
    ]

    selected = []
    
    # Ưu tiên 1: Wrong words đã đến hạn
    random.shuffle(due_wrong)
    selected.extend(due_wrong[:MAX_SESSION_WORDS])

    # Ưu tiên 2: New words
    if len(selected) < MAX_SESSION_WORDS:
        random.shuffle(new_words)
        needed = MAX_SESSION_WORDS - len(selected)
        selected.extend(new_words[:needed])

    # Ưu tiên 3: Due normal
    if len(selected) < MAX_SESSION_WORDS:
        random.shuffle(due_normal)
        needed = MAX_SESSION_WORDS - len(selected)
        selected.extend(due_normal[:needed])

    # Fallback: Các từ khác sắp đến hạn
    if len(selected) < MAX_SESSION_WORDS:
        other_words.sort(key=lambda x: x.get("next_review", ""))
        needed = MAX_SESSION_WORDS - len(selected)
        selected.extend(other_words[:needed])

    return selected[:MAX_SESSION_WORDS]

# ==============================================================================
# AUDIO & SPEECH HELPER
# ==============================================================================
def play_audio_script(text):
    """Sử dụng Web Speech API native trong trình duyệt để phát âm."""
    clean_text = text.replace("'", "\\'").replace('"', '\\"')
    js_code = f"""
        <script>
            if ('speechSynthesis' in window) {{
                window.speechSynthesis.cancel();
                var msg = new SpeechSynthesisUtterance('{clean_text}');
                msg.lang = 'en-US';
                msg.rate = 0.85;
                window.speechSynthesis.speak(msg);
            }}
        </script>
    """
    st.components.v1.html(js_code, height=0, width=0)

# ==============================================================================
# QUESTION GENERATOR
# ==============================================================================
def generate_question_data(word_item, q_type, all_vocab):
    """
    Tạo dữ liệu câu hỏi dựa vào dạng và AI (nếu cần context)
    """
    word = word_item["word"]
    meaning = word_item["meaning_vi"]
    difficulty = word_item.get("difficulty", 20)

    # Lấy distractors từ db hoặc mặc định
    other_words = [w for w in all_vocab if w["word"].lower() != word.lower()]
    random.shuffle(other_words)

    distractor_words = [w["word"] for w in other_words[:3]]
    while len(distractor_words) < 3:
        fallback = random.choice(["confident", "reluctant", "generous", "curious", "vulnerable", "essential"])
        if fallback != word and fallback not in distractor_words:
            distractor_words.append(fallback)

    distractor_phonetics = [w.get("phonetic", "/.../") for w in other_words[:3]]
    while len(distractor_phonetics) < 3:
        distractor_phonetics.append("/ˈsæm.pəl/")

    if q_type == TYPE_FILL_BLANK:
        # Gọi AI tạo câu ví dụ khớp difficulty
        prompt = f"""Generate a simple English sentence containing the word '{word}' (meaning: {meaning}).
The sentence should match difficulty level {difficulty}/100 (keep it simple, crystal clear context).
Return ONLY a JSON object:
{{
  "sentence": "Sentence with the word",
  "blank_sentence": "Sentence with ______ replacing the word"
}}"""
        res = call_openrouter(prompt)
        blank_sentence = f"She was ______ to accept the offer." # Fallback
        if res:
            try:
                data = json.loads(res)
                blank_sentence = data.get("blank_sentence", blank_sentence)
            except Exception:
                pass
        
        hint = calculate_hint(word, difficulty)
        return {
            "type": TYPE_FILL_BLANK,
            "prompt": f"Điền từ còn thiếu vào chỗ trống:",
            "context": blank_sentence,
            "hint": hint,
            "correct_answer": word
        }

    elif q_type == TYPE_CHOICE_ENG:
        options = distractor_words + [word]
        random.shuffle(options)
        return {
            "type": TYPE_CHOICE_ENG,
            "prompt": f"Chọn từ tiếng Anh phù hợp với nghĩa:",
            "context": f"👉 **{meaning}**",
            "options": options,
            "correct_answer": word
        }

    elif q_type == TYPE_LISTENING:
        options = distractor_words + [word]
        random.shuffle(options)
        return {
            "type": TYPE_LISTENING,
            "prompt": f"Bấm nút nghe và chọn từ đúng với nghĩa: **{meaning}**",
            "context": word, # Dùng để phát âm
            "options": options,
            "correct_answer": word
        }

    elif q_type == TYPE_SPELLING:
        hint = calculate_hint(word, difficulty)
        return {
            "type": TYPE_SPELLING,
            "prompt": f"Gõ từ tiếng Anh có nghĩa là:",
            "context": f"👉 **{meaning}** ({word_item.get('part_of_speech', 'n/a')})",
            "hint": hint,
            "correct_answer": word
        }

    elif q_type == TYPE_PHONETIC:
        correct_phonetic = word_item.get("phonetic", "/rɪˈlʌktənt/")
        options = distractor_phonetics + [correct_phonetic]
        random.shuffle(options)
        return {
            "type": TYPE_PHONETIC,
            "prompt": f"Chọn phiên âm chuẩn cho từ mang nghĩa: **{meaning}** ({word})",
            "context": f"Từ: **{word}**",
            "options": options,
            "correct_answer": correct_phonetic
        }

# ==============================================================================
# STATE INITIALIZATION
# ==============================================================================
if "app_data" not in st.session_state:
    st.session_state.app_data = load_data()

if "review_session" not in st.session_state:
    st.session_state.review_session = {
        "active": False,
        "words": [],
        "current_index": 0,
        "combo": 0,
        "xp_gained": 0,
        "correct_list": [],
        "wrong_list": [],
        "current_q_data": None,
        "answered": False,
        "user_is_correct": False,
        "user_answer": ""
    }

# Update daily streak
today_str = datetime.now().strftime("%Y-%m-%d")
stats = st.session_state.app_data["stats"]
if stats.get("last_active") != today_str:
    if stats.get("last_active"):
        last_date = datetime.strptime(stats["last_active"], "%Y-%m-%d")
        if (datetime.now() - last_date).days == 1:
            stats["streak"] = stats.get("streak", 0) + 1
        elif (datetime.now() - last_date).days > 1:
            stats["streak"] = 1
    else:
        stats["streak"] = 1
    stats["last_active"] = today_str
    save_data(st.session_state.app_data)

# ==============================================================================
# UI COMPONENTS & TABS
# ==============================================================================

# Sidebar Header & Stats Summary
with st.sidebar:
    st.title("⚡ LingoPulse")
    st.caption("Game-like Spaced Repetition")
    
    st.markdown("---")
    c1, c2 = st.columns(2)
    c1.metric("🔥 Streak", f"{stats.get('streak', 0)} ngày")
    c2.metric("⭐ Total XP", f"{stats.get('xp', 0)}")

    total_words = len(st.session_state.app_data["vocabulary"])
    mastered = len([w for w in st.session_state.app_data["vocabulary"] if w.get("status") == "mastered"])
    st.metric("📚 Từ đã lưu", f"{total_words} (Thành thạo: {mastered})")
    
    st.markdown("---")
    st.caption("⚙️ **Cấu hình:** OpenRouter API Key (Secrets)")

tab1, tab2, tab3 = st.tabs(["🔍 SCAN / ADD WORDS", "🎮 REVIEW SESSION", "📖 VOCAB NOTEBOOK"])

# ==============================================================================
# TAB 1: SCAN TEXT
# ==============================================================================
with tab1:
    st.header("Quét văn bản & Trích xuất từ mới")
    st.write("Dán bất kỳ đoạn văn tiếng Anh nào. AI sẽ tự động phân tích và chọn lọc các từ đáng học nhất mà bạn chưa có trong kho dữ liệu.")

    sample_text = "I was reluctant to accept the offer because the circumstances were rather complicated."
    input_text = st.text_area("Nhập hoặc dán đoạn văn tiếng Anh:", value=sample_text, height=120)

    if st.button("🚀 SCAN TEXT", type="primary"):
        if not input_text.strip():
            st.warning("Vui lòng nhập đoạn văn bản.")
        else:
            with st.spinner("🤖 AI đang phân tích văn bản và lọc từ vựng..."):
                existing_words = [w["word"].lower() for w in st.session_state.app_data["vocabulary"]]
                
                prompt = f"""Analyze the following English text and extract 3 to 6 valuable vocabulary items/phrases for English learners.
Ignore basic common words (e.g., the, is, beautiful, happy) unless they have specific nuance.
Text: "{input_text}"

Current existing words in user database (DO NOT INCLUDE THESE AGAIN):
{json.dumps(existing_words)}

Return ONLY a valid JSON array of objects with the exact format:
[
  {{
    "word": "word or phrase",
    "meaning_vi": "nghĩa tiếng Việt chính xác",
    "part_of_speech": "noun/verb/adjective/etc.",
    "phonetic": "/IPA phonetic/",
    "topic": "Daily life/Work/Technology/etc.",
    "example": "example sentence from text or simple clear example"
  }}
]"""

                response = call_openrouter(prompt)
                if response:
                    try:
                        extracted = json.loads(response)
                        added_count = 0
                        for item in extracted:
                            w_lower = item["word"].lower().strip()
                            if w_lower not in existing_words:
                                new_vocab = {
                                    "id": str(int(time.time() * 1000)) + str(random.randint(100, 999)),
                                    "word": item["word"].strip(),
                                    "meaning_vi": item["meaning_vi"].strip(),
                                    "part_of_speech": item.get("part_of_speech", "n/a"),
                                    "phonetic": item.get("phonetic", "/.../"),
                                    "topic": item.get("topic", "General"),
                                    "example": item.get("example", ""),
                                    "difficulty": 20, # Khởi tạo rất dễ
                                    "first_seen": datetime.now().isoformat(),
                                    "last_review": None,
                                    "next_review": datetime.now().isoformat(), # Sẵn sàng ôn ngay
                                    "review_count": 0,
                                    "correct_count": 0,
                                    "wrong_count": 0,
                                    "status": "new"
                                }
                                st.session_state.app_data["vocabulary"].append(new_vocab)
                                existing_words.append(w_lower)
                                added_count += 1

                        save_data(st.session_state.app_data)
                        st.success(f"🎉 Đã tìm thấy và thêm thành công **{added_count}** từ mới!")
                        
                        if extracted:
                            st.subheader("Danh sách từ vừa quét:")
                            st.json(extracted)

                    except Exception as e:
                        st.error(f"Lỗi khi xử lý phản hồi từ AI: {e}")

# ==============================================================================
# TAB 2: REVIEW SESSION (GAMIFIED & SPACED REPETITION)
# ==============================================================================
with tab2:
    session = st.session_state.review_session
    vocab_list = st.session_state.app_data["vocabulary"]

    # Dashboard Header Metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🔥 Streak", f"{stats.get('streak', 0)}d")
    col2.metric("⭐ XP", f"{stats.get('xp', 0)}")
    
    total_rev = max(1, stats.get("total_reviews", 0))
    acc = int((stats.get("correct_reviews", 0) / total_rev) * 100) if stats.get("total_reviews", 0) > 0 else 100
    col3.metric("🎯 Accuracy", f"{acc}%")
    
    now_str = datetime.now().isoformat()
    due_count = len([w for w in vocab_list if w.get("next_review", "") <= now_str])
    col4.metric("⏳ Từ cần ôn", f"{due_count}")

    st.markdown("---")

    # Flow 1: Session chưa bắt đầu
    if not session["active"]:
        st.subheader("Chế độ Ôn Tập Nhanh (Micro-Session)")
        st.write("Mỗi lượt ôn tập **chỉ kéo dài 5 - 6 từ**. Trả lời nhanh, phản hồi lập tức, không gây nản!")

        if st.button("🚀 START REVIEW (6 WORDS)", type="primary", use_container_width=True):
            selected = select_review_words(vocab_list)
            if not selected:
                st.info("🎉 Tuyệt vời! Hiện tại bạn không có từ nào cần ôn tập. Hãy quét thêm từ mới ở TAB 1.")
            else:
                session["active"] = True
                session["words"] = selected
                session["current_index"] = 0
                session["combo"] = 0
                session["xp_gained"] = 0
                session["correct_list"] = []
                session["wrong_list"] = []
                session["current_q_data"] = None
                session["answered"] = False
                st.rerun()

    # Flow 2: Đang trong Session
    else:
        curr_idx = session["current_index"]
        total_in_sess = len(session["words"])

        # Kiêm tra nếu hoàn thành session
        if curr_idx >= total_in_sess:
            st.balloons()
            st.success("🎉 SESSION COMPLETE!")
            
            acc_sess = int((len(session['correct_list']) / total_in_sess) * 100)
            
            sc1, sc2, sc3 = st.columns(3)
            sc1.metric("Từ đã ôn", f"{total_in_sess}")
            sc2.metric("Chính xác", f"{acc_sess}%")
            sc3.metric("XP nhận được", f"+{session['xp_gained']}")

            st.write("### Kết quả chi tiết:")
            if session["correct_list"]:
                st.write("✅ **Từ trả lời đúng:** " + ", ".join([w["word"] for w in session["correct_list"]]))
            if session["wrong_list"]:
                st.write("❌ **Từ trả lời sai (Sẽ nhắc lại sớm):** " + ", ".join([w["word"] for w in session["wrong_list"]]))

            st.caption("💬 *Bạn vừa cứu các từ vựng này khỏi bị quên! Mai chỉ cần xử lý vài từ nữa thôi.*")

            if st.button("Đóng & Về Dashboard", type="primary"):
                session["active"] = False
                st.rerun()

        else:
            # Lấy từ hiện tại
            current_word_item = session["words"][curr_idx]

            # Progress bar
            st.progress((curr_idx) / total_in_sess, text=f"Câu {curr_idx + 1} / {total_in_sess} | Combo: 🔥 x{session['combo']}")

            # Sinh dữ liệu câu hỏi nếu chưa có cho câu hiện tại
            if session["current_q_data"] is None:
                q_type = random.choice(ALL_TYPES)
                session["current_q_data"] = generate_question_data(current_word_item, q_type, vocab_list)
                session["answered"] = False

            qdata = session["current_q_data"]

            # RENDER CÂU HỎI
            st.markdown(f"### {qdata['prompt']}")
            st.markdown(f"{qdata['context']}")

            if "hint" in qdata and qdata["hint"]:
                st.info(f"💡 Gợi ý (Hint): `{qdata['hint']}`")

            # Form nhập/chọn đáp án
            if not session["answered"]:
                with st.form(key=f"q_form_{curr_idx}"):
                    user_input = ""
                    
                    if qdata["type"] in [TYPE_FILL_BLANK, TYPE_SPELLING]:
                        user_input = st.text_input("Nhập đáp án của bạn:", key=f"input_{curr_idx}")
                    
                    elif qdata["type"] in [TYPE_CHOICE_ENG, TYPE_LISTENING, TYPE_PHONETIC]:
                        if qdata["type"] == TYPE_LISTENING:
                            if st.form_submit_button("🔊 Bấm để nghe phát âm"):
                                play_audio_script(qdata["context"])
                        
                        user_input = st.radio("Chọn đáp án:", qdata["options"], key=f"radio_{curr_idx}")

                    submit_btn = st.form_submit_button("Gửi đáp án 🚀", type="primary")

                    if submit_btn:
                        if not str(user_input).strip():
                            st.warning("Vui lòng nhập hoặc chọn đáp án.")
                        else:
                            # Đánh giá đáp án
                            is_correct = str(user_input).strip().lower() == str(qdata["correct_answer"]).strip().lower()
                            session["answered"] = True
                            session["user_is_correct"] = is_correct
                            session["user_answer"] = user_input

                            # Cập nhật Spaced Repetition Logic & Word item
                            updated_item = calculate_next_review(current_word_item, is_correct)
                            
                            # Cập nhật DB
                            for idx, w in enumerate(st.session_state.app_data["vocabulary"]):
                                if w["id"] == updated_item["id"]:
                                    st.session_state.app_data["vocabulary"][idx] = updated_item
                                    break

                            # Gamification rewards
                            stats["total_reviews"] = stats.get("total_reviews", 0) + 1
                            if is_correct:
                                stats["correct_reviews"] = stats.get("correct_reviews", 0) + 1
                                session["combo"] += 1
                                gained = 10 + (session["combo"] * 2)
                                session["xp_gained"] += gained
                                stats["xp"] = stats.get("xp", 0) + gained
                                session["correct_list"].append(updated_item)
                            else:
                                session["combo"] = 0
                                session["wrong_list"].append(updated_item)

                            save_data(st.session_state.app_data)
                            st.rerun()

            # RENDER FEEDBACK SAU KHI CÓ ĐÁP ÁN
            else:
                is_corr = session["user_is_correct"]
                correct_ans = qdata["correct_answer"]
                target_audio_word = current_word_item["word"]

                # PHÁT ÂM BẮT BUỘC DÙ ĐÚNG HAY SAI
                play_audio_script(target_audio_word)

                if is_corr:
                    st.success(f"✅ **CHÍNH XÁC!** +{10 + session['combo']*2} XP | Combo 🔥 x{session['combo']}")
                else:
                    st.error(f"❌ **SAI RỒI!** Đáp án đúng là: **{correct_ans}**")
                    st.info(f"💡 Nghĩa: **{current_word_item['meaning_vi']}** | Ví dụ: *{current_word_item.get('example', '')}*")

                st.caption(f"🔊 Đang phát âm từ: **{target_audio_word}**")

                if st.button("CÂU TIẾP THEO ➡️", type="primary"):
                    session["current_index"] += 1
                    session["current_q_data"] = None
                    session["answered"] = False
                    st.rerun()

# ==============================================================================
# TAB 3: VOCABULARY NOTEBOOK & READING GENERATION
# ==============================================================================
with tab3:
    st.header("📖 Sổ Tay Từ Vựng & Reading Adaptive")

    notebook_tab1, notebook_tab2 = st.tabs(["📚 Danh sách từ vựng", "📰 AI Reading Practice"])

    # SUB-TAB 1: NOTEBOOK
    with notebook_tab1:
        c_search, c_filter_topic, c_filter_status = st.columns([2, 1, 1])
        search_kw = c_search.text_input("🔍 Tìm kiếm từ/nghĩa:", "")
        
        all_topics = list(set([w.get("topic", "General") for w in vocab_list]))
        filter_topic = c_filter_topic.selectbox("Chủ đề", ["All"] + all_topics)
        filter_status = c_filter_status.selectbox("Trạng thái", ["All", "new", "learning", "mastered"])

        # Lọc dữ liệu
        filtered_vocab = vocab_list
        if search_kw:
            filtered_vocab = [w for w in filtered_vocab if search_kw.lower() in w["word"].lower() or search_kw.lower() in w["meaning_vi"].lower()]
        if filter_topic != "All":
            filtered_vocab = [w for w in filtered_vocab if w.get("topic") == filter_topic]
        if filter_status != "All":
            filtered_vocab = [w for w in filtered_vocab if w.get("status") == filter_status]

        st.caption(f"Hiển thị {len(filtered_vocab)} / {len(vocab_list)} từ vựng")

        # Hiển thị dạng bảng card
        for item in filtered_vocab:
            with st.expander(f"🔹 **{item['word']}** ({item.get('phonetic', '')}) — *{item['meaning_vi']}*"):
                col_a, col_b = st.columns(2)
                col_a.write(f"**Từ loại:** {item.get('part_of_speech', 'n/a')}")
                col_a.write(f"**Chủ đề:** {item.get('topic', 'General')}")
                col_a.write(f"**Độ khó (Adaptive):** {item.get('difficulty', 20)}/100")
                
                col_b.write(f"**Trạng thái:** `{item.get('status', 'new')}`")
                col_b.write(f"**Số lần ôn:** {item.get('review_count', 0)} (Đúng: {item.get('correct_count', 0)} | Sai: {item.get('wrong_count', 0)})")
                col_b.write(f"**Lần ôn tiếp:** {item.get('next_review', 'N/A')[:16].replace('T', ' ')}")

                st.write(f"**Ví dụ:** *{item.get('example', 'Chưa có ví dụ')}*")
                
                if st.button(f"🔊 Nghe phát âm", key=f"audio_btn_{item['id']}"):
                    play_audio_script(item["word"])

    # SUB-TAB 2: READING PRACTICE (Adaptive IELTS Reading)
    with notebook_tab2:
        st.subheader("Tự động tạo bài Reading từ Vocabulary")
        st.write("Khi một chủ đề có từ **5 từ vựng trở lên**, AI sẽ tự động viết một đoạn văn ngắn IELTS-style ghép nối các từ đó lại với nhau theo đúng độ khó vừa sức nhất của bạn.")

        # Gom nhóm từ theo topic
        topic_groups = {}
        for w in vocab_list:
            t = w.get("topic", "General")
            topic_groups.setdefault(t, []).append(w)

        eligible_topics = {k: v for k, v in topic_groups.items() if len(v) >= 3} # Hạ tiêu chí xuống 3 để dễ test

        if not eligible_topics:
            st.info("💡 Bạn cần học ít nhất 3-5 từ thuộc cùng một chủ đề (Topic) để kích hoạt tính năng tạo bài Reading.")
        else:
            selected_read_topic = st.selectbox("Chọn chủ đề luyện Reading:", list(eligible_topics.keys()))
            words_in_topic = eligible_topics[selected_read_topic]

            # QUY TẮC PHÁT TRIỂN: Lấy difficulty THẤP NHẤT trong nhóm
            lowest_difficulty = min([w.get("difficulty", 20) for w in words_in_topic])

            st.write(f"**Số từ vựng tích lũy:** {len(words_in_topic)} từ | **Độ khó Reading (Lowest Rule):** `{lowest_difficulty}/100`")

            if st.button("📰 AI Generate Reading Passage", type="primary"):
                with st.spinner("🤖 AI đang biên soạn bài đọc phù hợp độ khó..."):
                    vocab_words = [w["word"] for w in words_in_topic]
                    prompt = f"""Write a simple, natural English passage (100-180 words) in IELTS style.
Topic: {selected_read_topic}
Target Difficulty Level: {lowest_difficulty}/100 (Keep sentences simple if level is low).
MUST naturally integrate these target vocabulary words: {json.dumps(vocab_words)}

Return ONLY JSON:
{{
  "title": "Passage Title",
  "passage": "Full English passage text...",
  "target_words_used": ["word1", "word2"]
}}"""
                    res = call_openrouter(prompt)
                    if res:
                        try:
                            read_data = json.loads(res)
                            st.session_state["current_reading"] = read_data
                        except Exception as e:
                            st.error(f"Lỗi tạo bài đọc: {e}")

            if "current_reading" in st.session_state:
                rd = st.session_state["current_reading"]
                st.markdown(f"### 📖 {rd.get('title', 'Reading Article')}")
                st.markdown(f"> {rd.get('passage', '')}")
                
                st.markdown("---")
                st.subheader("🎯 Thử thách dịch bài (Translation Test)")
                user_trans = st.text_area("Hãy dịch đoạn văn trên sang tiếng Việt để kiểm tra mức độ hiểu bài:", height=120)

                if st.button("Chấm điểm bản dịch 📝"):
                    if not user_trans.strip():
                        st.warning("Vui lòng nhập bản dịch của bạn.")
                    else:
                        with st.spinner("🤖 AI đang đánh giá ngữ nghĩa và độ hiểu..."):
                            grade_prompt = f"""Evaluate the user's Vietnamese translation of the English reading text.

English Text: "{rd.get('passage')}"
User Vietnamese Translation: "{user_trans}"

Evaluate two metrics:
1. Semantic Accuracy (%)
2. Comprehension (%)

Provide brief constructive feedback in Vietnamese.
Return ONLY JSON:
{{
  "semantic_accuracy": 85,
  "comprehension": 90,
  "feedback": "Nhận xét ngắn gọn..."
}}"""
                            res_grade = call_openrouter(grade_prompt)
                            if res_grade:
                                try:
                                    g_data = json.loads(res_grade)
                                    st.success("🎉 Đã chấm điểm xong!")
                                    
                                    m1, m2 = st.columns(2)
                                    m1.metric("Semantic Accuracy", f"{g_data.get('semantic_accuracy', 0)}%")
                                    m2.metric("Comprehension", f"{g_data.get('comprehension', 0)}%")
                                    
                                    st.write(f"💬 **Nhận xét AI:** {g_data.get('feedback', '')}")
                                except Exception as e:
                                    st.error(f"Lỗi chấm điểm: {e}")
