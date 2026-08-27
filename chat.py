import streamlit as st
from google import genai

st.set_page_config(page_title="Gemini Auto-Tester & Chat", page_icon="⚡")
st.title("⚡ Tra cứu Gemini AI (Đã tự động lọc Model chuẩn)")

# Nhập Key ở thanh bên
api_key = st.sidebar.text_input("Nhập Gemini API Key:", type="password")

if not api_key:
    st.info("💡 Vui lòng nhập API Key để ứng dụng bắt đầu Auto Test các mô hình.", icon="ℹ️")
else:
    try:
        client = genai.Client(api_key=api_key.strip())
        
        # Hàm Auto-Test toàn bộ danh sách Model
        @st.cache_data(show_spinner=False)
        def get_working_models(_key_str):
            c = genai.Client(api_key=_key_str)
            all_raw = list(c.models.list())
            
            working_list = []
            progress_bar = st.progress(0, text="Đang Auto-Test danh sách mô hình...")
            total = len(all_raw)
            
            for idx, m in enumerate(all_raw):
                # Lấy tên mô hình
                m_name = getattr(m, 'name', str(m))
                
                # Tiến hành test trực tiếp bằng một câu lệnh siêu ngắn
                try:
                    res = c.models.generate_content(
                        model=m_name,
                        contents="Hi",
                    )
                    if res and res.text:
                        working_list.append(m_name)
                except Exception:
                    # Nếu gặp bất kỳ lỗi nào (404, 403, 400...), tự động bỏ qua model này
                    pass
                
                # Cập nhật thanh tiến trình
                if total > 0:
                    progress_bar.progress((idx + 1) / total, text=f"Đang kiểm tra: {m_name}")
            
            progress_bar.empty()
            return working_list

        with st.spinner("🔍 Đang tiến hành Auto Test để lọc các model hoạt động..."):
            valid_models = get_working_models(api_key.strip())

        if not valid_models:
            st.error("❌ Không tìm thấy mô hình nào hoạt động thành công với API Key này.")
        else:
            st.sidebar.success(f"✅ Auto Test xong! Tìm thấy {len(valid_models)} model hoạt động hoàn hảo.")
            
            # Cho chọn các model đã qua kiểm duyệt
            selected_model = st.sidebar.selectbox(
                "Mô hình khả dụng (Không lỗi):",
                options=valid_models
            )
            
            st.write(f"👉 Mô hình đang dùng: **`{selected_model}`**")
            
            # Giao diện tra cứu
            user_prompt = st.text_area("Nhập câu hỏi / nội dung tra cứu:", height=120)
            
            if st.button("Gửi câu hỏi", type="primary"):
                if user_prompt.strip():
                    with st.spinner("Đang xử lý..."):
                        response = client.models.generate_content(
                            model=selected_model,
                            contents=user_prompt,
                        )
                        st.subheader("Kết quả:")
                        st.markdown(response.text)
                else:
                    st.warning("Vui lòng nhập nội dung câu hỏi!")

    except Exception as e:
        st.error(f"❌ Khởi tạo thất bại: {e}")
