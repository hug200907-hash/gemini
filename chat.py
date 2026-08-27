import streamlit as st
from google import genai

st.set_page_config(page_title="Gemini Debugger", page_icon="🛠️")
st.title("🛠️ Kiểm tra mô hình Gemini thực tế")

api_key = st.sidebar.text_input("Nhập API Key:", type="password")

if not api_key:
    st.info("Nhập API Key vào thanh bên để kiểm tra.")
else:
    try:
        client = genai.Client(api_key=api_key.strip())
        
        # 1. LẤY DANH SÁCH MÔ HÌNH THỰC TẾ
        st.subheader("1. Danh sách Model khả dụng từ Key của bạn:")
        raw_models = list(client.models.list())
        
        # Hiển thị tất cả tên model tìm thấy
        model_names = []
        for m in raw_models:
            # Lấy trường name của model
            m_name = getattr(m, 'name', str(m))
            model_names.append(m_name)
            
        st.json(model_names)
        
        # 2. CHỌN VÀ THỬ CHẠY
        st.subheader("2. Thử nghiệm gửi câu hỏi:")
        
        selected_model = st.selectbox("Chọn tên model từ danh sách trên:", options=model_names)
        user_prompt = st.text_input("Câu hỏi test:", value="Xin chào, bạn là mô hình nào?")
        
        if st.button("Chạy thử", type="primary"):
            with st.spinner("Đang gọi API..."):
                response = client.models.generate_content(
                    model=selected_model,
                    contents=user_prompt,
                )
                st.success("Thành công! Kết quả trả về:")
                st.write(response.text)
                
    except Exception as e:
        st.error(f"Lỗi: {e}")
