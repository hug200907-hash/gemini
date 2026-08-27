import streamlit as st
import concurrent.futures
import time
from openai import OpenAI

st.set_page_config(page_title="OpenRouter Free Multi-Model Test", page_icon="🌐", layout="wide")
st.title("🌐 Auto-Test & So sánh phản hồi các Model Free trên OpenRouter")

# Nhập API Key OpenRouter (dạng sk-or-v1-...)
api_key = st.sidebar.text_input("Nhập OpenRouter API Key (sk-or-v1-...):", type="password")

if not api_key:
    st.info("💡 Bạn có thể lấy API Key miễn phí tại: https://openrouter.ai/keys", icon="ℹ️")
else:
    try:
        # OpenRouter tương thích hoàn toàn với thư viện OpenAI
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key.strip(),
        )

        # ---------------------------------------------------------
        # BƯỚC 1: LẤY DANH SÁCH VÀ AUTO-TEST CÁC MODEL MIỄN PHÍ
        # ---------------------------------------------------------
        @st.cache_data(show_spinner=False)
        def get_free_working_models(_key_str):
            c = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=_key_str,
            )
            
            # Lấy toàn bộ danh sách model từ OpenRouter
            all_models = c.models.list()
            # Lọc các model có chữ ':free' trong ID (các model hoàn toàn miễn phí)
            free_models = [m.id for m in all_models.data if ":free" in m.id]
            
            working_list = []
            progress_bar = st.progress(0, text="Đang Auto-Test các mô hình Free...")
            total = len(free_models)
            
            for idx, m_id in enumerate(free_models):
                try:
                    # Chạy ping test cực ngắn
                    res = c.chat.completions.create(
                        model=m_id,
                        messages=[{"role": "user", "content": "Hi"}],
                        max_tokens=5,
                        timeout=8
                    )
                    if res.choices and res.choices[0].message.content:
                        working_list.append(m_id)
                except Exception:
                    # Tự động loại bỏ model lỗi/quá tải/hết băng thông
                    pass
                
                if total > 0:
                    progress_bar.progress((idx + 1) / total, text=f"Đang kiểm tra: {m_id}")
            
            progress_bar.empty()
            return working_list

        with st.spinner("🔍 Đang truy vấn OpenRouter & Auto-Test danh sách Model Free..."):
            valid_models = get_free_working_models(api_key.strip())

        if not valid_models:
            st.error("❌ Không tìm thấy mô hình Free nào hoạt động thành công lúc này.")
        else:
            st.sidebar.success(f"✅ Đã lọc xong! Có {len(valid_models)} mô hình FREE KHÔNG LỖI.")
            st.sidebar.write("**Danh sách sẵn sàng:**")
            for m in valid_models:
                st.sidebar.code(m, language="text")

            # ---------------------------------------------------------
            # BƯỚC 2: CHẠY CÂU HỎI TRÊN TOÀN BỘ MODEL KHÔNG LỖI
            # ---------------------------------------------------------
            st.subheader("📌 Gửi câu hỏi đồng loạt tới toàn bộ Model")
            
            user_prompt = st.text_input("Câu hỏi cần kiểm tra:", value="Hôm nay là ngày mấy?")
            
            if st.button("🚀 Chạy trên TOÀN BỘ Model Free không lỗi", type="primary"):
                st.divider()
                st.write(f"Đang gửi câu hỏi **'{user_prompt}'** tới {len(valid_models)} mô hình cùng lúc...")
                
                # Hàm thực thi gửi câu hỏi + Đo thời gian phản hồi (Latency)
                def query_model(model_name):
                    start_time = time.time()
                    try:
                        res = client.chat.completions.create(
                            model=model_name,
                            messages=[{"role": "user", "content": user_prompt}],
                        )
                        elapsed = round(time.time() - start_time, 2)
                        return model_name, res.choices[0].message.content, None, elapsed
                    except Exception as e:
                        elapsed = round(time.time() - start_time, 2)
                        return model_name, None, str(e), elapsed

                # Gửi yêu cầu song song (Multithreading)
                results = []
                with st.spinner("Đang chờ phản hồi từ tất cả các mô hình..."):
                    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                        futures = [executor.submit(query_model, m) for m in valid_models]
                        for future in concurrent.futures.as_completed(futures):
                            results.append(future.result())

                # IN KẾT QUẢ CỦA TOÀN BỘ MODEL
                for m_name, text_res, err, elapsed in results:
                    with st.expander(f"🤖 Model: **{m_name}** — ⏱️ `{elapsed}s`", expanded=True):
                        if text_res:
                            st.markdown(text_res)
                        else:
                            st.error(f"Lỗi phát sinh: {err}")

    except Exception as e:
        st.error(f"❌ Lỗi kết nối OpenRouter API: {e}")
