import sys
import os

# Aggiunge la cartella orchestrator al path di Python
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "orchestrator")))

from main import app
