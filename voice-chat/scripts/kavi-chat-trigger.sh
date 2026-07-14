#!/bin/bash
# kavi-chat-trigger.sh - sets the chat trigger flag for Kavi (called by xbindkeys on Menu key)
# Forces chat mode: whatever you say goes straight to the LLM, no need to say "kavi" first.
mkdir -p ~/.cache/kavi
touch ~/.cache/kavi/chat_trigger
