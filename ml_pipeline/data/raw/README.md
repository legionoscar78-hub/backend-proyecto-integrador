# Datos crudos (`raw/`)

Datasets originales, tal como se descargaron. **No se editan ni se sobrescriben**: toda
limpieza se hace en el ETL (`ml_pipeline/etl/`) y sale a `../processed/`.

Los archivos de esta carpeta **no se suben a git** (ver `.gitignore`; solo se versiona este
README). Para reproducir el proyecto, descárgalos de nuevo, colócalos aquí con estos
nombres y verifica el checksum.

> Los campos marcados **POR COMPLETAR** no se pudieron confirmar. Rellénalos con la
> página desde la que descargaste cada archivo.

---

## `DiseaseAndSymptoms.csv`

| | |
|---|---|
| Contenido | Casos con un diagnóstico (`diseases`) y 377 columnas de síntomas con valor 0/1 |
| Fuente / URL | **POR COMPLETAR** |
| Autor | **POR COMPLETAR** |
| Licencia | **POR COMPLETAR** |
| Fecha de descarga | **POR COMPLETAR** |
| Idioma | Inglés |
| Tamaño | 190,786,867 bytes (~182 MB) |
| SHA-256 | `8de90603ebada467fc2703db2ee4292856e52d64e94982ef926df22fa0c21320` |

**Posible origen (sin confirmar):** el dataset *Disease and symptoms dataset 2023* de
Mendeley Data, DOI [10.17632/2cxccsxydc.1](https://data.mendeley.com/datasets/2cxccsxydc/1),
publicado por Bran Stark, licencia **CC BY 4.0** (exige atribución). Coincide en cifras
(~246 mil filas, 773 enfermedades, 377 síntomas) y la página indica que fue **generado
artificialmente**. Si tu archivo viene de otro sitio (por ejemplo Kaggle), anota ese
enlace y su licencia arriba.

**Perfil verificado del archivo:**
- 246,945 filas × 378 columnas (`diseases` + 377 síntomas binarios), sin nulos.
- 773 enfermedades, entre 1 y 1,219 filas cada una (mediana 168).
- 57,298 filas duplicadas (23%). Hay que deduplicar **antes** de dividir train/test.
- ~5.3 síntomas por fila (de 1 a 12).
- 49 de los 377 síntomas no aparecen en ninguna fila.
- No incluye edad, peso, altura ni sexo: el modelo solo puede usar síntomas.

**Advertencia:** si es un dataset sintético, no refleja prevalencias ni cuadros clínicos
reales. Sirve para prototipar el sistema, no para sacar conclusiones clínicas.

---

## `ICD-10.csv`

| | |
|---|---|
| Contenido | Catálogo de códigos CIE-10 / ICD-10 con su descripción |
| Fuente / URL | **POR COMPLETAR** |
| Autor | **POR COMPLETAR** |
| Licencia | **POR COMPLETAR** |
| Fecha de descarga | **POR COMPLETAR** |
| Idioma | Inglés |
| Tamaño | 3,123,551 bytes (~3 MB) |
| SHA-256 | `4a36e3fbe7f1a932de2625b26a29ac868d3f8846b13715878b18357331e232da` |

**Perfil verificado del archivo:**
- 36,393 filas. Columnas: `id`, `text`, `parent` y una cuarta columna sin nombre.
- `parent` tiene un solo valor no nulo y la cuarta columna está casi vacía: se descartan en el EDA.
- Mezcla categorías de 3 caracteres (`A00`) con subcategorías más largas (`A000`).
  Para el proyecto se usan las de 3 caracteres.

---

## Verificar que un archivo no cambió

```bash
sha256sum DiseaseAndSymptoms.csv ICD-10.csv
```

Los valores deben coincidir con los de las tablas de arriba.
