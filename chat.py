import streamlit as st
from google import genai

st.set_page_config(page_title="Hỏi đáp cùng Gemini", page_icon="🤖")
st.title("🤖 Tra cứu thông tin với Gemini AI")

# Cho phép người dùng nhập API Key (lấy miễn phí tại aistudio.google.com)
api_key = st.sidebar.text_input("Nhập Gemini API Key của bạn:", type="password")

if not api_key:
    st.info("💡 Vui lòng nhập Gemini API Key ở thanh bên để bắt đầu.", icon="ℹ️")
else:
    try:
        # Khởi tạo client Gemini
        client = genai.Client(api_key=api_key)
        
        # Ô nhập câu hỏi
        user_prompt = st.text_area("Nhập nội dung cần tra cứu:", height=100)
        
        if st.button("Gửi câu hỏi", type="primary"):
            if user_prompt.strip() != "":
                with st.spinner("Gemini đang suy nghĩ..."):
                    # Gọi mô hình gemini-2.5-flash
                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=user_prompt,
                    )
                    st.subheader("Kế quả:")
                    st.write(response.text)
            else:
                st.warning("Vui lòng nhập nội dung câu hỏi!")
    except Exception as e:
        st.error(f"Đã xảy ra lỗi: {e}")
