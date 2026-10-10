# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Streamlit web app ("¿Dónde comemos?") that recommends restaurants from the user's own Google Maps list, mobile-first, deployed on Streamlit Community Cloud. Code, comments, UI text and commit messages are in **Spanish** — keep it that way.

Two independent halves:

1. **Data pipeline** (`obtener_datos/`, run locally now and then) → produces `excels/clasificacion_jev.xlsx` + `imagenes/*.jpg`.
2. **App** (`algoritmo/`) → reads only that excel and those images. `logica.py` (filters, scoring, sort; no Streamlit, no network — unit-tested in `tests/test_logica.py`), `servicios.py` (Nominatim, OSRM, OpenRouteService; no Streamlit), `app.py` (Streamlit UI and custom components).

## Commands

```bash
pip install -r requirements.txt            # app deps only (Streamlit Cloud reads this file)
pip install -r obtener_datos/requirements.txt && python -m playwright install chromium   # pipeline deps
pip install -r requirements-dev.txt && pytest tests/   # AppTest smoke tests + results reference (~40 s, uses network)
streamlit run algoritmo/app.py             # run the app (paths resolve from __file__, any cwd works)

# Data pipeline, in order (each step reads the previous outputs)
python obtener_datos/extraer_html.py --url "<shared list link>"   # downloads the list (Playwright, visible Chrome) -> origen/restaurantes.html -> excels/restaurantes_v1.xlsx + imagenes/
                                                     # without --url it reads the existing origen/restaurantes.html
python obtener_datos/extraer_resenas.py              # Playwright scrape of Google Maps -> excels/restaurantes_v2.xlsx
python obtener_datos/clasificar_restaurantes_jev.py  # v1 + v2 + Jev API -> excels/clasificacion_jev.xlsx
#   flags: --limite N, --hilos N, --reiniciar (drop cache), --verbose, --probar "texto"
```

`tests/test_humo.py` compares 3 fixed searches against `tests/referencia.json`; if you change data or scoring on purpose, regenerate it with `REGENERAR_REFERENCIA=1 pytest tests/test_humo.py`. For new checks, use Streamlit's AppTest (it can't drive the custom JS components; simulate them through `session_state`, e.g. set `ubicacion_actual` instead of using the location button):

```python
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("algoritmo/app.py", default_timeout=180)
at.session_state["ubicacion_actual"] = (40.4227, -3.6993); at.run()
at.button(key="boton_buscar").click().run()
assert not at.exception
```

Secrets: `TYPESAFE_API_KEY` env var (pipeline step 3, paid but cached); `ORS_API_KEY` in `.streamlit/secrets.toml` / Streamlit Cloud secrets (optional; without it walking times fall back to straight-line at 5 km/h).

## Data pipeline gotchas

- **Restaurant `ID` = row position in `restaurantes_v1.xlsx`** (assigned in `clasificar_restaurantes_jev.py`). Reordering or inserting restaurants shifts IDs (fine: IDs only live within one run/session). The Jev cache key (`obtener_datos/.cache/cache_jev.jsonl`) is model + `HUELLA` + review text only — Jev never sees the restaurant — so reordering never re-bills. Never put the ID back in the key.
- Locations/reviews from v2 are joined to v1 **by name** (normalized). Every v1 column flows through to the final excel unchanged, so adding a column in `extraer_html.py` is enough for the app to see it after re-running step 3.
- Google photo URLs (`gps-cs-s`) expire within weeks. `extraer_html.py` downloads each photo once to `imagenes/<slug-of-name>.jpg` (keyed by name, not ID; existing files are skipped) and, if the HTML URL is stale, falls back to opening the place in Google Maps with Playwright to get a fresh one. The app prefers the local file (`Imagen archivo` column) over `Imagen URL`.
- Changing Jev prompts/categories changes `HUELLA` and invalidates the whole cache.

## App architecture (`algoritmo/`)

`app.py` top-to-bottom: config → UI helpers → custom components → `INTERFAZ` (the script body). Keep Streamlit out of `logica.py`/`servicios.py`: the UI computes travel times via `servicios`, passes them to `logica.filtrar_y_puntuar(maestro, df_platos, r, minutos)`, and shows any warning itself.

- **Search flow**: geocode (selected Photon suggestion coords, else Nominatim bounded to Comunidad de Madrid with ", Madrid" appended) → travel times (OSRM for car, OpenRouteService for walking, haversine fallbacks) → `filtrar_y_puntuar` applies **hard filters** (time, cuisine, price overlap, dish) then scores with the `PESO_*` weights → result stored in `st.session_state["resultado"]`. Ordering is done afterwards by `ordenar_resultados`, so changing sort/view/"Ver más" never repeats the search. Never pad results with non-matching restaurants.
- **Two views on one page**: `session_state["vista"]` is `buscador` or `resultados`. The form is **always rendered** and only hidden with CSS (`.st-key-buscador`) in results view — if it weren't rendered, Streamlit would drop the widget values. Errors from a search launched in results view must go through `fallar_busqueda()` so they show in the visible view.
- **Custom components** use `st.components.v2.component`; their HTML/CSS/JS live in `algoritmo/componentes/` (loaded with `recurso("x.js")` into `_HTML_*`, `_CSS_*`, `_JS_*`) plus a small Python wrapper in `app.py`: map (Leaflet + MapLibre/OpenFreeMap, OSM fallback), results list, address autocomplete (Photon, called from the browser), current-location button. Style them with the theme's `var(--st-*)` CSS variables. Components can't read the disk: local photos are sent as base64 (`foto_restaurante`, cached).
- **Detail sheet** is an `st.dialog` with no widgets, opened only on the run right after a tap (`session_state.pop("ficha_abrir")`), so closing it with ✕ doesn't make it reappear.
- **Theme** lives in `.streamlit/config.toml` (light + dark). A few things the theme can't do (sticky search button, entry splash, cover strip) are CSS injected via `st.html` (`componentes/global.css`, `portada.css`, `intro.css`); they depend on Streamlit's internal `data-testid`/`st-key-*` class names and hardcode the light/dark backgrounds via `prefers-color-scheme`.

## Deployment

Streamlit Community Cloud, main file `algoritmo/app.py`; one app per branch (`main` and `v2` are deployed separately). `excels/`, `imagenes/` and `.streamlit/config.toml` must be committed; `.streamlit/secrets.toml` must not.
