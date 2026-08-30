import json
import random
import re
import time
from datetime import datetime, timedelta
import requests
import streamlit as st

# ==============================================================================
# 0. CONFIG & CONSTANTS
# ==============================================================================
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "minimax/minimax-m3:free"
DATA_FILE = "vocab_data.json"

DEFAULT_STATS = {
    "xp": 0,
    "streak": 0,
    "last_study_date": None,
    "words_mastered": 0,
    "total_reviews": 0,
    "correct_reviews": 0,
}

TOPICS = [
    "Daily life", "Work", "Technology", "Education", "Environment",
    "Business", "Health", "Science", "Travel", "General"
]

# ==============================================================================
# 1. PERSISTENCE (LOCAL JSON)
# ==============================================================================
def load_data():
    """Tải dữ liệu từ file local JSON. Tạo mới nếu chưa có."""
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "vocabulary" not in data:
                data["vocabulary"] = []
            if "stats" not in data:
                data["stats"] = DEFAULT_STATS.copy()
            if "readings" not in data:
                data["readings"] = []
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "vocabulary": [],
            "stats": DEFAULT_STATS.copy(),
            "readings": []
        }

def save_data(data):
    """Lưu dữ liệu vào file local JSON."""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ==============================================================================
# 2. OPENROUTER AI HELPER
# ==============================================================================
def call_openrouter(messages, temperature=0.7, retries=2):
    """
    Gọi OpenRouter API an toàn với cơ chế retry và bắt lỗi.
    Lấy API key từ st.secrets["OPENROUTER_API_KEY"].
    """
    api_key = st.secrets.get("OPENROUTER_API_KEY", None)
    if not api_key:
        st.error("❌ Không tìm thấy OPENROUTER_API_KEY trong Streamlit Secrets!")
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://streamlit.io",
        "X-Title": "Spaced Repetition Vocab App"
    }

    payload = {
        "model": DEFAULT_MODEL,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"}
    }

    for attempt in range(retries + 1):
        try:
            response = requests.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload,
                timeout=20
            )
            response.raise_for_status()
            res_json = response.json()
            content = res_json['choices'][0]['message']['content']
            
            # Cleaning JSON Markdown format block if present
            content_clean = re.sub(r"^```json\s*", "", content.strip())
            content_clean = re.sub(r"\s*```$", "", content_clean)
            
            return json.loads(content_clean)
        except Exception as e:
            if attempt == retries:
                st.warning(f"⚠️ Lỗi kết nối AI hoặc JSON malformed: {str(e)}")
                return None
            time.sleep(1)
    return None

# ==============================================================================
# 3. ALGORITHMS & HELPERS
# ==============================================================================
def calculate_hint(word_str, difficulty):
    """
    Tạo hint dựa trên difficulty (0-100).
    Thuật toán ưu tiên:
    1. Nguyên âm (a, e, i, o, u)
    2. Phụ âm
    3. Reveal ít hơn khi difficulty cao.
    """
    word_str = word_str.strip()
    n = len(word_str)
    if n <= 3:
        # Từ quá ngắn: chỉ reveal chữ đầu nếu difficulty thấp
        return word_str[0] + "_" * (n - 1) if difficulty < 50 else "_" * n

    # Số ký tự được hiển thị dựa theo difficulty
    if difficulty < 30:
        reveal_count = max(2, int(n * 0.5))
    elif difficulty < 70:
        reveal_count = max(1, int(n * 0.3))
    else:
        reveal_count = max(1, int(n * 0.15))

    vowels = ['a', 'e', 'i', 'o', 'u']
    vowel_indices = [i for i, ch in enumerate(word_str.lower()) if ch in vowels]
    consonant_indices = [i for i, ch in enumerate(word_str.lower()) if ch.isalpha() and ch not in vowels]

    indices_to_show = set()

    # Ưu tiên 1: Nguyên âm
    random.shuffle(vowel_indices)
    for idx in vowel_indices:
        if len(indices_to_show) < reveal_count:
            indices_to_show.add(idx)

    # Ưu tiên 2: Phụ âm nếu chưa đủ quota
    random.shuffle(consonant_indices)
    for idx in consonant_indices:
        if len(indices_to_show) < reveal_count:
            indices_to_show.add(idx)

    # Build pattern String
    hint_chars = []
    for i, ch in enumerate(word_str):
        if not ch.isalpha():
            hint_chars.append(ch)
        elif i in indices_to_show:
            hint_chars.append(ch)
        else:
            hint_chars.append("_")

    return " ".join(hint_chars)

def calculate_next_review(word_item, is_correct):
    """
    Short Spaced Repetition Logic.
    Interval rất ngắn để duy trì momentum học tập.
    """
    now = datetime.now()
    review_count = word_item.get("review_count", 0) + 1
    
    if is_correct:
        word_item["correct_count"] = word_item.get("correct_count", 0) + 1
        word_item["difficulty"] = max(0, word_item.get("difficulty", 20) + 5)
        
        # Short intervals: 15m -> 1h -> 4h -> 12h -> 1d -> 2d -> max 5d
        intervals = [15, 60, 240, 720, 1440, 2880, 7200]
        idx = min(review_count - 1, len(intervals) - 1)
        next_minutes = intervals[idx]
    else:
        word_item["wrong_count"] = word_item.get("wrong_count", 0) + 1
        word_item["difficulty"] = max(0, word_item.get("difficulty", 20) - 8)
        # Nếu sai: giảm interval mạnh xuống 5 - 15 phút
        next_minutes = random.choice([5, 10, 15])

    # Check Mastered Status
    if word_item.get("correct_count", 0) >= 4 and word_item.get("wrong_count", 0) <= 1:
        word_item["status"] = "mastered"
    else:
        word_item["status"] = "learning"

    word_item["review_count"] = review_count
    word_item["last_review"] = now.isoformat()
    word_item["next_review"] = (now + timedelta(minutes=next_minutes)).isoformat()
    return word_item

def trigger_audio(text):
    """Web Speech API JavaScript Injection cho Audio TTS ngay lập tức."""
    js_code = f"""
    <script>
        var msg = new SpeechSynthesisUtterance("{text}");
        msg.lang = 'en-US';
        msg.rate = 0.85;
        window.speechSynthesis.speak(msg);
    </script>
    """
    st.components.v1.html(js_code, height=0)

# ==============================================================================
# 4. QUESTION GENERATION ENGINE (AI + FALLBACK)
# ==============================================================================
def generate_question_for_word(word_item, existing_words):
    """
    Tạo ngẫu nhiên 1 trong 5 dạng câu hỏi phù hợp với difficulty của từ.
    """
    q_type = random.choice([1, 2, 3, 4, 5])
    word = word_item["word"]
    meaning = word_item["meaning_vi"]
    difficulty = word_item.get("difficulty", 20)

    # Lấy danh sách từ khác làm distractors
    other_words = [w for w in existing_words if w["word"].lower() != word.lower()]
    random.shuffle(other_words)

    # Prompt AI để lấy câu ví dụ/context adaptive
    prompt = f"""
    Generate a simple english sentence for the word '{word}' (meaning: '{meaning}').
    Difficulty scale (0-100): {difficulty}.
    Rules:
    - If difficulty is low (<40), use extremely simple grammar and clear context.
    - Do not use overly complex academic words.
    - Return JSON format: {{"sentence": "The exact sentence with the target word", "blank_sentence": "Sentence with target word replaced by ______"}}
    """

    ai_res = call_openrouter([{"role": "user", "content": prompt}], temperature=0.7)
    
    if ai_res and "sentence" in ai_res:
        sentence = ai_res["sentence"]
        blank_sentence = ai_res.get("blank_sentence", sentence.replace(word, "______"))
    else:
        # Fallback local nếu AI timeout/lỗi
        ex = word_item.get("example", f"I want to learn about {word}.")
        sentence = ex
        blank_sentence = re.sub(re.escape(word), "______", ex, flags=re.IGNORECASE)
        if "______" not in blank_sentence:
            blank_sentence = f"Fill the word '{meaning}': ______"

    # --- DẠNG 1: FILL IN THE BLANK ---
    if q_type == 1:
        return {
            "type": 1,
            "type_title": "✍️ Fill in the Blank",
            "word": word,
            "meaning": meaning,
            "context": blank_sentence,
            "hint": calculate_hint(word, difficulty),
            "correct_answer": word
        }

    # --- DẠNG 2: CHỌN NGHĨA TIẾNG ANH ---
    elif q_type == 2:
        distractors = [w["word"] for w in other_words[:3]]
        while len(distractors) < 3:
            distractors.append(f"word_{random.randint(100,999)}")
        options = distractors + [word]
        random.shuffle(options)
        return {
            "type": 2,
            "type_title": "🎯 Choose the English Word",
            "word": word,
            "meaning": meaning,
            "prompt_text": f"Từ nào có nghĩa là: **'{meaning}'**?",
            "options": options,
            "correct_answer": word
        }

    # --- DẠNG 3: NGHE + CHỌN TỪ ---
    elif q_type == 3:
        distractors = [w["word"] for w in other_words[:3]]
        while len(distractors) < 3:
            distractors.append(f"option_{random.randint(10,99)}")
        options = distractors + [word]
        random.shuffle(options)
        return {
            "type": 3,
            "type_title": "🎧 Listen & Select",
            "word": word,
            "meaning": meaning,
            "prompt_text": f"Nghe phát âm và chọn từ đúng (Nghĩa: {meaning})",
            "options": options,
            "correct_answer": word
        }

    # --- DẠNG 4: SPELLING ---
    elif q_type == 4:
        return {
            "type": 4,
            "type_title": "🔤 Spelling Challenge",
            "word": word,
            "meaning": meaning,
            "context": f"Nghĩa: **{meaning}** | Topic: {word_item.get('topic', 'General')}",
            "hint": calculate_hint(word, difficulty),
            "correct_answer": word
        }

    # --- DẠNG 5: CHỌN PHIÊN ÂM ---
    else:
        phonetic = word_item.get("phonetic", "/.../")
        distractor_phonetics = [w.get("phonetic", "/.../") for w in other_words if w.get("phonetic")]
        
        # Fallback phonetics nếu thiếu
        dummy_phonetics = ["/rɪˈlʌktənt/", "/ˈrelevənt/", "/rɪˈzɪstənt/", "/ˈkiːən/"]
        for p in dummy_phonetics:
            if p != phonetic and len(distractor_phonetics) < 3:
                distractor_phonetics.append(p)

        options = distractor_phonetics[:3] + [phonetic]
        random.shuffle(options)
        return {
            "type": 5,
            "type_title": "🗣️ Select Correct Pronunciation",
            "word": word,
            "meaning": meaning,
            "prompt_text": f"Chọn phiên âm chuẩn IPA cho từ: **{word}** ({meaning})",
            "options": options,
            "correct_answer": phonetic
        }

# ==============================================================================
# 5. STREAMLIT UI & TAB RENDERERS
# ==============================================================================

def init_session_state():
    """Khởi tạo session_state cho ứng dụng."""
    if "data" not in st.session_state:
        st.session_state.data = load_data()
    if "session_active" not in st.session_state:
        st.session_state.session_active = False
    if "current_queue" not in st.session_state:
        st.session_state.current_queue = []
    if "current_q_index" not in st.session_state:
        st.session_state.current_q_index = 0
    if "current_question" not in st.session_state:
        st.session_state.current_question = None
    if "answered" not in st.session_state:
        st.session_state.answered = False
    if "session_stats" not in st.session_state:
        st.session_state.session_stats = {"correct": 0, "total": 0, "xp_gained": 0}
    if "combo" not in st.session_state:
        st.session_state.combo = 0
    if "temp_correct" not in st.session_state:
        st.session_state.temp_correct = []
    if "temp_wrong" not in st.session_state:
        st.session_state.temp_wrong = []

# --- TAB 1: SCAN / ADD WORDS ---
def render_tab_scan():
    st.markdown("### 🔍 Scan Text & Instant Extract")
    st.caption("Paste bất kỳ đoạn văn tiếng Anh nào. AI sẽ tự chọn các từ đáng học nhất và loại bỏ từ trùng lặp!")
    
    text_input = st.text_area("Nhập đoạn văn tiếng Anh:", height=150, placeholder="I was reluctant to accept the offer because the circumstances were rather complicated.")
    
    if st.button("🚀 SCAN TEXT", use_container_width=True):
        if not text_input.strip():
            st.warning("Vui lòng nhập đoạn văn trước khi Scan!")
            return

        with st.spinner("🤖 AI đang phân tích và lọc từ vựng..."):
            existing_words = {w["word"].lower() for w in st.session_state.data["vocabulary"]}
            
            prompt = f"""
            Analyze the following text and extract 3-6 valuable English vocabulary items to learn.
            Text: "{text_input}"

            Rules:
            1. Skip extremely basic words (e.g., 'is', 'the', 'go', 'happy').
            2. For each word, provide: word, meaning_vi, part_of_speech, phonetic (IPA), topic (choose one: {', '.join(TOPICS)}), simple example sentence.
            3. Do not include words already in this list: {list(existing_words)}
            4. Return strictly JSON format:
            {{
                "words": [
                    {{
                        "word": "reluctant",
                        "meaning_vi": "miễn cưỡng",
                        "part_of_speech": "adjective",
                        "phonetic": "/rɪˈlʌktənt/",
                        "topic": "Daily life",
                        "example": "She was reluctant to leave."
                    }}
                ]
            }}
            """
            
            res = call_openrouter([{"role": "user", "content": prompt}])
            
            if res and "words" in res and len(res["words"]) > 0:
                added_count = 0
                now_str = datetime.now().isoformat()
                
                for item in res["words"]:
                    w_lower = item["word"].lower().strip()
                    if w_lower not in existing_words:
                        new_entry = {
                            "id": str(random.randint(100000, 999999)),
                            "word": item["word"].strip(),
                            "meaning_vi": item.get("meaning_vi", ""),
                            "part_of_speech": item.get("part_of_speech", ""),
                            "phonetic": item.get("phonetic", ""),
                            "topic": item.get("topic", "General"),
                            "example": item.get("example", ""),
                            "difficulty": 20, # Bắt đầu rất dễ
                            "status": "new",
                            "created_at": now_str,
                            "last_review": None,
                            "next_review": now_str, # Sẵn sàng học ngay
                            "review_count": 0,
                            "correct_count": 0,
                            "wrong_count": 0
                        }
                        st.session_state.data["vocabulary"].append(new_entry)
                        existing_words.add(w_lower)
                        added_count += 1
                
                if added_count > 0:
                    save_data(st.session_state.data)
                    st.balloons()
                    st.success(f"🎉 Đã thêm thành công {added_count} từ vựng mới vào Notebook!")
                else:
                    st.info("💡 Tất cả các từ đáng học trong đoạn văn đều đã có trong Notebook của bạn!")
            else:
                st.error("Không thể trích xuất từ vựng. Vui lòng thử lại đoạn văn khác.")

# --- TAB 2: REVIEW (MICRO-SESSION GAME) ---
def render_tab_review():
    stats = st.session_state.data["stats"]
    
    # 1. Header Metrics Dashboard
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🔥 Streak", f"{stats['streak']} Days")
    col2.metric("⭐ Total XP", stats['xp'])
    col3.metric("📚 Words", len(st.session_state.data["vocabulary"]))
    acc = int((stats['correct_reviews'] / stats['total_reviews'] * 100)) if stats['total_reviews'] > 0 else 0
    col4.metric("🎯 Accuracy", f"{acc}%")

    st.markdown("---")

    # 2. Logic bắt đầu Session mới
    if not st.session_state.session_active:
        st.subheader("🎯 Ready for a Quick 5–6 Words Review?")
        st.caption("Mỗi session chỉ gồm 6 câu hỏi ngẫu nhiên. Nhanh chóng, tập trung và không gây ngợp!")
        
        if st.button("🚀 START REVIEW SESSION", use_container_width=True, type="primary"):
            vocab = st.session_state.data["vocabulary"]
            now_str = datetime.now().isoformat()
            
            # Ưu tiên: 1. Due Wrong/New 2. Due Words 3. Sắp đến hạn
            due_words = [w for w in vocab if w.get("next_review", "") <= now_str or w.get("status") == "new"]
            
            if not due_words:
                # Fallback: Lấy các từ ít được review nhất
                due_words = sorted(vocab, key=lambda x: x.get("next_review", ""))
            
            if not due_words:
                st.info("🎉 Chưa có từ vựng nào trong danh sách. Hãy sang Tab 1 để Scan thêm từ nhé!")
                return
            
            selected_words = random.sample(due_words, min(6, len(due_words)))
            
            st.session_state.current_queue = selected_words
            st.session_state.current_q_index = 0
            st.session_state.session_active = True
            st.session_state.session_stats = {"correct": 0, "total": len(selected_words), "xp_gained": 0}
            st.session_state.temp_correct = []
            st.session_state.temp_wrong = []
            st.session_state.combo = 0
            st.session_state.answered = False
            st.session_state.current_question = generate_question_for_word(
                selected_words[0], st.session_state.data["vocabulary"]
            )
            st.rerun()
        return

    # 3. Trong khi đang trong Session
    queue = st.session_state.current_queue
    idx = st.session_state.current_q_index

    # --- SESSION COMPLETE SUMMARY ---
    if idx >= len(queue):
        st.balloons()
        st.markdown("## 🎉 Session Complete!")
        s_stats = st.session_state.session_stats
        acc_session = int((s_stats['correct'] / s_stats['total']) * 100) if s_stats['total'] > 0 else 0
        
        st.success(f"""
        **Kết quả lượt học:**
        - 📚 **Words Reviewed:** {s_stats['total']}
        - ✅ **Correct:** {s_stats['correct']}
        - 🎯 **Accuracy:** {acc_session}%
        - ⭐ **XP Gained:** +{s_stats['xp_gained']} XP
        """)
        
        # Cập nhật Global Stats
        stats["xp"] += s_stats["xp_gained"]
        stats["total_reviews"] += s_stats["total"]
        stats["correct_reviews"] += s_stats["correct"]
        
        # Update Daily Streak
        today_str = datetime.now().strftime("%Y-%m-%d")
        last_date = stats.get("last_study_date")
        if last_date != today_str:
            if last_date == (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"):
                stats["streak"] += 1
            elif last_date is None:
                stats["streak"] = 1
            stats["last_study_date"] = today_str

        save_data(st.session_state.data)

        if st.button("🔥 Continue Learning (Another 6 Words)", use_container_width=True):
            st.session_state.session_active = False
            st.rerun()
        return

    # --- RENDER QUESTION GAME UI ---
    q = st.session_state.current_question
    curr_word_item = queue[idx]

    # Progress bar & Combo
    st.progress((idx) / len(queue))
    st.caption(f"Question {idx + 1} of {len(queue)} | 🔥 Combo: x{st.session_state.combo}")
    
    st.markdown(f"### {q['type_title']}")
    
    # Form/Container cho Question
    with st.container():
        user_choice = None
        
        if q["type"] == 1 or q["type"] == 4:
            st.markdown(f"**Context:** {q.get('context', '')}")
            st.markdown(f"💡 **Hint:** `{q['hint']}`")
            user_choice = st.text_input("Nhập đáp án tiếng Anh:", key=f"input_{idx}").strip()
            
        elif q["type"] == 2 or q["type"] == 5:
            st.markdown(q["prompt_text"])
            user_choice = st.radio("Chọn đáp án đúng:", q["options"], key=f"radio_{idx}")
            
        elif q["type"] == 3:
            st.markdown(q["prompt_text"])
            if st.button("🔊 Play Audio", key=f"audio_btn_{idx}"):
                trigger_audio(q["word"])
            user_choice = st.radio("Chọn từ bạn nghe được:", q["options"], key=f"radio_listen_{idx}")

        # --- SUBMIT ANSWER LOGIC ---
        if not st.session_state.answered:
            if st.button("CHECK ANSWER 🚀", type="primary", use_container_width=True):
                if not user_choice:
                    st.warning("Vui lòng nhập/chọn đáp án!")
                    return

                st.session_state.answered = True
                is_correct = (user_choice.lower() == q["correct_answer"].lower())
                
                # Auto Play Audio phát âm từ sau khi trả lời (Dù Đúng hay Sai)
                trigger_audio(q["word"])
                
                # Cập nhật Spaced Repetition Data cho từ
                updated_item = calculate_next_review(curr_word_item, is_correct)
                
                # Cập nhật vào global vocab data
                for i, w in enumerate(st.session_state.data["vocabulary"]):
                    if w["word"].lower() == updated_item["word"].lower():
                        st.session_state.data["vocabulary"][i] = updated_item
                        break

                if is_correct:
                    st.session_state.combo += 1
                    earned_xp = 10 + (st.session_state.combo * 2)
                    st.session_state.session_stats["correct"] += 1
                    st.session_state.session_stats["xp_gained"] += earned_xp
                    st.session_state.temp_correct.append(q["word"])
                    st.session_state.last_result = ("correct", earned_xp)
                else:
                    st.session_state.combo = 0
                    st.session_state.temp_wrong.append(q["word"])
                    st.session_state.last_result = ("wrong", 0)

                save_data(st.session_state.data)
                st.rerun()

        # --- FEEDBACK DISPLAY & NEXT BUTTON ---
        else:
            res_type, xp = st.session_state.last_result
            if res_type == "correct":
                st.success(f"✅ **CHÍNH XÁC!** (+{xp} XP) 🔊 Pronouncing '{q['word']}'...")
            else:
                st.error(f"❌ **SAI RỒI!** Đáp án đúng là: **{q['correct_answer']}** 🔊 Pronouncing '{q['word']}'...")
                st.info(f"💡 Nghĩa: {q['meaning']}")

            if st.button("NEXT QUESTION ➡️", use_container_width=True, type="primary"):
                st.session_state.answered = False
                st.session_state.current_q_index += 1
                if st.session_state.current_q_index < len(queue):
                    next_word = queue[st.session_state.current_q_index]
                    st.session_state.current_question = generate_question_for_word(
                        next_word, st.session_state.data["vocabulary"]
                    )
                st.rerun()

# --- TAB 3: VOCABULARY NOTEBOOK & READING GENERATOR ---
def render_tab_notebook():
    st.markdown("### 📚 Vocabulary Notebook & AI Reading")
    vocab = st.session_state.data["vocabulary"]

    if not vocab:
        st.info("Sổ tay từ vựng trống. Hãy dùng Tab 1 để Scan thêm từ mới!")
        return

    # Sub-tabs cho Notebook
    nt_tab1, nt_tab2 = st.tabs(["📖 Word List", "📰 AI Topic Reading"])

    # 1. WORD LIST VIEW
    with nt_tab1:
        col_s, col_f1, col_f2 = st.columns([2, 1, 1])
        search_q = col_s.text_input("🔍 Tìm kiếm từ...", "")
        topic_filter = col_f1.selectbox("Filter Topic:", ["All"] + TOPICS)
        status_filter = col_f2.selectbox("Filter Status:", ["All", "new", "learning", "mastered"])

        # Lọc danh sách
        filtered_vocab = vocab
        if search_q:
            filtered_vocab = [w for w in filtered_vocab if search_q.lower() in w["word"].lower() or search_q.lower() in w["meaning_vi"].lower()]
        if topic_filter != "All":
            filtered_vocab = [w for w in filtered_vocab if w.get("topic") == topic_filter]
        if status_filter != "All":
            filtered_vocab = [w for w in filtered_vocab if w.get("status") == status_filter]

        st.caption(f"Hiển thị {len(filtered_vocab)} / {len(vocab)} từ")

        for w in filtered_vocab:
            with st.expander(f"**{w['word']}** {w.get('phonetic', '')} — *{w.get('meaning_vi', '')}*"):
                c1, c2 = st.columns(2)
                c1.write(f"**Part of Speech:** {w.get('part_of_speech', 'N/A')}")
                c1.write(f"**Topic:** {w.get('topic', 'General')}")
                c1.write(f"**Difficulty:** {w.get('difficulty', 20)}/100")
                
                c2.write(f"**Status:** `{w.get('status', 'new')}`")
                c2.write(f"**Reviews:** {w.get('review_count', 0)} (Correct: {w.get('correct_count', 0)})")
                c2.write(f"**Next Review:** {w.get('next_review', 'Now')[:16].replace('T', ' ')}")
                
                if w.get("example"):
                    st.caption(f"💬 Example: *{w['example']}*")
                
                if st.button(f"🔊 Listen '{w['word']}'", key=f"nb_sound_{w['id']}"):
                    trigger_audio(w['word'])

    # 2. READING GENERATION VIEW
    with nt_tab2:
        st.markdown("#### 📰 AI Adaptive Reading Practice")
        st.caption("Tự động tạo đoạn văn ngắn tích hợp từ vựng đã học theo Topic khi đạt đủ 5+ từ!")
        
        selected_topic = st.selectbox("Chọn Topic để đọc:", TOPICS)
        topic_words = [w for w in vocab if w.get("topic") == selected_topic]
        
        st.write(f"Số từ đã học trong topic **{selected_topic}**: {len(topic_words)} từ.")

        if len(topic_words) < 3:
            st.warning("⚠️ Bạn cần có ít nhất 3 từ vựng trong Topic này để tạo bài đọc IELTS phù hợp!")
        else:
            if st.button("✨ Generate AI Reading Passage", type="primary"):
                with st.spinner("🤖 AI đang biên soạn bài đọc adaptive..."):
                    # ALGORITHM: Lấy difficulty thấp nhất làm difficulty bài đọc
                    min_diff = min([w.get("difficulty", 20) for w in topic_words])
                    word_list_str = ", ".join([w["word"] for w in topic_words])
                    
                    prompt = f"""
                    Create a short reading passage (100-180 words) in English about topic '{selected_topic}'.
                    Target vocabulary to include naturally: {word_list_str}.
                    Reading difficulty level (0-100): {min_diff} (Keep sentences easy to digest if low).
                    Return JSON:
                    {{
                        "title": "Passage Title",
                        "content": "Full English passage text...",
                        "target_words_used": ["word1", "word2"]
                    }}
                    """
                    reading_res = call_openrouter([{"role": "user", "content": prompt}])
                    if reading_res and "content" in reading_res:
                        st.session_state.current_reading = reading_res
                    else:
                        st.error("Không thể tạo bài đọc lúc này.")

        # Hiển thị bài đọc và phần dịch
        if "current_reading" in st.session_state:
            rd = st.session_state.current_reading
            st.markdown(f"### 📖 {rd.get('title', 'Reading Practice')}")
            st.info(rd["content"])
            
            st.markdown("#### ✍️ Translation Challenge")
            user_translation = st.text_area("Hãy dịch đoạn văn trên sang tiếng Việt:")
            
            if st.button("CHẤM BẢN DỊCH 📝"):
                if not user_translation.strip():
                    st.warning("Vui lòng nhập bản dịch của bạn!")
                else:
                    with st.spinner("🤖 AI đang đánh giá bản dịch..."):
                        grade_prompt = f"""
                        Original English: "{rd['content']}"
                        User Vietnamese Translation: "{user_translation}"

                        Evaluate semantic accuracy and comprehension.
                        Return JSON format:
                        {{
                            "semantic_accuracy": 88,
                            "comprehension": 90,
                            "feedback": "Nhận xét ngắn gọn ưu/nhược điểm bản dịch..."
                        }}
                        """
                        g_res = call_openrouter([{"role": "user", "content": grade_prompt}])
                        if g_res:
                            st.markdown("##### 🎯 Kết quả đánh giá AI:")
                            st.write(f"📊 **Semantic Accuracy:** {g_res.get('semantic_accuracy', 0)}%")
                            st.write(f"🧠 **Comprehension:** {g_res.get('comprehension', 0)}%")
                            st.success(f"💬 **Feedback:** {g_res.get('feedback', '')}")

# ==============================================================================
# 6. MAIN APP ENTRY POINT
# ==============================================================================
def main():
    st.set_page_config(
        page_title="VocabBuilder AI",
        page_icon="⚡",
        layout="wide",
        initial_sidebar_state="collapsed"
    )

    init_session_state()

    st.title("⚡ Spaced Repetition Vocab Game")
    st.caption("Học từ vựng siêu tốc • Micro-sessions • AI Adaptive")

    tab1, tab2, tab3 = st.tabs([
        "🔍 TAB 1: SCAN / ADD WORDS",
        "🎮 TAB 2: REVIEW SESSION",
        "📚 TAB 3: VOCAB NOTEBOOK"
    ])

    with tab1:
        render_tab_scan()
    with tab2:
        render_tab_review()
    with tab3:
        render_tab_notebook()

if __name__ == "__main__":
    main()
