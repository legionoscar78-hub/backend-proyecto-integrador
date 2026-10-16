import pandas as pd
from pathlib import Path

# Obtiene la carpeta actual donde está transform.py (.../etl/)
CURRENT_DIR = Path(__file__).resolve().parent

# Sube los niveles necesarios para llegar a donde está tu carpeta 'data' o 'raw'
# Por ejemplo, si 'data' está en la raíz de 'backend':
RAW = CURRENT_DIR.parent / "data" / "raw"

# Si tu carpeta se llama simplemente 'raw' dentro de ml_pipeline, sería:
# RAW = CURRENT_DIR.parent / "raw"

df = pd.read_csv(RAW / "DiseaseAndSymptoms.csv")

# Agregados los paréntesis para ejecutar el método head()
print(df.head())

