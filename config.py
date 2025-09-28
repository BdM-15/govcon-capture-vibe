import os

OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')

# Reason: No need for validation since a default is always set.
# Add other configs as needed