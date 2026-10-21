# Estudiar Sistemas Operativos

Aplicación web local para memorizar el contenido de **«Sistemas Operativos.pdf»** con preguntas, tarjetas de memoria, exámenes y repasos espaciados.

- Backend: Python + FastAPI · Plantillas: Jinja2 · Frontend: HTML, CSS y JavaScript nativo
- Progreso: SQLite (`data/progreso.db`, se crea solo al primer uso)
- Preguntas: `data/questions.json` (166 preguntas en 10 unidades, generadas solo a partir del PDF)

## Instalación y ejecución (Ubuntu)

Desde la carpeta `prueba`:

```bash
# 1. Crear el entorno virtual
python3 -m venv .venv
```

> Si Ubuntu responde que falta `ensurepip`, hay dos opciones:
> instalar el paquete del sistema (`sudo apt install python3.12-venv`) y repetir el paso 1, **o**
> crear el entorno sin tocar el sistema:
> ```bash
> python3 -m venv --without-pip .venv
> curl -sSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
> .venv/bin/python /tmp/get-pip.py
> ```

```bash
# 2. Activarlo
source .venv/bin/activate

# 3. Instalar las dependencias
pip install -r requirements.txt

# 4. Iniciar FastAPI con Uvicorn
uvicorn app.main:app --reload

# 5. Abrir la aplicación en el navegador
xdg-open http://127.0.0.1:8000

# 6. Ejecutar las pruebas (en otra terminal, con el entorno activado)
pytest
```

Para detener el servidor: `Ctrl+C`.

## Cómo se usa

| Pantalla | Qué hace |
|---|---|
| **Inicio** (`/`) | Unidades y temas, cantidad de preguntas, progreso general y pendientes de repaso. |
| **Estudiar** (`/estudiar`) | Elegís una unidad; ves una pregunta, escribís tu respuesta, la revelás (con la página del PDF) y te autoevaluás: *No la recordé*, *Parcialmente* o *La recordé bien*. |
| **Tarjetas** (`/tarjetas`) | Frente con la pregunta, reverso con la respuesta, mismas tres opciones. |
| **Examen** (`/examen`) | Preguntas aleatorias de las unidades elegidas. Las respuestas se muestran solo al terminar; corregís cada una, ves la puntuación, el resultado por unidad y los temas a repasar. |
| **Repaso** (`/repaso`) | Solo las preguntas cuya fecha de repaso llegó (falladas, parciales o vencidas). |
| **Progreso** (`/progreso`) | Estado por unidad, preguntas que más te cuestan e historial de exámenes. |

### Repetición espaciada

- **No la recordé** → vuelve en la próxima sesión (queda pendiente hoy mismo y se repite una vez al final de la sesión actual).
- **Parcialmente** → repaso mañana.
- **La recordé bien** → el intervalo crece: 1, 3, 7, 14, 30 y 60 días.
- Una pregunta queda **dominada** después de 2 aciertos seguidos.
- En el examen, *bien* = 1 punto, *parcial* = 0,5 y *no* = 0; el resultado también actualiza los repasos.

## Estructura

```
prueba/
├── app/
│   ├── main.py          # rutas HTML y API JSON
│   ├── database.py      # conexión y tablas SQLite
│   ├── models.py        # validación de peticiones (Pydantic)
│   ├── study.py         # banco de preguntas, repetición espaciada, estadísticas, exámenes
│   ├── templates/       # base, index, study, flashcards, exam, progress
│   └── static/          # css/style.css, js/app.js
├── data/
│   ├── questions.json   # banco de preguntas
│   └── progreso.db      # tu progreso (se crea automáticamente)
├── tests/               # pruebas con pytest
├── tools/extraer_pdf.py # vuelca el texto del PDF por página
├── requirements.txt
└── README.md
```

### API JSON

| Método y ruta | Uso |
|---|---|
| `GET /api/units` | Unidades con estadísticas |
| `GET /api/questions?unit_id=u4` | Preguntas de una unidad, en orden de estudio |
| `GET /api/review` | Preguntas pendientes de repaso |
| `GET /api/flashcards?unit_id=u4` | Tarjetas (frente/reverso) |
| `POST /api/answers` | Registra una autoevaluación `{question_id, result, user_answer, mode}` |
| `POST /api/exams` | Crea un examen `{unit_ids, count}` (sin respuestas) |
| `POST /api/exams/{id}/finish` | Entrega las respuestas escritas y devuelve las correctas |
| `POST /api/exams/{id}/grade` | Guarda la corrección y devuelve la puntuación |
| `GET /api/stats` | Estadísticas generales |

## Sobre el contenido del PDF

- Las 37 páginas tienen texto extraíble; no hay páginas escaneadas.
- Algunas partes están **solo en imágenes** (infografías de las págs. 1 y 17, árbol histórico de la pág. 4, diagramas de las págs. 11, 18–20, 25, 27 y 37). Se revisaron visualmente; las preguntas basadas en ellas aparecen marcadas como «contenido de un diagrama».
- En la pág. 32 el título «Arquitectura simplificada» no tiene contenido debajo en el PDF.

## Reiniciar el progreso

Borrá `data/progreso.db` con el servidor detenido. Las pruebas usan una base temporal y nunca tocan tu progreso.
