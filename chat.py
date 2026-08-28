import os
import sys
import time
import psutil
import torch
import streamlit as st

# Import llama-cpp để chạy file .gguf trên CPU
try:
    from llama_cpp import Llama
    LLAMA_AVAILABLE = True
except ImportError:
    LLAMA_AVAILABLE = False

# ==========================================
# CONFIGURATION & GLOBAL SETUP
# ==========================================
st.set_page_config(
    page_title="DeepSeek GGUF CPU Chat",
    page_icon="🤖",
    layout="wide"
)

# Chỉ định chạy CPU
os.environ["CUDA_VISIBLE_DEVICES"] = ""

DEFAULT_MODEL_PATH = "./DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf"

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
        "pytorch_version": torch.__version__,
        "device": "CPU"
    }

def check_memory_safety(model_path):
    mem = psutil.virtual_memory()
    avail_gb = mem.available / (1024 ** 3)
    
    # Ước tính dung lượng file model để kiểm tra RAM
    if os.path.exists(model_path):
        file_size_gb = os.path.getsize(model_path) / (1024 ** 3)
        required_ram = file_size_gb * 1.5  # Cần dung lượng file + overhead
        if avail_gb < required_ram:
            return False, f"Cảnh báo RAM: Cần ~{required_ram:.2f} GB RAM khả dụng, hiện chỉ có {avail_gb:.2f} GB!"
    return True, "RAM đủ điều kiện"

# ==========================================
# CACHED MODEL LOAD FUNCTION
# ==========================================
@st.cache_resource
def load_gguf_model(model_path: str, n_threads: int, n_ctx: int):
    if not LLAMA_AVAILABLE:
        raise ImportError("Chưa cài đặt 'llama-cpp-python'. Vui lòng chạy: pip install llama-cpp-python")

    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Không tìm thấy file model tại: {model_path}")

    is_safe, msg = check_memory_safety(model_path)
    if not is_safe:
        st.warning(msg)

    # Khởi tạo mô hình Llama C++ chạy hoàn toàn trên CPU
    llm = Llama(
        model_path=model_path,
        n_ctx=n_ctx,
        n_threads=n_threads,
        n_gpu_layers=0,  # Ép buộc 0 GPU layer -> 100% CPU
        verbose=False
    )
    return llm

# ==========================================
# SIDEBAR
# ==========================================
st.sidebar.title("⚙️ Cấu hình Model & CPU")

# Model path
model_path = st.sidebar.text_input("MODEL_PATH (.gguf)", value=DEFAULT_MODEL_PATH)

# Thread CPU
max_threads = psutil.cpu_count(logical=True) or 1
cpu_threads = st.sidebar.slider("CPU Threads", min_value=1, max_value=max_threads, value=min(4, max_threads))

# Thiết lập biến môi trường Threads
os.environ["OMP_NUM_THREADS"] = str(cpu_threads)
os.environ["MKL_NUM_THREADS"] = str(cpu_threads)

st.sidebar.markdown("---")
st.sidebar.subheader("🎛️ Hyperparameters")
n_ctx = st.sidebar.select_slider("Context Size (Tokens)", options=[1024, 2048, 4096, 8192], value=2048)
temperature = st.sidebar.slider("Temperature", 0.0, 1.0, 0.7, 0.05)
top_p = st.sidebar.slider("Top P", 0.0, 1.0, 0.9, 0.05)
max_tokens = st.sidebar.slider("Max Tokens Output", 64, 2048, 512, 64)

# Thông tin hệ thống
st.sidebar.markdown("---")
st.sidebar.subheader("📊 Thông tin Hệ thống")
sys_info = get_system_info()

st.sidebar.text(f"Device: {sys_info['device']}")
st.sidebar.text(f"Physical Cores: {sys_info['physical_cores']}")
st.sidebar.text(f"Logical Threads: {sys_info['logical_threads']}")
st.sidebar.text(f"Total RAM: {sys_info['total_ram_gb']} GB")
st.sidebar.text(f"Available RAM: {sys_info['avail_ram_gb']} GB")
st.sidebar.text(f"Used RAM: {sys_info['used_ram_gb']} GB")
st.sidebar.text(f"CPU Usage: {sys_info['cpu_usage_pct']}%")
st.sidebar.text(f"Python: {sys_info['python_version']}")

# ==========================================
# MAIN INTERFACE
# ==========================================
st.title("🤖 DeepSeek GGUF Local Chat (CPU Only)")

# Quản lý nút bấm
col_btn1, col_btn2, col_bench = st.columns([1, 1, 2])

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "system", "content": "You are a helpful AI assistant."}
    ]

with col_btn1:
    if st.button("New Chat", use_container_width=True):
        st.session_state.messages = [{"role": "system", "content": "You are a helpful AI assistant."}]
        st.rerun()

with col_btn2:
    if st.button("Clear Chat", use_container_width=True):
        st.session_state.messages = [{"role": "system", "content": "You are a helpful AI assistant."}]
        st.rerun()

# Benchmark Button
with col_bench:
    run_benchmark = st.button("🚀 Run CPU Benchmark", use_container_width=True)

# ------------------------------------------
# BENCHMARK LOGIC
# ------------------------------------------
if run_benchmark:
    st.markdown("### 📈 Kết quả CPU Benchmark")
    bench_prompt = "Explain what artificial intelligence is in simple terms."
    
    try:
        start_load = time.time()
        llm_bench = load_gguf_model(model_path, cpu_threads, n_ctx)
        load_time = time.time() - start_load
        
        start_gen = time.time()
        output = llm_bench(
            prompt=f"System: You are a helpful assistant.\nUser: {bench_prompt}\nAssistant:",
            max_tokens=50,
            temperature=temperature,
            top_p=top_p
        )
        gen_time = time.time() - start_gen
        
        tokens_gen = output["usage"]["completion_tokens"]
        tokens_per_sec = tokens_gen / gen_time if gen_time > 0 else 0
        mem_used = psutil.virtual_memory().used / (1024 ** 3)
        cpu_use = psutil.cpu_percent()

        st.write(f"**Prompt:** *\"{bench_prompt}\"*")
        st.write(f"**Kết quả tạo ra:** {output['choices'][0]['text']}")
        
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("Load Time", f"{load_time:.2f} s")
        col_m2.metric("Generation Time", f"{gen_time:.2f} s")
        col_m3.metric("Tokens Generated", f"{tokens_gen}")
        col_m4.metric("Tokens/sec", f"{tokens_per_sec:.2f}")

        col_m5, col_m6 = st.columns(2)
        col_m5.metric("CPU Usage", f"{cpu_use}%")
        col_m6.metric("RAM Used", f"{mem_used:.2f} GB")

    except Exception as e:
        st.error(f"Xảy ra lỗi khi chạy Benchmark: {str(e)}")

# ------------------------------------------
# DISPLAY CHAT HISTORY
# ------------------------------------------
for msg in st.session_state.messages:
    if msg["role"] != "system":
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

# ------------------------------------------
# CHAT INPUT & INFERENCE
# ------------------------------------------
if prompt := st.chat_input("Nhập câu hỏi..."):
    # Hiển thị tin nhắn người dùng
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    # Xử lý sinh câu trả lời bằng Llama-cpp CPU
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        
        try:
            # 1. Load model vào Cache
            llm = load_gguf_model(model_path, cpu_threads, n_ctx)
            
            # 2. Format Prompt chuẩn chat
            formatted_prompt = ""
            for msg in st.session_state.messages:
                if msg["role"] == "system":
                    formatted_prompt += f"System: {msg['content']}\n"
                elif msg["role"] == "user":
                    formatted_prompt += f"User: {msg['content']}\n"
                elif msg["role"] == "assistant":
                    formatted_prompt += f"Assistant: {msg['content']}\n"
            formatted_prompt += "Assistant:"

            # 3. Streaming câu trả lời trực tiếp ra UI
            full_response = ""
            stream = llm(
                prompt=formatted_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                stream=True
            )
            
            for chunk in stream:
                text_chunk = chunk["choices"][0]["text"]
                full_response += text_chunk
                message_placeholder.markdown(full_response + "▌")
                
            message_placeholder.markdown(full_response)
            
            # 4. Lưu câu trả lời vào Session State
            st.session_state.messages.append({"role": "assistant", "content": full_response})

        except Exception as e:
            st.error(f"❌ **Lỗi Inference:** {str(e)}")
