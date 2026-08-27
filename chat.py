import streamlit as st
from google import genai
import concurrent.futures

st.set_page_config(page_title="Multi-Model Gemini Test", page_icon="🧪", layout="wide")
st.title("🧪 Auto-Test & So sánh phản hồi toàn bộ Model Gemini không lỗi")

api_key = st.sidebar.text_input("Nhập Gemini API Key (AQ...):", type="password")

if not api_key:
    st.info("💡 Nhập API Key ở thanh bên để khởi động hệ thống Auto-Test.", icon="ℹ️")
else:
    try:
        client = genai.Client(api_key=api_key.strip())
        
        # ---------------------------------------------------------
        # BƯỚC 1: LỌC MODEL KHÔNG LỖI (PING TEST)
        # ---------------------------------------------------------
        @st.cache_data(show_spinner=False)
        def get_working_models(_key_str):
            c = genai.Client(api_key=_key_str)
            all_raw = list(c.models.list())
            
            working_list = []
            progress_bar = st.progress(0, text="Đang Auto-Test danh sách mô hình...")
            total = len(all_raw)
            
            for idx, m in enumerate(all_raw):
                m_name = getattr(m, 'name', str(m))
                try:
                    # Gửi tin nhắn test siêu ngắn để lọc lỗi (404, 403,...)
                    res = c.models.generate_content(
                        model=m_name,
                        contents="Hi",
                    )
                    if res and res.text:
                        working_list.append(m_name)
                except Exception:
                    # Tự động bỏ qua các mô hình bị lỗi
                    pass
                
                if total > 0:
                    progress_bar.progress((idx + 1) / total, text=f"Đang kiểm tra: {m_name}")
            
            progress_bar.empty()
            return working_list

        with st.spinner("🔍 Đang chạy Auto-Test để lọc các Model hoạt động..."):
            valid_models = get_working_models(api_key.strip())

        if not valid_models:
            st.error("❌ Không tìm thấy mô hình nào hoạt động thành công với API Key này.")
        else:
            st.sidebar.success(f"✅ Đã lọc xong! Có {len(valid_models)} mô hình KHÔNG LỖI.")
            st.sidebar.write("**Danh sách sẵn sàng:**")
            for m in valid_models:
                st.sidebar.code(m, language="text")

            # ---------------------------------------------------------
            # BƯỚC 2: CHẠY CÂU HỎI TRÊN TOÀN BỘ MODEL KHÔNG LỖI
            # ---------------------------------------------------------
            st.subheader("📌 Gửi câu hỏi đồng loạt tới toàn bộ Model")
            
            # Ô nhập câu hỏi (Mặc định là câu hỏi thời gian)
            user_prompt = st.text_input("Câu hỏi cần kiểm tra:", value="Hôm nay là ngày mấy?")
            
            if st.button("🚀 Chạy trên TOÀN BỘ Model không lỗi", type="primary"):
                st.divider()
                st.write(f"Đang gửi câu hỏi **'{user_prompt}'** tới {len(valid_models)} mô hình cùng lúc...")
                
                # Hàm trợ giúp gọi API cho từng model
                def query_model(model_name):
                    try:
                        res = client.models.generate_content(
                            model=model_name,
                            contents=user_prompt,
                        )
                        return model_name, res.text, None
                    except Exception as e:
                        return model_name, None, str(e)

                # Chạy song song (Multithreading) để lấy kết quả nhanh nhất
                results = []
                with st.spinner("Đang chờ phản hồi từ tất cả các mô hình..."):
                    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                        futures = [executor.submit(query_model, m) for m in valid_models]
                        for future in concurrent.futures.as_completed(futures):
                            results.append(future.result())

                # IN KẾT QUẢ CỦA TOÀN BỘ MODEL
                for m_name, text_res, err in results:
                    with st.expander(f"🤖 Model: **{m_name}**", expanded=True):
                        if text_res:
                            st.markdown(text_res)
                        else:
                            st.error(f"Lỗi phát sinh: {err}")

    except Exception as e:
        st.error(f"❌ Lỗi khởi tạo hệ thống: {e}")
