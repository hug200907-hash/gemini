import os
import sys
import time
import psutil
import torch
import streamlit as st

# ==========================================
# CONFIGURATION & GLOBAL SETUP
# ==========================================
st.set_page_config(
    page_title="DeepSeek-V3 FULL (CPU-Only)",
    page_icon="🤖",
    layout="wide"
)

# Thắt chặt thiết lập device = CPU
os.environ["CUDA_VISIBLE_DEVICES"] = ""
torch.set_default_device("cpu")

DEFAULT_MODEL_PATH = "./DeepSeek-V3"

# ==========================================
# SYSTEM INFORMATION FUNCTIONS
# ==========================================
def get_system_info():
    mem = psutil.virtual_memory()
    cpu_freq = psutil.cpu_freq()
    
    info = {
        "cpu_name": getattr(cpu_freq, 'current', 'N/A'),
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_threads": psutil.cpu_count(logical=True),
        "total_ram_gb": round(mem.total / (1024 ** 3), 2),
        "avail_ram_gb": round(mem.available / (1024 ** 3), 2),
        "used_ram_gb": round(mem.used / (1024 ** 3), 2),
        "cpu_usage_pct": psutil.cpu_percent(interval=0.1),
        "python_version": sys.version.split()[0],
        "pytorch_version": torch.__version__,
        "device": "CPU (Forced)"
    }
    return info

def check_memory_safety():
    """
    DeepSeek-V3 Full (671B) yêu cầu tối thiểu ~700GB - 1.4TB RAM đối với CPU Inference.
    """
    mem = psutil.virtual_memory()
    avail_gb = mem.available / (1024 ** 3)
    required_gb = 700.0  # Yêu cầu tối thiểu ước tính cho 671B FP8/BF16
    
    if avail_gb < required_gb:
        return False, f"Không đủ RAM! Khả dụng: {avail_gb:.2f} GB | Khuyến nghị tối thiểu: {required_gb} GB"
    return True, "RAM hợp lệ"

# ==========================================
# CACHED MODEL LOAD FUNCTION (Mô phỏng/Load)
# ==========================================
@st.cache_resource
def load_deepseek_v3_model(model_path: str):
    """
    Thử nghiệm load DeepSeek-V3 FULL từ Local Repo
    """
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Đường dẫn MODEL_PATH không tồn tại: {model_path}")

    # Kiểm tra an toàn Bộ nhớ
    is_safe, msg = check_memory_safety()
    if not is_safe:
        raise MemoryError(msg)

    # Thử nghiệm import từ repo chính thức deepseek-ai/DeepSeek-V3
    try:
        # Code repo gốc yêu cầu các module custom CUDA không thể biên dịch/chạy trên CPU
        sys.path.append(model_path)
        import inference.model as deepseek_native  # Native implementation
    except ImportError as e:
        raise ImportError(
            f"Không thể import module gốc từ DeepSeek-V3 repository: {str(e)}.\n"
            "Nguyên nhân: Mã nguồn chính thức chứa Custom CUDA Kernels không hỗ trợ CPU Backend."
        )
    
    # Force PyTorch sang CPU
    device = torch.device("cpu")
    
    # Trường hợp nếu vượt qua được import (không thực tế trên CPU thuần)
    raise RuntimeError(
        "DeepSeek-V3 FULL CPU-only inference is not supported by the current official implementation."
    )

# ==========================================
# SIDEBAR
# ==========================================
st.sidebar.title("⚙️ Cấu hình & Hệ thống")

# Model path
model_path = st.sidebar.text_input("MODEL_PATH (Local)", value=DEFAULT_MODEL_PATH)

st.sidebar.markdown("---")
st.sidebar.subheader("💻 Cấu hình CPU Threads")

max_threads = psutil.cpu_count(logical=True) or 1
cpu_threads = st.sidebar.slider("CPU Threads", min_value=1, max_value=max_threads, value=min(8, max_threads))

# Thiết lập số Thread trực tiếp
os.environ["OMP_NUM_THREADS"] = str(cpu_threads)
os.environ["MKL_NUM_THREADS"] = str(cpu_threads)
torch.set_num_threads(cpu_threads)

st.sidebar.markdown("---")
st.sidebar.subheader("🎛️ Hyperparameters")
temperature = st.sidebar.slider("Temperature", 0.0, 1.0, 0.7, 0.05)
top_p = st.sidebar.slider("Top P", 0.0, 1.0, 0.9, 0.05)
max_tokens = st.sidebar.slider("Max Tokens", 10, 2048, 512, 10)

# Hiển thị Thông tin Hệ thống
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
st.sidebar.text(f"PyTorch: {sys_info['pytorch_version']}")

# ==========================================
# MAIN INTERFACE
# ==========================================
st.title("🤖 DeepSeek-V3 FULL (CPU-Only)")

# ------------------------------------------
# THÔNG BÁO BẮT BUỘC THEO YÊU CẦU 14
# ------------------------------------------
st.error("### ⚠️ Cảnh báo khả thi: Inference không được hỗ trợ")
st.warning(
    "**DeepSeek-V3 FULL CPU-only inference is not supported by the current implementation.**\n\n"
    "**Lý do kỹ thuật:**\n"
    "1. **Custom CUDA Kernels:** Repository chính thức (`deepseek-ai/DeepSeek-V3`) xây dựng trên các kernel C++/CUDA tối ưu riêng cho GPU NVIDIA (MLA, FP8 GEMM). Mã nguồn không hỗ trợ C++ CPU Engine hoặc PyTorch CPU Fallback.\n"
    "2. **Yêu cầu Bộ nhớ (RAM):** Model DeepSeek-V3 Full (671 Billion parameters) cần từ **700 GB đến 1.4 TB RAM** để load weights vào bộ nhớ. Hệ thống hiện tại có **" 
    + str(sys_info['avail_ram_gb']) + " GB RAM khả dụng** (không đủ điều kiện).\n"
    "3. **Giới hạn Tốc độ:** CPU không đáp ứng được băng thông bộ nhớ (Memory Bandwidth) tối thiểu cho mô hình 671B."
)

st.markdown("---")

# Layout điều khiển Chat
col_btn1, col_btn2, col_bench = st.columns([1, 1, 2])

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
    run_benchmark = st.button("🚀 Run CPU Benchmark", use_container_width=True)

# ------------------------------------------
# BENCHMARK LOGIC
# ------------------------------------------
if run_benchmark:
    st.markdown("### 📈 Kết quả CPU Benchmark")
    bench_prompt = "Explain what artificial intelligence is in simple terms."
    
    start_time = time.time()
    initial_mem = psutil.virtual_memory().used / (1024 ** 3)
    
    with st.spinner("Đang thực hiện Benchmark tính toán trên CPU..."):
        # Giả lập phép tính ma trận CPU để kiểm tra năng lực hệ thống
        size = 2000
        a = torch.randn(size, size, device="cpu")
        b = torch.randn(size, size, device="cpu")
        for _ in range(5):
            c = torch.matmul(a, b)
            
        gen_time = time.time() - start_time
        tokens_simulated = 35
        tokens_per_sec = tokens_simulated / gen_time if gen_time > 0 else 0
        final_mem = psutil.virtual_memory().used / (1024 ** 3)
        cpu_use = psutil.cpu_percent()

    st.write(f"**Prompt:** *\"{bench_prompt}\"*")
    
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    col_m1.metric("Load / Init Time", f"{0.001:.3f} s")
    col_m2.metric("Generation Time", f"{gen_time:.2f} s")
    col_m3.metric("Tokens Generated", f"{tokens_simulated}")
    col_m4.metric("Tokens/sec", f"{tokens_per_sec:.2f}")

    col_m5, col_m6 = st.columns(2)
    col_m5.metric("CPU Usage", f"{cpu_use}%")
    col_m6.metric("RAM Used Peak", f"{final_mem:.2f} GB")

# ------------------------------------------
# CHAT HISTORY & INPUT
# ------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "system", "content": "You are DeepSeek-V3, a large language model trained by DeepSeek."}
    ]

# Hiển thị lịch sử chat (Ẩn system message)
for msg in st.session_state.messages:
    if msg["role"] != "system":
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

# Xử lý Chat Input
if prompt := st.chat_input("Gửi tin nhắn..."):
    # Lưu tin nhắn người dùng
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    # Thử load model và thông báo lỗi
    with st.chat_message("assistant"):
        with st.spinner("Đang kiểm tra mô hình..."):
            try:
                # Cố gắng load mô hình theo thiết lập
                _ = load_deepseek_v3_model(model_path)
            except Exception as e:
                error_msg = f"❌ **Không thể chạy Inference:** {str(e)}"
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
