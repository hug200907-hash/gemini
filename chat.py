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
    page_title="DeepSeek-R1 Streamlit Cloud Chat",
    page_icon="🤖",
    layout="wide"
)

# Sử dụng Server Inference miễn phí của Hugging Face cho mô hình DeepSeek-R1 Distill
FREE_API_URL = "https://api-inference.huggingface.co/models/deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B"

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
        "device": "Streamlit Cloud Container"
    }

# ==========================================
# SIDEBAR
# ==========================================
st.sidebar.title("⚙️ Cấu hình & Hệ thống")

# Token Hugging Face tùy chọn (Nếu không nhập sẽ dùng Token công cộng)
hf_token = st.sidebar.text_input(
    "Hugging Face Token (Tùy chọn)", 
    type="password",
    help="Dùng token miễn phí từ huggingface.co/settings/tokens để không bị giới hạn số lần gọi."
)

st.sidebar.markdown("---")
st.sidebar.subheader("🎛️ Hyperparameters")
temperature = st.sidebar.slider("Temperature", 0.01, 1.0, 0.7, 0.05)
max_new_tokens = st.sidebar.slider("Max Tokens Output", 64, 2048, 512, 64)

# Thông tin máy chủ Cloud
st.sidebar.markdown("---")
st.sidebar.subheader("📊 Máy chủ Streamlit Cloud")
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
st.title("🤖 DeepSeek-R1 Streamlit Cloud Chat")
st.caption("🚀 Chạy mô hình DeepSeek-R1-Distill-Qwen-1.5B trực tiếp trên Cloud (Miễn phí 100%)")

col_btn1, col_btn2, col_bench = st.columns([1, 1, 2])

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

# Benchmark Button
with col_bench:
    run_benchmark = st.button("🚀 Run Cloud Benchmark", use_container_width=True)

# ------------------------------------------
# BENCHMARK LOGIC
# ------------------------------------------
if run_benchmark:
    st.markdown("### 📈 Kết quả Benchmark API Cloud")
    bench_prompt = "Explain what artificial intelligence is in simple terms."
    
    headers = {}
    if hf_token:
        headers["Authorization"] = f"Bearer {hf_token}"
        
    payload = {
        "inputs": f"<|im_start|>user\n{bench_prompt}<|im_end|>\n<|im_start|>assistant\n",
        "parameters": {
            "max_new_tokens": 50,
            "temperature": temperature,
            "return_full_text": False
        }
    }
    
    start_time = time.time()
    with st.spinner("Đang đo tốc độ xử lý Cloud..."):
        try:
            res = requests.post(FREE_API_URL, headers=headers, json=payload, timeout=30)
            gen_time = time.time() - start_time
            
            if res.status_code == 200:
                result_text = res.json()[0]["generated_text"]
                tokens_est = len(result_text.split()) # Ước tính số token
                tokens_per_sec = tokens_est / gen_time if gen_time > 0 else 0
                
                st.write(f"**Prompt:** *\"{bench_prompt}\"*")
                st.write(f"**Trả lời:** {result_text}")
                
                col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                col_m1.metric("Response Time", f"{gen_time:.2f} s")
                col_m2.metric("Tokens Est.", f"{tokens_est}")
                col_m3.metric("Speed (Tokens/s)", f"{tokens_per_sec:.2f}")
                col_m4.metric("Status", "200 OK")
            else:
                st.error(f"Lỗi Benchmark: HTTP {res.status_code} - {res.text}")
        except Exception as e:
            st.error(f"Lỗi kết nối Benchmark: {str(e)}")

# ------------------------------------------
# CHAT HISTORY DISPLAY
# ------------------------------------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# ------------------------------------------
# CHAT INPUT & GENERATION
# ------------------------------------------
if prompt := st.chat_input("Nhập câu hỏi cho DeepSeek..."):
    # Lưu tin nhắn người dùng
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    # Gửi yêu cầu sinh văn bản
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        message_placeholder.markdown("⏳ *DeepSeek đang suy nghĩ...*")
        
        # Build prompt chuẩn template ChatML cho DeepSeek
        formatted_prompt = ""
        for msg in st.session_state.messages:
            formatted_prompt += f"<|im_start|>{msg['role']}\n{msg['content']}<|im_end|>\n"
        formatted_prompt += "<|im_start|>assistant\n"
        
        headers = {}
        if hf_token:
            headers["Authorization"] = f"Bearer {hf_token}"
            
        payload = {
            "inputs": formatted_prompt,
            "parameters": {
                "max_new_tokens": max_new_tokens,
                "temperature": temperature,
                "return_full_text": False
            },
            "options": {
                "wait_for_model": True # Tự động đợi nếu Model chưa khởi động xong trên Cloud
            }
        }
        
        try:
            response = requests.post(FREE_API_URL, headers=headers, json=payload, timeout=60)
            
            if response.status_code == 200:
                raw_output = response.json()
                if isinstance(raw_output, list) and len(raw_output) > 0:
                    ans_text = raw_output[0].get("generated_text", "")
                else:
                    ans_text = str(raw_output)
                    
                # Làm sạch token thừa nếu có
                ans_text = ans_text.replace("<|im_end|>", "").strip()
                
                message_placeholder.markdown(ans_text)
                st.session_state.messages.append({"role": "assistant", "content": ans_text})
                
            elif response.status_code == 503:
                message_placeholder.error("⚠️ Mô hình đang được nạp vào máy chủ Cloud (Cold Start). Vui lòng đợi 10-15 giây và thử gửi lại tin nhắn!")
            else:
                message_placeholder.error(f"❌ Lỗi API (Status {response.status_code}): {response.text}")
                
        except Exception as e:
            message_placeholder.error(f"❌ Lỗi kết nối: {str(e)}")
