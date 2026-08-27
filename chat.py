import streamlit as st
from google import genai

st.set_page_config(page_title="Tra cứu Gemini AI", page_icon="🤖")
st.title("🤖 Tra cứu thông tin với Gemini AI")

# Nhập Key ở thanh bên (Hỗ trợ cả Key mới dạng AQ...)
api_key = st.sidebar.text_input("Nhập Gemini API Key:", type="password")

if not api_key:
    st.info("💡 Vui lòng nhập Gemini API Key ở thanh bên để bắt đầu.", icon="ℹ️")
else:
    try:
        # Khởi tạo Client
        client = genai.Client(api_key=api_key.strip())
        
        # Tự động lấy danh sách Model thực tế từ API của bạn
        @st.cache_data(show_spinner=False)
        def get_model_options(_key):
            c = genai.Client(api_key=_key)
            model_names = []
            for m in c.models.list():
                # Lấy thuộc tính name hoặc display_name
                name = getattr(m, 'name', '') or str(m)
                name = name.replace("models/", "")
                if "gemini" in name:
                    model_names.append(name)
            return model_names

        with st.spinner("Đang xác thực API Key..."):
            available_models = get_model_options(api_key.strip())

        # Chọn mô hình mặc định: ưu tiên gemini-3.6-flash, nếu không có thì lấy mô hình đầu tiên trong danh sách
        default_index = 0
        if "gemini-3.6-flash" in available_models:
            default_index = available_models.index("gemini-3.6-flash")
            
        selected_model = st.sidebar.selectbox(
            "Chọn mô hình Gemini:",
            options=available_models if available_models else ["gemini-3.6-flash"],
            index=default_index
        )
        
        st.write(f"Đang sử dụng mô hình: **`{selected_model}`**")
        
        # Giao diện tra cứu
        user_prompt = st.text_area("Nhập nội dung cần tra cứu:", height=120)
        
        if st.button("Gửi câu hỏi", type="primary"):
            if user_prompt.strip():
                with st.spinner(f"Đang xử lý với {selected_model}..."):
                    response = client.models.generate_content(
                        model=selected_model,
                        contents=user_prompt,
                    )
                    st.subheader("Kết quả:")
                    st.markdown(response.text)
            else:
                st.warning("Vui lòng nhập nội dung câu hỏi!")
                
    except Exception as e:
        st.error(f"❌ Đã xảy ra lỗi: {e}")
