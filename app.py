import os
import time
import anthropic
import pandas as pd
from flask import Flask, request, jsonify, render_template_string, Response, stream_with_context
import json

app = Flask(__name__)
VERSION = "2.1.0"

df = pd.read_excel("MASTERv1f.xlsx", sheet_name="TABLA1")

client = anthropic.Anthropic(api_key="ANTHROPIC_API_KEY")

REGLAS = """
Eres un sistema experto en codificación de instrumental quirúrgico.
Recibirás un subset filtrado de instrumentos y una query del cliente.
Debes devolver ÚNICAMENTE el CODIGO del instrumento que mejor hace match.
Si no hay match con suficiente confianza, responde: NO MATCH

REGLAS:
1) Ignorar numerales de cantidad como "UNA (01)" o "DOS (02)"
2) Convertir medidas de cm a mm para comparar
3) Si no hay medida exacta, buscar en ±5mm e indicarlo
4) En SONDAS no tomar la "abotonada" salvo que se solicite
5) Pinza anatómica = sin diente, con estrías (aparece "de sierra")
6) Pinza quirúrgica = con diente (aparece "1 x 2 dientes")
7) Si no especifica tipo de pinza, asumir anatómica
8) Si hay dos medidas iguales, preferir "estándar" sobre "mediana"
9) DUROTIP : NUNCA ofrecer salvo que el cliente escriba literalmente "durotip" o "filo endurecido" o "carburo de tungsteno". Si hay opción estándar disponible, SIEMPRE preferir la estándar.
10) DUROGRIP : NUNCA ofrecer salvo que el cliente escriba literalmente "durogrip" o "boca endurecida" o "carburo de tungsteno". Si hay opción estándar disponible, SIEMPRE preferir la estándar.
11) NOIR/ATRAUMATA: solo si el cliente lo pide
12) Si piden semicurvo, ofrecer curvo
13) RCT=recta, CRV=curva, ATR=atraumática
14) Porta esponja: preferir "boca de sierra" si no se especifica
15) Murphy = Gross = Duplay
16) Si no hay nombre específico, preferir el genérico
17) BABY: buscar "BABY" o "FINO". No ofrecer BABY si no se solicita

Responde en este formato exacto:
CODIGO: [el codigo]
CONFIANZA: [Alta/Media/Baja]
RAZON: [explicacion breve en español]
"""

HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>FRAG-IS : Codificador de Instrumental</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; }
        h1 { color: #1F4E79; }
        textarea { width: 100%; height: 150px; padding: 10px; font-size: 14px; border: 1px solid #ccc; border-radius: 6px; }
        button { background: #1F4E79; color: white; padding: 12px 30px; border: none; border-radius: 6px; font-size: 15px; cursor: pointer; margin-top: 10px; }
        button:hover { background: #2E75B6; }
        button:disabled { opacity: 0.5; cursor: default; }
        #results { margin-top: 20px; }
        .result-row { background: #f5f5f5; padding: 12px; margin: 8px 0; border-radius: 6px; border-left: 4px solid #1F4E79; }
        .codigo { font-weight: bold; color: #1F4E79; font-size: 16px; }
        .no-match { border-left-color: #cc0000; }
        .no-match .codigo { color: #cc0000; }
        .procesando { background: #fff9e6; padding: 12px; margin: 8px 0; border-radius: 6px; border-left: 4px solid #f0a500; color: #888; font-style: italic; font-size: 13px; }
    </style>
</head>
<body>
    <h1>FRAG-IS : Codificador de Instrumental</h1>
    <p style="color:#888; font-size:12px; margin-top:-15px;">v{{ version }}</p>
    <p>Pega la lista de instrumentos (uno por línea) y presiona Codificar.</p>
    <textarea id="queries" placeholder="tijera de mayo curva 14cm&#10;pinza kocher recta 18cm&#10;porta agujas mayo hegar 20cm"></textarea>
    <br>
    <button id="btn" onclick="codificar()">Codificar instrumentos</button>
    <div id="results"></div>

    <script>
        async function codificar() {
            const texto = document.getElementById('queries').value.trim();
            if (!texto) return;
            const queries = texto.split('\\n').filter(q => q.trim());
            const btn = document.getElementById('btn');
            const div = document.getElementById('results');

            btn.disabled = true;
            btn.textContent = 'Procesando...';
            div.innerHTML = '';

            const response = await fetch('/codificar', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ queries: queries })
            });

            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const text = decoder.decode(value);
                const lines = text.split('\\n').filter(l => l.trim());

                for (const line of lines) {
                    try {
                        const data = JSON.parse(line);

                        if (data.tipo === 'procesando') {
                            const queryCapitalizado = data.query.charAt(0).toUpperCase() + data.query.slice(1);
                            div.innerHTML += `<div class="procesando" id="proc_${data.id}">⏳ Procesando ${data.id} = ${queryCapitalizado}...</div>`;
                        }

                        if (data.tipo === 'resultado') {
                            const noMatch = data.codigo === 'NO MATCH';
                            const queryCapitalizado = data.query.charAt(0).toUpperCase() + data.query.slice(1);
                            const procEl = document.getElementById('proc_' + data.id);
                            if (procEl) procEl.remove();
                            div.innerHTML += `
                                <div class="result-row ${noMatch ? 'no-match' : ''}">
                                    <div style="font-size:14px; margin-bottom:4px;">${data.id} = ${queryCapitalizado} = <span class="codigo">${data.codigo}</span></div>
                                    <div style="font-size:12px; color:#888;">(${data.razon} · ${data.confianza})</div>
                                </div>`;
                        }
                    } catch(e) {}
                }
            }

            btn.disabled = false;
            btn.textContent = 'Codificar instrumentos';
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML, version=VERSION)


@app.route('/codificar', methods=['POST'])
def codificar():
    data = request.json
    queries = data.get('queries', [])

    def generar():
        for i, query in enumerate(queries, 1):
            yield json.dumps({"tipo": "procesando", "id": i, "query": query}) + "\n"

            try:
                # Hard filter
                query_upper = query.upper()
                subset = df.copy()
                for categoria in sorted(df['SEARCH-SPACE'].unique(), key=len, reverse=True):
                    palabras = [p.strip() for p in str(categoria).upper().split(',')]
                    if any(palabra in query_upper for palabra in palabras):
                        subset = df[df['SEARCH-SPACE'] == categoria]
                        break

                subset_texto = '\n'.join(
                    f"{row['DESCRIPCION FULL']}|{row['CODIGO']}"
                    for _, row in subset.iterrows()
                )

                mensaje = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=300,
                    system=[
                        {
                            "type": "text",
                            "text": f"SUBSET DE INSTRUMENTAL QUIRURGICO:\n{subset_texto}",
                            "cache_control": {"type": "ephemeral"}
                        },
                        {
                            "type": "text",
                            "text": REGLAS
                        }
                    ],
                    messages=[{
                        "role": "user",
                        "content": f"QUERY DEL CLIENTE: {query}"
                    }]
                )

                respuesta = mensaje.content[0].text

                codigo = "NO MATCH"
                confianza = ""
                razon = ""

                for linea in respuesta.split('\n'):
                    if linea.startswith('CODIGO:'):
                        codigo = linea.replace('CODIGO:', '').strip()
                    elif linea.startswith('CONFIANZA:'):
                        confianza = linea.replace('CONFIANZA:', '').strip()
                    elif linea.startswith('RAZON:'):
                        razon = linea.replace('RAZON:', '').strip()

                yield json.dumps({
                    "tipo": "resultado",
                    "id": i,
                    "query": query,
                    "codigo": codigo,
                    "confianza": confianza,
                    "razon": razon
                }) + "\n"

                if i < len(queries):
                    pausa = max(5, int(len(subset) * 15 / 50000 * 60) + 5)
                    time.sleep(pausa)

            except Exception as e:
                yield json.dumps({
                    "tipo": "resultado",
                    "id": i,
                    "query": query,
                    "codigo": "ERROR",
                    "confianza": "",
                    "razon": str(e)
                }) + "\n"

    return Response(stream_with_context(generar()), mimetype='text/plain')

if __name__ == '__main__':
    app.run(debug=True)
