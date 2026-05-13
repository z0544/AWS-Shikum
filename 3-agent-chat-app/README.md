# Simple Chat Interface

A Gradio-based chat interface for interacting with your AWS Bedrock agent.

## Usage

1. Install dependencies:
   ```bash
   uv sync
   ```

2. Run the chat interface:
   ```bash
   python simple_chat_gui/chat_gui.py
   ```

3. Open your browser to `http://localhost:8080` to start chatting with your agent.

## Features

- Simple web-based chat interface
- Real-time communication with AWS Bedrock agent
- Clear chat history functionality
- Automatic session ID generation for each conversation

## Configuration

The agent ARN is currently hardcoded in the script. Update the `agent_arn` variable in `chat.py` if you need to connect to a different agent.