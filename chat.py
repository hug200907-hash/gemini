import streamlit as st
from google import genai

st.set_page_config(page_title="Hỏi đáp Gemini", page_icon="🤖")
st.title("🤖 Tra cứu thông tin với Gemini AI")

# Nhập Key dạng AQ...
api_key = st.sidebar.text_input("Nhập Gemini API Key (AQ...):", type="password")

if not api_key:
    st.info("💡 Vui lòng nhập Gemini API Key ở thanh bên để bắt đầu.", icon="ℹ️")
else:
    try:
        # Khởi tạo client kết nối Gemini API
        client = genai.Client(api_key=api_key.strip())
        
        user_prompt = st.text_area("Nhập nội dung cần tra cứu:", height=120)
        
        if st.button("Tra cứu", type="primary"):
            if user_prompt.strip():
                with st.spinner("Gemini đang xử lý..."):
                    # Cập nhật tên mô hình khả dụng (gemini-1.5-flash)
                    response = client.models.generate_content(
                        model="gemini-1.5-flash",
                        contents=user_prompt,
                    )
                    st.subheader("Kết quả:")
                    st.markdown(response.text)
            else:
                st.warning("Vui lòng nhập câu hỏi!")
    except Exception as e:
        st.error(f"Đã xảy ra lỗi: {e}")
