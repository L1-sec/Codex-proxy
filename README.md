# 🚀 Codex Proxy

<div align="center">

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://python.org)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)](https://github.com)
[![Status](https://img.shields.io/badge/status-stable-brightgreen)](https://github.com)

**Run OpenAI Codex CLI for free (or at low cost) using any OpenAI-compatible API**  
*Zero OpenAI API costs. Full Codex CLI experience.*

</div>

---

## 📖 Overview

This proxy server acts as a bridge between [OpenAI Codex CLI](https://github.com/openai/codex) and any OpenAI-compatible API provider (DeepSeek, NVIDIA, Ollama, vLLM, etc.). It transparently converts between Codex's internal API format and standard OpenAI Chat Completions format, allowing you to use free or low-cost models as a drop-in replacement.

**Why this project?**
- 💰 **No OpenAI Costs** — Use free APIs like DeepSeek, NVIDIA, or local models
- 🔄 **Full Compatibility** — Works with Codex CLI without any modifications
- 🌊 **Streaming Support** — Real-time SSE streaming responses
- 🛠️ **Tool Calling** — Full function/tool calling support with automatic format conversion
- 🔌 **Plug & Play** — One-click `.bat` launcher included
- 🎛️ **Multi-Provider** — Switch between DeepSeek, NVIDIA, Ollama, or any OpenAI-compatible endpoint

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🔄 **Protocol Conversion** | Converts Codex internal API ↔ OpenAI Chat Completions format |
| 🌊 **SSE Streaming** | Full Server-Sent Events streaming for real-time responses |
| 🛠️ **Tool Calling** | Automatic conversion of function/tool calls between formats |
| 🔀 **Multi-Route** | Supports `/responses`, `/v1/responses`, `/v1/chat/completions` endpoints |
| 🌐 **CORS Support** | Cross-origin requests enabled by default |
| 📝 **Debug Logging** | Optional debug mode with request logging to `proxy_debug.log` |
| ⚙️ **Flexible Configuration** | Edit the Python file directly — no `.env` file needed |
| 🖥️ **Production Ready** | Uses Waitress WSGI server with configurable thread pool |

---

## 🎯 Supported Providers & Models

The proxy works with any OpenAI-compatible API. Some recommended configurations:

| Provider | Base URL | Recommended Model | Cost |
|----------|----------|-------------------|------|
| **DeepSeek** (via SenseNova) | `https://token.sensenova.cn/v1` | `deepseek-v4-flash` | Free / Low |
| **NVIDIA NIM** | `https://integrate.api.nvidia.com/v1` | `mistralai/mistral-nemotron` | Free |
| **Ollama** (local) | `http://localhost:11434/v1` | `llama3` | Free |
| **vLLM** (self-hosted) | `http://your-server:8000/v1` | `your-model` | Free |
| **OpenRouter** | `https://openrouter.ai/api/v1` | `openai/gpt-4o` | Pay-as-you-go |

> 💡 **Recommendation**: DeepSeek and NVIDIA both offer generous free tiers — perfect for daily coding tasks.

---

## 📋 Prerequisites

- **Python 3.10+** — [Download](https://python.org/downloads/)
- **OpenAI Codex CLI** — [Download from GitHub](https://github.com/openai/codex) (the `codex.exe` binary)
- **API Key** — Sign up at your preferred provider (DeepSeek, NVIDIA, etc.)

---

## 🔧 Installation

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/codex-proxy.git
cd codex-proxy
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Place Codex CLI binary

Download the `codex.exe` (Windows) or `codex` (macOS/Linux) binary from [OpenAI Codex releases](https://github.com/openai/codex) and place it in the project directory.

### 4. Configure your API

Edit `codex_proxy.py` and update the configuration section at the top:

```python
# ===================== 配置 =====================
API_KEY = "your-api-key-here"            # Your API key
MODEL = "deepseek-v4-flash"              # Model name
BASE_URL = "https://token.sensenova.cn/v1"  # API endpoint
HOST = "127.0.0.1"
PORT = 5000
DEBUG = False                            # Set True for debug logs
```

Pre-configured examples are included in the file (just uncomment the provider you want to use).

---

## 🚀 Usage

### One-Click Launch (Windows — Recommended)

Simply double-click `start.bat`, or run:

```bat
start.bat
```

What it does:
1. Opens a new terminal window running the proxy server
2. Waits 0.3 seconds for the server to start
3. Launches Codex CLI (automatically connected through the proxy)

### Manual Launch

#### Step 1: Start the proxy server

```bash
python codex_proxy.py
```

You should see:

```
============================================================
 Codex Proxy 启动中...
============================================================
  Endpoint: http://127.0.0.1:5000
  Model:    deepseek-v4-flash
  Debug:    关闭
  Routes:   /responses, /v1/responses, /v1/chat/completions
============================================================
```

#### Step 2: Configure Codex CLI

Codex CLI needs to be configured to use the proxy. Set the following environment variables or Codex config:

```bash
# The proxy runs at http://127.0.0.1:5000
# Configure Codex to use this as its API endpoint
```

> ⚠️ **Note**: Configuration method may vary by Codex CLI version. The included `start.bat` handles this automatically for Windows.

#### Step 3: Run Codex

```bash
codex
```

---

## 🔧 Configuration Reference

All configuration is in `codex_proxy.py`, in the `# ===================== 配置 =====================` section:

| Variable | Description | Default |
|----------|-------------|---------|
| `API_KEY` | Your provider's API key | *(required)* |
| `MODEL` | Model name to use | `deepseek-v4-flash` |
| `BASE_URL` | OpenAI-compatible API endpoint | `https://token.sensenova.cn/v1` |
| `HOST` | Proxy listen address | `127.0.0.1` |
| `PORT` | Proxy listen port | `5000` |
| `THREADS` | Waitress worker threads | `4` |
| `DEBUG` | Enable debug logging | `False` |

### Switching Providers

Simply edit the `API_KEY`, `MODEL`, and `BASE_URL` values. Common examples:

**NVIDIA (free):**
```python
API_KEY = "nvapi-your-nvidia-key"
MODEL = "mistralai/mistral-nemotron"
BASE_URL = "https://integrate.api.nvidia.com/v1"
```

**Ollama (local, free):**
```python
API_KEY = "ollama"
MODEL = "llama3"
BASE_URL = "http://localhost:11434/v1"
```

**OpenRouter:**
```python
API_KEY = "sk-or-v1-your-key"
MODEL = "openai/gpt-4o"
BASE_URL = "https://openrouter.ai/api/v1"
```

---

## 🏗️ How It Works

```
┌──────────┐     Internal API      ┌─────────────┐     OpenAI API      ┌──────────────┐
│          │ ────────────────────▶  │             │ ─────────────────▶  │              │
│  Codex   │     /responses        │   Proxy     │   /v1/chat/        │  DeepSeek /  │
│  CLI     │     /v1/responses     │   Server    │   completions      │  NVIDIA /    │
│          │ ◀──────────────────── │  (Flask +   │ ◀───────────────── │  Ollama /    │
│          │     SSE Stream        │  Waitress)  │   SSE Stream       │  vLLM ...    │
└──────────┘                       └─────────────┘                    └──────────────┘
  127.0.0.1                         127.0.0.1:5000                    api.provider.com
```

The proxy handles:
- **Message format conversion**: Responses API `input` array → Chat Completions `messages` array
- **Tool/function calling**: Bidirectional conversion between API formats
- **Streaming**: Full SSE event stream with progress events (`response.created`, `response.in_progress`, `response.completed`)
- **Error handling**: Graceful error forwarding with formatted SSE error events

---

## 📝 Debug Mode

Set `DEBUG = True` in `codex_proxy.py` to enable request logging:

- All incoming messages are logged to `proxy_debug.log`
- Tool calls and parameters are recorded
- Useful for troubleshooting API format issues

---

## ❓ FAQ

**Q: Why does Codex need a proxy?**
A: Codex CLI uses a custom API format that isn't directly compatible with standard OpenAI-compatible endpoints. The proxy bridges this gap.

**Q: Is this free to use?**
A: The proxy itself is free and open-source. API costs depend on your chosen provider. DeepSeek and NVIDIA both offer free tiers.

**Q: Can I use it on macOS/Linux?**
A: Yes! Just run `python codex_proxy.py` and launch the Codex CLI binary for your platform.

**Q: How do I get an API key?**
A:
- **DeepSeek (SenseNova)**: Register at [token.sensenova.cn](https://token.sensenova.cn)
- **NVIDIA**: Register at [build.nvidia.com](https://build.nvidia.com) → any model → "Get API Key"
- **Ollama**: No key needed — it's local!

---

## 📄 License

MIT License — see [LICENSE](LICENSE) file for details.

---

<div align="center">

Made with ❤️ for the open-source community

</div>
