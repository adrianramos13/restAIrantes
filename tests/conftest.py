import sys
from pathlib import Path

# Los módulos de la app (logica, servicios...) viven en algoritmo/ y se importan por nombre,
# igual que hace Streamlit al ejecutar algoritmo/app.py.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "algoritmo"))
