import os
import sys
import time
import psutil
import requests
import streamlit as st

# ==========================================
# CONFIGURATION & GLOBAL SETUP
# ==========================================
st.set_page_config(
    page_title="DeepSeek Local/Cloud Chat",
    page_icon="🤖",
    layout="wide"
)

# Cấu hình Mặc định (Có thể dùng Ollama Server Local hoặc Cloud API)
DEFAULT_API_URL = st.sidebar.text_input("Ollama / API Endpoint", value="http://localhost:11434/api/generate")
DEFAULT_MODEL_NAME = st.sidebar.text_input("Model Name", value="deepseek-r1:1.5b")

# ==========================================
# SYSTEM INFORMATION FUNCTIONS
# ==========================================
def get_system_info():
    mem = psutil.virtual_memory()
    return {
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_threads": psutil.cpu_count(logical=True),
        "total_ram_gb": round(mem.total / (1024 ** 3), 2),
        "avail_ram_gb": round(mem.available / (1024 ** 3), 2),
        "used_ram_gb": round(mem.used / (1024 ** 3), 2),
        "cpu_usage_pct": psutil.cpu_percent(interval=0.1),
        "python_version": sys.version.split()[0],
        "device": "Cloud/CPU Mode"
    }

# ==========================================
# SIDEBAR
# ==========================================
st.sidebar.title("⚙️ Cấu hình Model & Server")

st.sidebar.markdown("---")
st.sidebar.subheader("🎛️ Hyperparameters")
temperature = st.sidebar.slider("Temperature", 0.0, 1.0, 0.7, 0.05)
top_p = st.sidebar.slider("Top P", 0.0, 1.0, 0.9, 0.05)

# Thông tin hệ thống
st.sidebar.markdown("---")
st.sidebar.subheader("📊 Thông tin Máy chủ Streamlit")
sys_info = get_system_info()

st.sidebar.text(f"Device: {sys_info['device']}")
st.sidebar.text(f"Logical Threads: {sys_info['logical_threads']}")
st.sidebar.text(f"Total RAM: {sys_info['total_ram_gb']} GB")
st.sidebar.text(f"Available RAM: {sys_info['avail_ram_gb']} GB")
st.sidebar.text(f"CPU Usage: {sys_info['cpu_usage_pct']}%")
st.sidebar.text(f"Python: {sys_info['python_version']}")

# ==========================================
# MAIN INTERFACE
# ==========================================
st.title("🤖 DeepSeek Streamlit Cloud Chat")

col_btn1, col_btn2 = st.columns([1, 1])

if "messages" not in st.session_state:
    st.session_state.messages = []

with col_btn1:
    if st.button("New Chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

with col_btn2:
    if st.button("Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# Display Chat History
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# User Input
if prompt := st.chat_input("Nhập câu hỏi..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        
        # Payload gửi tới API Backend
        payload = {
            "model": DEFAULT_MODEL_NAME,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": temperature,
                "top_p": top_p
            }
        }
        
        try:
            response = requests.post(DEFAULT_API_URL, json=payload, stream=True, timeout=30)
            
            if response.status_code == 200:
                full_response = ""
                for line in response.iter_lines():
                    if line:
                        import json
                        chunk = json.loads(line.decode('utf-8'))
                        text_chunk = chunk.get("response", "")
                        full_response += text_chunk
                        message_placeholder.markdown(full_response + "▌")
                message_placeholder.markdown(full_response)
                st.session_state.messages.append({"role": "assistant", "content": full_response})
            else:
                st.error(f"❌ Kết nối API thất bại (Status code: {response.status_code}). Kiểm tra lại Endpoint trên Sidebar.")
                
        except Exception as e:
            st.error(f"❌ Không thể kết nối tới Server AI: {str(e)}\n\n*Gợi ý:* Nếu chạy trên Streamlit Cloud, bạn cần nhập URL API Public (như Ngrok hoặc Ollama Cloud URL) vào ô Endpoint bên Sidebar.")
