# Viber Desktop MCP Server for Linux

[![MCP](https://img.shields.io/badge/MCP-Model%20Context%20Protocol-blue.svg)](https://modelcontextprotocol.io)
[![Linux](https://img.shields.io/badge/Platform-Linux%20(X11%2FXrdp)-orange.svg)](https://www.linux.org)
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.14-green.svg)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A production-ready **Model Context Protocol (MCP)** server providing reliable, bidirectional automation for **Viber Desktop on Linux**.

Enables AI agents (such as **Hermes Agent**, **Claude Desktop / Claude Code**, and **n8n automation pipelines**) to search contacts, open chats, read conversation history, prepare verified drafts in any language, and send messages with strict operator oversight.

---

## ⚡ Highlights

- **⚡ Zero-OCR Instant Reading**: Reads visible conversation history and composer state directly via **Linux AT-SPI accessibility over D-Bus** in milliseconds, with 100% exact character fidelity.
- **🌐 Full Multilingual & Unicode Support**: Native clipboard injection (`xclip` + `xdotool`) guarantees flawless typing of Cyrillic characters (`ї`, `є`, `ґ`, `І`), emojis, and non-ASCII scripts.
- **📞 Universal Number Addressing**: Switch to any phone number or saved contact instantly using Viber's native protocol launcher (`viber://chat?number=...`).
- **🔒 Race-Condition Safe**: Built-in sequential execution lock (`asyncio.Lock`) ensures safe, serial execution on the single shared desktop GUI.
- **🛡️ Sandboxing & Daemon Compatibility**: Transparently works inside isolated systemd services (e.g. `PrivateTmp=true`) via automated user-session runner delegation.
- **👥 Dynamic Address Book**: Persistent `contacts.json` with fuzzy name/surname/alias lookup and dynamic contact saving (`save_contact`).
- **🛑 Strict Safety Gate**: Draft creation (`put_draft`) is separated from sending (`send_message`), requiring explicit operator confirmation before dispatching.

---

## 🛠️ System Requirements

- **Operating System**: Linux (Debian 12+, Ubuntu 22.04+, Arch, Fedora, etc.)
- **Display Server**: X11 (or XWayland / xrdp virtual display, e.g. `:10`)
- **Viber Desktop**: Official Viber Desktop for Linux (tested on Viber 27.3.x)
- **Python**: `>= 3.11`
- **System Packages**:
  ```bash
  sudo apt-get update && sudo apt-get install -y \
      xclip \
      xdotool \
      x11-utils \
      python3-dbus \
      python3-pil
  ```

---

## 📦 Installation

```bash
git clone https://github.com/vivajarvis777-dev/viber-mcp-linux.git
cd viber-mcp-linux

# Install using uv (recommended)
uv sync

# Or using standard venv + pip
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Copy the example contacts configuration:
```bash
cp contacts.example.json contacts.json
```

---

## ⚙️ Configuration & MCP Client Setup

### 1. Hermes Agent (`~/.hermes/config.yaml`)

Add the server to your Hermes MCP configuration:

```yaml
mcp_servers:
  viber:
    command: /path/to/viber-mcp-linux/.venv/bin/python
    args:
      - /path/to/viber-mcp-linux/server.py
    timeout: 60
    connect_timeout: 15
    env:
      DISPLAY: :10.0
      XDG_SESSION_TYPE: x11
      XDG_RUNTIME_DIR: /run/user/1000
      DBUS_SESSION_BUS_ADDRESS: unix:path=/run/user/1000/bus
      VIBER_LAUNCHER: /path/to/launch-viber
    trust: full
    supports_parallel_tool_calls: false
    tools:
      include:
        - health
        - list_contacts
        - find_contact
        - save_contact
        - open_chat
        - read_open_chat
        - put_draft
        - send_message
```

### 2. Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "viber": {
      "command": "/path/to/viber-mcp-linux/.venv/bin/python",
      "args": [
        "/path/to/viber-mcp-linux/server.py"
      ],
      "env": {
        "DISPLAY": ":0",
        "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus",
        "VIBER_LAUNCHER": "/opt/viber/Viber"
      }
    }
  }
}
```

### 3. n8n Workflow Automation

Configure an **MCP Client Node** in your n8n workflow connecting via stdio to `/path/to/viber-mcp-linux/server.py`. You can trigger automated Viber message drafting or notifications directly from webhooks, CRM updates, or incoming events.

---

## 🧰 Available MCP Tools

| Tool | Mode | Description |
|---|---|---|
| `health()` | Read-only | Returns Viber window visibility, AT-SPI accessibility status, and the currently active contact. |
| `list_contacts()` | Read-only | Returns all known address book contacts and their aliases from `contacts.json`. |
| `find_contact(query)` | Read-only | Search contacts by name, surname, alias, or phone number. Automatically normalizes direct phone numbers. |
| `save_contact(phone, name, aliases)` | Write | Saves or updates contact metadata into `contacts.json` dynamically during runtime. |
| `open_chat(to)` | Action | Opens the conversation for any phone number (`+380...`), contact name, or alias. |
| `read_open_chat(to?)` | Read-only | Reads visible message bubbles from the currently open or specified chat via AT-SPI. |
| `put_draft(to, text)` | Action | Pastes verified text into the chat composer via clipboard and validates it with exact AT-SPI readback. |
| `send_message(to, text, approval_token)` | Destructive | Sends the prepared message after explicit operator approval, clears composer, and verifies delivery in chat history. |

---

## 🏗️ Architecture & How It Works

```mermaid
flowchart TD
    Agent["AI Agent (Hermes / Claude / n8n)"] -->|MCP stdio| Server["server.py (FastMCP)"]
    Server --> Lock["asyncio.Lock (Sequential Safety)"]
    
    subgraph Viber_Linux_Automation ["Viber Desktop Linux Automation"]
        Lock --> Launcher["Launcher (viber://chat?number=...)"]
        Lock --> ATSPI["Direct D-Bus AT-SPI Reader"]
        Lock --> X11Input["X11 Clipboard & xdotool"]
        Lock --> VisualCheck["Dynamic Window Header Verification"]
    end
    
    Launcher -->|IPC| ViberApp["Viber Desktop (Qt / X11)"]
    X11Input -->|Ctrl+V / Return| ViberApp
    ViberApp -->|Accessible Tree| ATSPI
    ViberApp -->|Frame Buffer| VisualCheck
```

### 1. Direct D-Bus Accessibility (No OCR Latency)
Traditional GUI automation relies on screenshots and computer vision OCR, which are slow, error-prone, and cannot distinguish sender from recipient reliably. This MCP server communicates directly with the **AT-SPI D-Bus accessibility registry** (`org.a11y.atspi.Accessible` and `org.a11y.atspi.Text`). It reads chat history in under 50ms with 100% character precision.

### 2. Solving Linux Daemon Isolation (`PrivateTmp=true`)
When running as a background systemd service, agents often have `PrivateTmp=true` enabled. However, Viber Desktop creates its single-application IPC socket in the host's `/tmp/Viber-0-3eb`. This MCP server automatically detects mount namespace isolation and transparently executes the launcher command via `systemd-run --user` inside the user session, switching chats in ~1.2s without hanging.

### 3. Native Conversation Draft Preservation
Viber Desktop stores unsent composer text in memory per conversation. When switching between multiple contacts, drafts are preserved independently without leaking between chats.

---

## 🔒 Security & Safety Best Practices

1. **Human-in-the-Loop Safeguard**: The `send_message` tool requires an `approval_token` (defaulting to `"CONFIRMED"` only after explicit chat confirmation), ensuring the agent never sends unintended messages.
2. **Privacy First**: `contacts.json` and screenshot artifacts (`private/`) are ignored in `.gitignore` by default to prevent leaking personal phone numbers.
3. **Execution Locking**: The global async mutex prevents parallel commands from interleaving during clipboard operations or window switching.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
