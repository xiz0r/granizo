"""Colores de los PNG de radar de REDEMET (maxcappi y CAPPI 3/5/7/10 km) → reflectividad en dBZ.

La escala es una rampa de 10 colores por cada 5 dBZ (pasos de 0,5 dBZ), dibujada sin suavizar: cada píxel trae
exactamente uno de estos colores. Se armó juntando los colores de 39 imágenes y ordenándolos; la leyenda del sitio
(redemet.decea.mil.br) marca 20, 30 y 45 dBZ justo donde empiezan el verde, la transición al amarillo y la del naranja
al rojo, y la fila de mm/h de la misma leyenda (1, 3 y 25 mm/h) coincide con Marshall-Palmer para esos dBZ.
El último tramo (magenta → violeta, 65 dBZ o más) casi no aparece y se completó siguiendo la leyenda.

Píxeles transparentes = sin eco. Cada imagen es una grilla lat/lon regular entre los límites que devuelve la API.
"""
import numpy as np

BLOCKS = [
    # 0–5 dBZ: celeste → turquesa
    [(114, 255, 255), (102, 253, 253), (91, 251, 252), (79, 249, 250), (67, 248, 249), (55, 246, 247), (44, 244, 246),
     (32, 243, 244), (20, 241, 243), (8, 239, 241)],
    # 5–10
    [(0, 236, 240), (0, 228, 241), (0, 220, 242), (0, 213, 242), (0, 205, 243), (1, 197, 244), (1, 189, 244),
     (1, 182, 245), (1, 174, 246), (1, 166, 247)],
    # 10–15: → azul
    [(1, 156, 247), (1, 139, 247), (1, 123, 247), (1, 107, 247), (1, 91, 247), (0, 75, 246), (0, 59, 246),
     (0, 42, 246), (0, 26, 246), (0, 10, 246)],
    # 15–20: azul → verde
    [(0, 10, 237), (0, 35, 212), (0, 61, 188), (0, 86, 163), (0, 112, 138), (0, 138, 114), (0, 163, 89),
     (0, 189, 65), (0, 214, 40), (0, 240, 15)],
    # 20–25: verde
    [(0, 253, 1), (0, 248, 1), (0, 242, 1), (0, 237, 1), (0, 232, 1), (0, 227, 0), (0, 222, 0), (0, 216, 0),
     (0, 211, 0), (0, 206, 0)],
    # 25–30
    [(0, 200, 0), (0, 195, 0), (0, 189, 0), (0, 183, 0), (0, 177, 0), (0, 171, 0), (0, 165, 0), (0, 160, 0),
     (0, 154, 0), (0, 148, 0)],
    # 30–35: verde → amarillo
    [(13, 150, 0), (38, 161, 0), (64, 172, 0), (89, 184, 0), (115, 195, 0), (141, 206, 0), (166, 217, 0),
     (192, 228, 0), (217, 239, 0), (243, 250, 0)],
    # 35–40: amarillo
    [(254, 252, 0), (251, 246, 0), (249, 240, 0), (246, 233, 0), (244, 227, 0), (242, 221, 0), (239, 215, 0),
     (237, 209, 0), (234, 203, 0), (232, 197, 0)],
    # 40–45: → naranja
    [(232, 191, 0), (235, 186, 0), (237, 181, 0), (240, 176, 0), (242, 171, 0), (244, 166, 0), (247, 161, 0),
     (249, 156, 0), (252, 151, 0), (254, 146, 0)],
    # 45–50: naranja → rojo
    [(255, 135, 0), (255, 121, 0), (255, 106, 0), (255, 92, 0), (255, 77, 0), (254, 63, 0), (254, 48, 0),
     (254, 34, 0), (254, 20, 0), (254, 5, 0)],
    # 50–55: rojo
    [(251, 0, 0), (247, 0, 0), (243, 0, 0), (239, 0, 0), (235, 0, 0), (231, 1, 0), (227, 1, 0), (223, 1, 0),
     (218, 1, 0), (214, 1, 0)],
    # 55–60: rojo oscuro
    [(212, 1, 0), (210, 1, 0), (208, 1, 0), (207, 1, 0), (205, 1, 0), (203, 0, 1), (202, 0, 1), (200, 0, 1),
     (198, 0, 1), (196, 0, 1)],
    # 60–65: rojo → magenta (el último color no se vio: extrapolado)
    [(200, 0, 19), (206, 0, 45), (212, 0, 70), (218, 0, 96), (224, 0, 121), (230, 0, 146), (236, 0, 172),
     (242, 0, 197), (248, 0, 223), (254, 0, 248)],
]
# 65–80: magenta → violeta, como la leyenda (rgb(255,0,255) → rgb(151,88,201)), en 30 pasos.
_tail = [tuple(int(round(a + (b - a) * k / 29)) for a, b in zip((255, 0, 255), (151, 88, 201))) for k in range(30)]
PALETTE = np.array([c for block in BLOCKS for c in block] + _tail, dtype=float)
DBZ = np.arange(len(PALETTE)) * 0.5
EXACT = {tuple(int(x) for x in c): z for c, z in zip(PALETTE, DBZ)}
EXACT[(64, 173, 0)] = EXACT[(64, 172, 0)]  # redondeo distinto entre imágenes


def decode(rgba):
    """Arreglo HxWx4 (uint8) → dBZ (float, NaN sin eco). Los colores que no están en la escala van al más parecido."""
    rgba = np.asarray(rgba)
    out = np.full(rgba.shape[:2], np.nan)
    echo = rgba[..., 3] > 0
    if not echo.any():
        return out
    px = rgba[echo][:, :3].astype(int)
    codes = px[:, 0] * 65536 + px[:, 1] * 256 + px[:, 2]
    uniq, inv = np.unique(codes, return_inverse=True)
    vals = np.empty(len(uniq))
    for i, code in enumerate(uniq):
        c = (code // 65536, code // 256 % 256, code % 256)
        vals[i] = EXACT[c] if c in EXACT else DBZ[np.abs(PALETTE - c).sum(1).argmin()]
    out[echo] = vals[inv]
    return out


def grid(frame, shape):
    """Centros de píxel (lat, lon) de una imagen con los límites de la API (fila 0 = norte)."""
    h, w = shape
    lat_max, lat_min = float(frame["lat_max"]), float(frame["lat_min"])
    lon_min, lon_max = float(frame["lon_min"]), float(frame["lon_max"])
    lat = lat_max - (np.arange(h) + 0.5) * (lat_max - lat_min) / h
    lon = lon_min + (np.arange(w) + 0.5) * (lon_max - lon_min) / w
    return lat, lon
