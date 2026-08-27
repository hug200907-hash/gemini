import streamlit as st
from google import genai

st.set_page_config(page_title="Gemini Model Checker & Chat", page_icon="🔍")
st.title("🔍 Trình kiểm tra Key & Tra cứu Gemini")

# Nhập API Key ở thanh bên
api_key = st.sidebar.text_input("Nhập Gemini API Key:", type="password")

if not api_key:
    st.info("💡 Vui lòng nhập API Key để ứng dụng quét danh sách Model hỗ trợ.", icon="ℹ️")
else:
    try:
        # Khởi tạo Client với Key của bạn
        client = genai.Client(api_key=api_key.strip())
        
        # Lấy danh sách mô hình thực tế mà Key hỗ trợ
        @st.cache_data(show_spinner=False)
        def fetch_models(_key_str):
            # Tạo temp client để tránh lỗi cache
            c = genai.Client(api_key=_key_str)
            all_models = list(c.models.list())
            # Lọc ra các mô hình hỗ trợ sinh nội dung (generateContent)
            available = [
                m.name.replace("models/", "") 
                for m in all_models 
                if "generateContent" in getattr(m, "supported_generation_methods", [])
            ]
            return available

        with st.spinner("Đang xác thực Key và tải danh sách Model..."):
            available_models = fetch_models(api_key.strip())

        if not available_models:
            st.error("Key hợp lệ nhưng không tìm thấy mô hình generateContent nào khả dụng.")
        else:
            st.sidebar.success(f"Key hợp lệ! Tìm thấy {len(available_models)} mô hình.")
            
            # Cho người dùng chọn mô hình từ danh sách thực tế trả về
            selected_model = st.sidebar.selectbox(
                "Chọn mô hình khả dụng:",
                options=available_models
            )
            
            st.write(f"Đang sử dụng mô hình: **`{selected_model}`**")
            
            # Giao diện tra cứu
            user_prompt = st.text_area("Nhập nội dung cần tra cứu / đặt câu hỏi:", height=120)
            
            if st.button("Gửi câu hỏi", type="primary"):
                if user_prompt.strip():
                    with st.spinner(f"Đang xử lý bằng {selected_model}..."):
                        response = client.models.generate_content(
                            model=selected_model,
                            contents=user_prompt,
                        )
                        st.subheader("Kết quả:")
                        st.markdown(response.text)
                else:
                    st.warning("Vui lòng nhập nội dung câu hỏi!")

    except Exception as e:
        st.error(f"❌ Key không hợp lệ hoặc lỗi kết nối: {e}")
