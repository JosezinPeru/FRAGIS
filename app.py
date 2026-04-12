import pandas as pd
from flask import Flask

app = Flask(__name__)

df = pd.read_excel("MASTERv1f.xlsx", sheet_name="TABLA1")

@app.route('/')
def index():
    total = len(df)
    columnas = list(df.columns)
    primera = df.iloc[0].to_dict()
    
    return f"""
    <h1>FRAGIS Proof of Concept</h1>
    <p>✅ Excel cargado correctamente</p>
    <p>📦 Total de instrumentos: <b>{total}</b></p>
    <p>📋 Columnas encontradas: <b>{columnas}</b></p>
    <hr>
    <p>Primer instrumento del Excel:</p>
    <pre>{primera}</pre>
    """

if __name__ == '__main__':
    app.run(debug=True)