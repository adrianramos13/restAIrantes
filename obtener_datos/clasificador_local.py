"""Clasificador GRATIS de reseñas, para sustituir a Jev (que cobra por token).

Responde lo mismo que `clasificar_restaurantes_jev.clasificar` (cocina + sentimiento, con probabilidades y
confianza), así que el resto del análisis (votos por restaurante, platos, excel, catálogo) no cambia:
  - Sentimiento: las ESTRELLAS que puso quien escribe la reseña (4-5 Buena, 3 Neutra, 1-2 Mala). Es lo que
    Jev intentaba adivinar del texto, pero dicho por el propio cliente. Sin estrellas, palabras clave.
  - Cocina: palabras clave por categoría (los platos de ejemplo de CATEGORIAS + gentilicios y platos típicos de
    PALABRAS_EXTRA). Gana la categoría con más palabras en la reseña; sin ninguna -> "no_se_sabe".
No toca CATEGORIAS ni HUELLA: la caché de Jev sigue valiendo si algún día se vuelve a usar.
"""

import re

from clasificar_restaurantes_jev import CATEGORIA_SIN_DATOS, CATEGORIAS, TERMINOS_POR_CATEGORIA, _sin_tildes

# Más pistas por categoría (sin tildes, en minúsculas; se buscan como palabra completa o principio de palabra).
PALABRAS_EXTRA = {
    "espanola": ["comida casera", "cocina tradicional", "comida espanola", "cocina espanola", "menu del dia",
                 "cocido", "rabo de toro", "oreja", "lacon", "pulpo a la gallega", "fabada", "cochinillo",
                 "lechazo", "chistorra", "morcilla", "huevos rotos", "asturian", "gallego", "gallega", "vasco",
                 "vasca", "castellan", "andaluz", "extremen", "manchego", "riojan", "navarr", "leones", "cantabr"],
    "tapas_raciones": ["tapas", "tapa ", "tapeo", "tapear", "pincho", "pintxo", "racion", "raciones", "media racion",
                       "bravas", "montadito", "vermut", "barra", "taberna", "bocadillo de calamares"],
    "arroces_mediterranea": ["arroz", "arroces", "paella", "arroceria", "fideua", "valencian", "senyoret",
                             "arroz con bogavante", "arroz del senoret"],
    "carnes_parrilla": ["parrilla", "brasa", "asador", "chuleton", "chuleta", "entrecot", "solomillo", "lomo alto",
                        "lomo bajo", "vaca vieja", "carne a la", "steak", "picanha", "picana", "costillar",
                        "churrasco", "secreto", "presa iberica", "tomahawk", "maduracion", "madurada"],
    "pescados_mariscos": ["marisco", "marisqueria", "pescado", "pulpo", "gambas", "gamba", "langostino", "ostra",
                          "mejillon", "almeja", "navaja", "zamburina", "bogavante", "centolla", "percebe",
                          "cigala", "bacalao", "merluza", "rodaballo", "lubina", "dorada", "atun", "chipiron",
                          "sepia", "boqueron", "pescaito", "fritura"],
    "italiana": ["italian", "pizza", "pizzeria", "pasta", "trattoria", "osteria", "risotto", "lasana", "carbonara",
                 "gnocchi", "nocchi", "burrata", "tiramisu", "ravioli", "focaccia", "napolitan", "calzone",
                 "spaghetti", "espagueti", "tagliatelle", "pappardelle", "parmesan", "mozzarella", "panna cotta"],
    "japonesa": ["japon", "sushi", "sashimi", "nigiri", "maki", "uramaki", "ramen", "gyoza", "tempura", "udon",
                 "yakitori", "izakaya", "temaki", "edamame", "teriyaki", "tataki", "okonomiyaki", "takoyaki",
                 "mochi", "omakase", "wagyu"],
    "asiatica_otra": ["chin", "thai", "tailand", "corean", "korea", "vietnam", "indio", "india", "hindu", "nepal",
                      "pakistan", "wok", "dim sum", "dumpling", "pato laqueado", "pad thai", "curry", "bibimbap",
                      "kimchi", "tikka", "naan", "biryani", "tandoori", "masala", "baozi", "bao", "noodle",
                      "tallarines", "arroz tres delicias", "rollito", "hot pot", "malasi", "indonesi", "filipin"],
    "mexicana": ["mexic", "taco", "taqueria", "guacamole", "nacho", "burrito", "quesadilla", "enchilada",
                 "tex mex", "tex-mex", "fajita", "cochinita", "pastor", "tortilla de maiz", "mezcal", "margarita",
                 "chilaquiles", "pozole", "totopo"],
    "latinoamericana": ["peru", "ceviche", "cebiche", "lomo saltado", "pisco", "argentin", "empanada",
                        "provoleta", "venezol", "arepa", "colombian", "bandeja paisa", "brasil", "rodizio",
                        "cuban", "dominican", "ecuator", "boliv", "chilen", "uruguay", "tequeno", "patacon",
                        "chimichurri", "anticucho", "aji de gallina", "salvadore", "pupusa"],
    "oriente_medio": ["liban", "turc", "grieg", "arabe", "marroqu", "persa", "irani", "sirio", "siria", "hummus",
                      "humus", "falafel", "shawarma", "kebab", "kebap", "durum", "gyros", "moussaka", "musaka",
                      "tajine", "cuscus", "couscous", "baklava", "tabule", "pita", "halal", "georgian"],
    "americana": ["hamburgues", "burger", "alitas", "wings", "costillas bbq", "barbacoa", "bbq", "hot dog",
                  "perrito", "sandwich", "smash", "diner", "patatas fritas",
                  "pollo frito", "fried chicken", "nuggets", "cheeseburger", "brisket", "pulled pork"],
    "europea_otra": ["frances", "francia", "bistro", "creperie", "crepe", "galette", "portugu", "bacalhau",
                     "francesinha", "aleman", "salchicha", "codillo", "britan", "ingles", "fish and chips",
                     "nordic", "sueco", "belga", "suiz", "fondue", "raclette", "austriac", "schnitzel", "ruso",
                     "ucran", "polac", "hungar", "goulash", "jachapuri", "khachapuri"],
    "vegetariana_vegana": ["vegano", "vegana", "veganos", "veganas", "vegetarian", "plant based", "sin carne",
                           "tofu", "seitan", "tempeh", "heura", "bowl", "poke", "healthy", "saludable"],
    "reposteria_cafeteria": ["cafeteria", "cafe ", "cafes", "brunch", "desayuno", "desayunar", "merienda",
                             "pasteleria", "panaderia", "obrador", "tarta", "bolleria", "croissant", "cruasan",
                             "tostada", "tortitas", "pancake", "gofre", "helado", "heladeria", "churro",
                             "chocolate con churros", "cupcake", "cookie", "galleta", "bizcocho", "napolitana de",
                             "capuchino", "latte", "matcha", "specialty coffee", "zumo", "smoothie"],
    "fusion_autor": ["fusion", "de autor", "cocina de autor", "creativ", "menu degustacion", "degustacion",
                     "estrella michelin", "michelin", "vanguardia", "gastronomico", "maridaje",
                     "alta cocina", "experiencia gastronomica"],
}

# Sin estrellas (raro): sentimiento por palabras.
_POSITIVAS = ["buenisim", "riquisim", "espectacular", "excelente", "genial", "perfect", "increible", "maravill",
              "recomendable", "recomiendo", "repetir", "repetiremos", "volveremos", "delicios", "brutal",
              "estupend", "fantastic", "encant", "muy bueno", "muy buena", "muy rico", "muy rica", "de 10"]
_NEGATIVAS = ["malisim", "horrible", "fatal", "pesim", "asqueros", "decepcion", "no volvere", "no volveremos",
              "no recomiendo", "nunca mas", "lamentable", "frio", "fria", "caro para", "tardaron", "esperar mas",
              "sucio", "sucia", "mal servicio", "muy malo", "muy mala", "no merece", "timo", "vergonzos"]


def _patron(terminos):
    """Una regex por categoría: cada término al principio de palabra ("japon" vale para japonés/japonesa)."""
    trozos = sorted({re.escape(_sin_tildes(t).strip()) for t in terminos if t.strip()}, key=len, reverse=True)
    return re.compile(r"\b(?:" + "|".join(trozos) + ")")


PATRONES = {cat: _patron(TERMINOS_POR_CATEGORIA.get(cat, []) + PALABRAS_EXTRA.get(cat, []))
            for cat in CATEGORIAS if cat != CATEGORIA_SIN_DATOS}
_PAT_POS, _PAT_NEG = _patron(_POSITIVAS), _patron(_NEGATIVAS)


def _repartir(puntos, elegida):
    """Probabilidades (proporcionales a los puntos) y confianza (la de la elegida)."""
    total = sum(puntos.values())
    probs = {k: (v / total if total else (1.0 if k == elegida else 0.0)) for k, v in puntos.items()}
    return probs, probs[elegida]


def cocina(texto):
    t = _sin_tildes(texto)
    puntos = {cat: len(pat.findall(t)) for cat, pat in PATRONES.items()}
    mejor = max(puntos, key=lambda c: puntos[c])   # empate -> la primera de CATEGORIAS, como en la agregación
    if puntos[mejor] == 0:
        return CATEGORIA_SIN_DATOS, {CATEGORIA_SIN_DATOS: 1.0}, 1.0
    probs, conf = _repartir(puntos, mejor)
    return mejor, probs, conf


def sentimiento(texto, estrellas=None):
    try:
        e = float(estrellas)
    except (TypeError, ValueError):
        e = None
    if e is not None and e == e:   # no NaN
        elegido = "Buena" if e >= 4 else "Mala" if e <= 2 else "Neutra"
        return elegido, {elegido: 1.0}, 1.0
    t = _sin_tildes(texto)
    pos, neg = len(_PAT_POS.findall(t)), len(_PAT_NEG.findall(t))
    elegido = "Buena" if pos > neg else "Mala" if neg > pos else "Neutra"
    probs, conf = _repartir({"Buena": pos, "Mala": neg, "Neutra": 0.5}, elegido)
    return elegido, probs, conf


def clasificar(texto, estrellas=None):
    """Mismo formato que clasificar_restaurantes_jev.clasificar."""
    cat, cat_probs, cat_conf = cocina(texto)
    sent, sent_probs, sent_conf = sentimiento(texto, estrellas)
    return {"categoria": cat, "categoria_probs": cat_probs, "categoria_confianza": cat_conf,
            "sentimiento": sent, "sentimiento_probs": sent_probs, "sentimiento_confianza": sent_conf}
