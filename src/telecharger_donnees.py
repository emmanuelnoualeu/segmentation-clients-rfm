"""Télécharge le jeu public « Online Retail » (UCI, miroir GitHub) dans data/.

    python src/telecharger_donnees.py
"""
from pathlib import Path
from urllib.request import urlretrieve

URL = ("https://raw.githubusercontent.com/databricks/Spark-The-Definitive-Guide/"
       "master/data/retail-data/all/online-retail-dataset.csv")
CIBLE = Path(__file__).resolve().parents[1] / "data" / "online_retail.csv"

if __name__ == "__main__":
    CIBLE.parent.mkdir(exist_ok=True)
    if not CIBLE.exists():
        print("Téléchargement (45 Mo)…")
        urlretrieve(URL, CIBLE)
    print(f"Données disponibles : {CIBLE}")
