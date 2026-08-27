import streamlit as st
from google import genai

st.set_page_config(page_title="Gemini Model Checker", page_icon="⚡")
st.title("⚡ Kiểm tra Key & Danh sách Model Gemini")

api_key = st.sidebar.text_input("Nhập Gemini API Key (AQ...):", type="password")

if not api_key:
    st.info("💡 Nhập API Key ở thanh bên để quét danh sách mô hình thực tế.", icon="ℹ️")
else:
    try:
        client = genai.Client(api_key=api_key.strip())
        
        # Hàm lấy toàn bộ model khả dụng từ API
        @st.cache_data(show_spinner=False)
        def get_all_supported_models(_key_str):
            c = genai.Client(api_key=_key_str)
            model_list = []
            
            # Lấy tất cả model từ API
            for m in c.models.list():
                # Lấy tên rút gọn (bỏ tiền tố 'models/' nếu có)
                name = m.name.replace("models/", "") if hasattr(m, "name") else str(m)
                
                # Ưu tiên lấy các dòng mô hình text/flash/pro/chat
                if any(k in name for k in ["gemini", "flash", "pro"]):
                    model_list.append(name)
                    
            return model_list

        with st.spinner("Đang truy vấn Google API để lấy danh sách Model..."):
            models = get_all_supported_models(api_key.strip())

        if not models:
            st.warning("⚠️ API trả về danh sách rỗng. Vui lòng kiểm tra lại dự án trên Google AI Studio đã bật Gemini API chưa.")
        else:
            st.sidebar.success(f"Đã tìm thấy {len(models)} mô hình!")
            
            # Dropdown chọn model
            selected_model = st.sidebar.selectbox("Mô hình khả dụng với Key của bạn:", options=models)
            
            st.write(f"👉 Đang kết nối tới: **`{selected_model}`**")
            
            user_prompt = st.text_area("Nhập nội dung cần tra cứu:", height=120)
            
            if st.button("Bắt đầu Tra cứu", type="primary"):
                if user_prompt.strip():
                    with st.spinner("Đang phản hồi..."):
                        response = client.models.generate_content(
                            model=selected_model,
                            contents=user_prompt,
                        )
                        st.subheader("Kết quả:")
                        st.markdown(response.text)
                else:
                    st.warning("Vui lòng nhập nội dung câu hỏi.")
                    
    except Exception as e:
        st.error(f"❌ Lỗi xác thực Key hoặc kết nối API: {e}")
