# Hallazgos del estudio Southern Andes — OpenVIS

Documento vivo. Resume los hallazgos científicos del fork
[MendozaVolcanic/openVIS-Colaboracion-1](https://github.com/MendozaVolcanic/openVIS-Colaboracion-1).
Generado a partir de los runs en `data/results/` y los análisis en `data/sensitivity/`.

---

## 1. Cobertura IMS de los volcanes chilenos

Sobre **67 volcanes chilenos** del catálogo Smithsonian GVP:

- **100% (67/67) están en Tier A (<1500 km)** de al menos una estación IMS sudamericana.
- I01AR (Argentina, recientemente operativa) cubre el sur a distancias **muy cortas**:
  - Puyehue-Cordón Caulle: **128 km**
  - Villarrica: **182 km**
  - Osorno: **166 km**
  - Mocho-Choshuenco: **148 km**

Esto cuestiona la noción de "long-range only" — para el sur de Chile estamos en **rango cercano a medio**.

📁 `data/coverage/chile_ims_coverage.csv` · `data/coverage/chile_ims_coverage.png`

---

## 2. Casos de estudio ejecutados

| Caso | Año | Estaciones detectoras | IP_max | TP_pct | Veff |
|------|------|----------------------|--------|--------|------|
| Puyehue-Cordón Caulle | 2011 | I41PY, I02AR, I08BO | 24 999 | 98.3% | BGR |
| Calbuco | 2015 | I08BO (+ I14CL con Dazim=10°) | 7 463 | 92.1% | =1 |
| Villarrica | 2015 | I02AR, I08BO | 9 768 | **0%** ⚠️ | =1 |
| Chaitén | 2008 | I41PY | 764 | 100% | =1 |

---

## 3. Hallazgo crítico: contaminación cruzada Calbuco/Villarrica

Las **122 ventanas con IP≥100** del run de Villarrica (rango 2015-02 a 2015-05)
están **todas concentradas el 23-abr-2015 entre 10:20 y 11:30 UTC** —
exactamente la fase eruptiva de Calbuco.

**Causa:** desde I08BO (Bolivia, ~2600 km), Calbuco y Villarrica tienen
azimuts que difieren ~5°. Con `Dazim=10°` ambos volcanes caen dentro
del rango de tolerancia del filtro de back-azimuth, así que las
detecciones de **una** erupción se asocian a **ambos** volcanes.

**Implicancia operacional:** para distinguir erupciones de volcanes
geográficamente cercanos (mismo cono volcánico desde un IMS lejano)
se necesita:
1. Múltiples estaciones triangulando para reducir ambigüedad de azimut.
2. `Dazim` más estricto cuando hay volcanes "cercanos" (azimutalmente).
3. Cross-checking con sismicidad o cámaras locales.

📁 `data/sensitivity/false_positives_summary.csv`

---

## 4. Caso Chaitén 2008 — actividad post-paroxismo

VIS detectó **17 ventanas de IP≥100 entre 9:15 y 10:35 UTC del 9 de junio
de 2008** (un mes después del inicio de la erupción), con IP_max=764
desde I41PY (Paraguay, 2302 km).

Esto es **consistente con el catálogo histórico**: la crisis de Chaitén
tuvo múltiples pulsos explosivos durante todo mayo y junio 2008. El 9
de junio en particular tuvo colapsos de columna eruptiva
documentados (SERNAGEOMIN, GVP).

**Este es un caso donde VIS encuentra señal no documentada en los
catálogos primarios** — útil para revisión retrospectiva.

📁 `data/results/20260426T015621/`

---

## 5. Sensibilidad al parámetro Dazim (Calbuco 2015)

Barrido sistemático sobre Dazim ∈ {3°, 5°, 7°, 10°, 15°}, 5 corridas
(`scripts/dazim_sweep.py`):

| Dazim | Stations active | IP_max  | Stations in true window | False-positive periods |
|-------|-----------------|---------|-------------------------|-----------------------|
| 3°    | 0               | 0       | —                       | 1 (sin detección)     |
| **5°**| 1 (I08BO)       | 7 290   | I08BO                   | **0** ✅              |
| 7°    | 2               | 7 463   | I08BO                   | 1                     |
| 10°   | 2               | 7 463   | I08BO                   | 1                     |
| **15°**| 3 (+I02AR+I14CL)| **11 339** | **I02AR + I08BO**    | 1                     |

**Hallazgos:**
- Con `Dazim=3°` el filtro de azimut es **demasiado estricto** y se pierde
  toda detección útil.
- `Dazim=5°` es el **mejor compromiso operacional**: 1 estación robusta
  (I08BO), cero falsos positivos.
- `Dazim=15°` añade **I02AR (Argentina, 1721 km)** dentro de la ventana
  real (22-23 abril), subiendo IP_max a 11 339 Pa·det — pero introduce
  1 período eruptivo espurio fuera de ventana.

📁 `data/sensitivity/dazim_sweep_summary.csv` · `data/sensitivity/dazim_sweep_summary.png`

---

## 6. Brechas y próximos pasos

- **Veff-ratios para 2015**: solicitar a De Negri (`rodrigo.de_negri_leiva@uca.fr`)
  los archivos `veff50_IS##_2015_VIS.mat` para reprocesar Calbuco/Villarrica
  con corrección estratosférica.
- **Tablas ARCADE**: ídem, para corrección de back-azimuth dependiente de tiempo.
- **I01AR (Argentina)**: aún no está en el catálogo de bulletins BGR procesados.
  Si está disponible en otro formato, sería el game-changer para volcanes
  del sur de Chile (<200 km).
- **Datos PMCC locales OVDAS**: integrar bulletins propios de OVDAS en lugar
  de depender exclusivamente del IMS.
- **Validación cruzada con sismicidad volcanotectónica** de OVDAS para los
  4 casos de estudio.
