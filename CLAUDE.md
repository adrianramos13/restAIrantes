# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Streamlit web app ("¿Dónde comemos?") that recommends restaurants from the user's own Google Maps list, mobile-first, deployed on Streamlit Community Cloud. Code, comments, UI text and commit messages are in **Spanish** — keep it that way.

Two independent halves:

1. **Data pipeline** (`obtener_datos/`, run locally now and then) → produces `excels/clasificacion_jev.xlsx` + `imagenes/*.jpg`.
2. **App** (`algoritmo/app.py`, a single file) → reads only that excel and those images.

## Commands

```bash
pip install -r requirements.txt            # app deps (Streamlit Cloud reads this file)
streamlit run algoritmo/app.py             # run the app (paths resolve from __file__, any cwd works)

# Data pipeline, in order (each step reads the previous outputs)
python obtener_datos/extraer_html.py                 # origen/restaurantes.html -> excels/restaurantes_v1.xlsx + imagenes/
python obtener_datos/extraer_resenas.py              # Playwright scrape of Google Maps -> excels/restaurantes_v2.xlsx
python obtener_datos/clasificar_restaurantes_jev.py  # v1 + v2 + Jev API -> excels/clasificacion_jev.xlsx
#   flags: --limite N, --hilos N, --reiniciar (drop cache), --verbose, --probar "texto"
```

There is no test suite. Verify app changes with Streamlit's AppTest (it can't drive the custom JS components; simulate them through `session_state`, e.g. set `ubicacion_actual` instead of using the location button):

```python
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("algoritmo/app.py", default_timeout=180)
at.session_state["ubicacion_actual"] = (40.4227, -3.6993); at.run()
at.button(key="boton_buscar").click().run()
assert not at.exception
```

Secrets: `TYPESAFE_API_KEY` env var (pipeline step 3, paid but cached); `ORS_API_KEY` in `.streamlit/secrets.toml` / Streamlit Cloud secrets (optional; without it walking times fall back to straight-line at 5 km/h).

Note: the README still describes step 2 as using Outscraper; the code now scrapes with Playwright and writes `restaurantes_v2.xlsx`, which is what step 3 reads.

## Data pipeline gotchas

- **Restaurant `ID` = row position in `restaurantes_v1.xlsx`** (assigned in `clasificar_restaurantes_jev.py`). Reordering or inserting restaurants shifts IDs. The Jev cache key (`obtener_datos/.cache/cache_jev.jsonl`) includes that ID, so a reorder re-bills reviews.
- Locations/reviews from v2 are joined to v1 **by name** (normalized). Every v1 column flows through to the final excel unchanged, so adding a column in `extraer_html.py` is enough for the app to see it after re-running step 3.
- Google photo URLs (`gps-cs-s`) expire within weeks. `extraer_html.py` downloads each photo once to `imagenes/<slug-of-name>.jpg` (keyed by name, not ID; existing files are skipped) and, if the HTML URL is stale, falls back to opening the place in Google Maps with Playwright to get a fresh one. The app prefers the local file (`Imagen archivo` column) over `Imagen URL`.
- Changing Jev prompts/categories changes `HUELLA` and invalidates the whole cache.

## App architecture (`algoritmo/app.py`)

Top-to-bottom: config constants → scoring/filtering → travel times → UI helpers → custom components → `INTERFAZ` (the script body).

- **Search flow**: geocode (selected Photon suggestion coords, else Nominatim bounded to Comunidad de Madrid with ", Madrid" appended) → travel times (OSRM for car, OpenRouteService for walking, haversine fallbacks) → `filtrar_y_puntuar` applies **hard filters** (time, cuisine, price overlap, dish) then scores with the `PESO_*` weights → result stored in `st.session_state["resultado"]`. Ordering is done afterwards by `ordenar_resultados`, so changing sort/view/"Ver más" never repeats the search. Never pad results with non-matching restaurants.
- **Two views on one page**: `session_state["vista"]` is `buscador` or `resultados`. The form is **always rendered** and only hidden with CSS (`.st-key-buscador`) in results view — if it weren't rendered, Streamlit would drop the widget values. Errors from a search launched in results view must go through `fallar_busqueda()` so they show in the visible view.
- **Custom components** use `st.components.v2.component` with `_HTML_*`, `_CSS_*`, `_JS_*` string constants plus a small Python wrapper: map (Leaflet + MapLibre/OpenFreeMap, OSM fallback), results list, address autocomplete (Photon, called from the browser), current-location button. Style them with the theme's `var(--st-*)` CSS variables. Components can't read the disk: local photos are sent as base64 (`foto_restaurante`, cached).
- **Detail sheet** is an `st.dialog` with no widgets, opened only on the run right after a tap (`session_state.pop("ficha_abrir")`), so closing it with ✕ doesn't make it reappear.
- **Theme** lives in `.streamlit/config.toml` (light + dark). A few things the theme can't do (sticky search button, entry splash, cover strip) are CSS injected via `st.html`; they depend on Streamlit's internal `data-testid`/`st-key-*` class names and hardcode the light/dark backgrounds via `prefers-color-scheme`.

## Deployment

Streamlit Community Cloud, main file `algoritmo/app.py`; one app per branch (`main` and `v2` are deployed separately). `excels/`, `imagenes/` and `.streamlit/config.toml` must be committed; `.streamlit/secrets.toml` must not.
