import os

OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')

# Validation
if not OLLAMA_BASE_URL:
    raise ValueError("OLLAMA_BASE_URL must be set in environment or .env file")

# Add other configs as needed