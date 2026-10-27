# Detalle técnico y registro de decisiones

Sistema que **obtiene, procesa y visualiza** información de restaurantes y de sus menús.

| Etapa | Estado |
|---|---|
| 0. Corridas programadas (base de datos + cola de tareas) | ✅ Lista |
| 1. Obtención de datos de Just Eat (crawling) | ✅ Lista |
| 2. Procesamiento: vincular cada restaurante de Just Eat con su ficha de Google | ✅ Lista |
| 3. Procesamiento: clasificar cada plato en las categorías estándar | ✅ Lista |
| 4. Visualización: dashboard interactivo | ✅ Lista |

---

## Etapa 0 — Cómo se ejecuta: corridas programadas

Cada ejecución del pipeline es una **corrida**, registrada en la base de datos con su estado. Nadie tiene que
dejar un proceso corriendo a mano:

```
 Se pide una corrida  ──►  Todos los días a las 06:00  ──►  La cola la procesa  ──►  Paso siguiente…
 (queda "En espera")       se toman las que esperan          paso por paso           o "Terminado" / "Fallido"
```

- **Pedir una corrida:** desde el panel de administración ("Añadir corrida") o con `manage.py start_pipeline`.
  Queda **En espera** hasta la revisión diaria; con `--now` se procesa en el momento.
- **Pasos, en orden:** (1) obtener los datos de Just Eat, (2) cargar los datos de Google, (3) vincular cada
  restaurante de Just Eat con su ficha de Google, (4) clasificar los platos de los restaurantes vinculados,
  (5) **publicar**. Cuando un paso termina bien, se encola el siguiente.
- **Nada se ve a medias:** los pasos 1 a 4 escriben en **tablas auxiliares de la corrida**, que nadie más ve.
  Recién el paso 5, si todos los anteriores terminaron bien, pasa todo junto (restaurantes, fichas de Google,
  vínculos, taxonomía y platos) a las tablas que muestran el panel y el dashboard, **en una sola transacción**.
  Si algo falla en el camino, esas tablas siguen mostrando la última corrida publicada, entera.
- **Si un paso falla**, la corrida queda **Fallida** con el mensaje de error, visible en el panel, y no sigue.
  Para reintentar se crea una **corrida nueva** (acción "Reprocesar" en el panel); nunca se retoma una a medias.
  Lo que la corrida fallida dejó en las tablas auxiliares se guarda 7 días para diagnosticar, y después se borra.
- **Nada queda colgado:** un paso que nadie tomó en 1 hora, o que sigue en curso pasado su tiempo máximo
  (por ejemplo, porque se cayó el servidor), se marca como fallido automáticamente.
- **Resultados consultables:** cada restaurante obtenido se guarda en la base (tabla de venues), con nombre,
  marca, dirección, coordenadas, valoración, cocinas, horarios y menú. Cada corrida publicada lo actualiza y deja
  anotado qué corrida lo escribió; el historial completo queda en el archivo de cada corrida.
- **Las decisiones de las personas ganan:** si mientras corre una corrida alguien confirma o rechaza un vínculo,
  o corrige la categoría de un plato, al publicar se respeta lo que decidió la persona.

---

## Etapa 1 — Obtención de datos de Just Eat

### En una frase

Para cada restaurante de nuestra lista, el sistema entra en Just Eat, trae **sus datos** (nombre, dirección,
valoración, horarios, tipo de cocina…) y **su menú completo** (platos, descripciones, precios y opciones), y
lo guarda todo en **un único archivo** con el mismo formato que el archivo de referencia que nos entregaron
(`just_eat_venues.json`).

### Cómo funciona, paso a paso

```
 Lista de restaurantes  ──►  Consulta a Just Eat   ──►  Ordena y limpia  ──►  Archivo de resultados
 (2.696 direcciones web)     (de a 10 restaurantes)     los datos             (uno por corrida)
```

### Dónde quedan los resultados

Cada corrida guarda sus archivos en **su propia carpeta**, nombrada con la fecha y hora en que empezó (hora
UTC). Así ninguna corrida pisa ni borra los resultados de otra:

```
output/
  20261026T135228Z/                     ← corrida del 26/10/2026 a las 13:52:28 UTC
    just_eat_venues.json                ← resultado final
    just_eat_venues.failures.json       ← restaurantes que fallaron y por qué (solo si hubo fallos)
    menu_items.json                     ← platos clasificados (etapa 3)
  20261027T090000Z/                     ← otra corrida, independiente
    ...
```

### Qué pasa si algo sale mal

- **Falla un restaurante** (por ejemplo, ya no existe en Just Eat): se anota en la lista de fallos y la
  corrida sigue con el resto. El resultado final incluye todos los que sí se pudieron obtener.
- **La corrida se traba** (por ejemplo, Just Eat deja de responder): si pasa **1 hora** sin terminar, se
  cancela y queda **marcada como fallida**. No se genera archivo final, porque estaría incompleto. El archivo
  de avance se conserva para revisar hasta dónde llegó.
- **No se retoma desde donde quedó.** Una corrida fallida se vuelve a pedir completa. Así cada resultado
  corresponde siempre a una única corrida, de principio a fin.

### Decisiones tomadas

| # | Decisión | Por qué |
|---|---|---|
| 1 | **Platos con varios tamaños** (ej. pizza mediana / familiar): se guarda **un solo plato, con el precio y las opciones del primer tamaño**. | Es la regla del archivo de referencia (verificada en el 100% de los casos revisados). Guardar todos los tamaños queda como mejora futura. |
| 2 | **Los extras no llevan precio** (ej. "queso extra"): se guarda la opción, pero no su costo. | El archivo de referencia nunca guarda ese precio. Empezamos simple; se puede agregar después. |
| 3 | **La marca sale de una tabla propia que mantenemos nosotros** ([`brands.json`](../src/libs/crawler/data/brands.json), 654 restaurantes), cargada inicialmente desde el archivo de referencia (`python -m libs.crawler.build_brands`) y ampliable a mano. | Just Eat no publica la marca, y no se puede deducir del nombre: "Pans & Company" pertenece a "Eat Out" y VIPS a "GRUPO ALSEA". Deducirla por nombre daba cientos de errores. Un restaurante que no está en la tabla queda sin marca. |
| 4 | **La lista de restaurantes es un archivo del proyecto**, revisado por el equipo. El sistema no acepta direcciones de afuera. | Es una lista controlada que cambia poco. Si en el futuro tuviera que cambiar seguido, conviene llevarla a una tabla fácil de editar y volver a validar cada dirección. |
| 5 | **De a 10 restaurantes a la vez**, con pausas y reintentos. Se configura con `CRAWLER_BATCH_SIZE`. *(Al principio eran 4.)* | Equilibrio entre velocidad y no sobrecargar a Just Eat, para evitar que nos bloqueen. Medido sobre la lista completa: con 10 el crawl tarda 6,2 minutos contra 12,1 con 4, con los mismos 4 fallos (restaurantes que ya no existen) y sin pedidos rechazados por Just Eat. |
| 6 | **Una carpeta por corrida, sin retomar corridas, con un límite de 1 hora.** | Corridas independientes y fáciles de auditar. Una corrida trabada no queda "colgada" para siempre. |
| 7 | **El proceso completo vive en un único componente reutilizable**, que se ejecuta igual desde la cola de tareas o a mano desde la línea de comandos. | Una sola lógica para la ejecución programada y para las pruebas o urgencias. |
| 8 | **Las corridas se controlan con registros en la base**, revisados una vez por día, y cada paso encola al siguiente. | El estado y los errores de cada corrida quedan a la vista de todos, y una corrida pedida nunca se pierde aunque se caiga un servidor. |
| 9 | **Los restaurantes se guardan en la base con sus datos principales en columnas y el menú completo como documento.** | Permite filtrar y buscar para el dashboard ya mismo. Los platos de los restaurantes vinculados tienen además su propia tabla, con su categoría (etapa 3). |

---

## Etapa 2 — Vincular cada restaurante de Just Eat con su ficha de Google

### En una frase

Para cada restaurante que obtuvo la corrida, el sistema busca **su ficha en Google** (con valoración,
reseñas, web, horarios y etiquetas). Si la encuentra con seguridad, los vincula solo. Si es dudoso, lo deja
**para que una persona lo confirme**. Si no la encuentra, no inventa nada.

### Cómo funciona, paso a paso

```
 Archivo de Google  ──►  Para cada restaurante:     ──►  Decide con reglas  ──►  Cada ficha de Google
 (21.926 lugares)        fichas a menos de 400 m,        claras: aceptado,       se vincula a un solo
                         ¿nombre parecido? ¿misma        a revisar o nada        restaurante
                         calle y número?
```

1. **Se cargan las fichas de Google** desde un archivo configurado (ver Decisiones). Si el archivo es el mismo
   que en la corrida anterior, no se vuelve a cargar. El archivo de referencia trae 22.991 registros de 21.926
   lugares distintos; los repetidos se cargan una sola vez.
2. **Se buscan candidatos cerca:** solo las fichas a menos de 400 m de cada restaurante.
3. **Se comparan tres señales:**
   - **El nombre.** Las palabras raras pesan mucho y las comunes poco: compartir "Goiko" dice mucho,
     compartir "restaurante" o "sushi" no dice nada.
   - **La distancia.**
   - **La dirección:** misma calle y mismo número, aunque una esté en castellano y otra en catalán.
4. **Se decide con reglas explícitas,** que se pueden explicar caso por caso:
   - **Aceptado:** nombre distintivo y muy parecido, cerca o en la misma dirección. También un nombre bastante
     parecido en la misma dirección.
   - **A revisar:** nombre distintivo pero lejos, o nombre parecido pero genérico.
   - **Nunca se vincula solo por la dirección:** en un centro comercial hay decenas de locales en el mismo
     número.
5. **Uno a uno:** cada ficha de Google se asigna a un solo restaurante, empezando por los vínculos más seguros.
   El que pierde prueba con su siguiente candidato, si tiene.

### Qué resultados da

Con el archivo de referencia completo (2.696 restaurantes):

| Resultado | Restaurantes | Qué significa |
|---|---|---|
| **Aceptado automáticamente** | 1.248 | Vinculado sin intervención. |
| **A revisar** | 46 | Probable, pero una persona lo confirma o lo rechaza en el panel. |
| **Sin vínculo** | 1.402 | No tiene ficha en los datos de Google: casi todos los supermercados (Caprabo, Dia, Condis…), marcas que solo existen en delivery y locales fuera de la zona que cubre el archivo de Google. |

**¿Qué tan bien funciona?** Lo medimos contra **200 restaurantes revisados a mano**, elegidos al azar entre
casos fáciles, dudosos y sin candidato:

- **Precisión:** el 100% de los vínculos automáticos es correcto.
- **Cobertura:** se vincula automáticamente el 92% de los restaurantes que sí tienen ficha en Google, y el 94%
  contando los que quedan a revisar.

Esta medición es un test del proyecto: si un cambio futuro baja la precisión del 97%, los tests fallan.

**Ejemplos de casos difíciles que resuelve bien:**

| Just Eat | Google | Por qué es difícil |
|---|---|---|
| Goiko Barcelona Laietana | Goiko | La sucursal ("Laietana") está en el nombre de un lado solo. |
| Mixiang | Mi Xiang | Nombre junto o separado. |
| Sushiyaki — *Calle Consejo de Ciento 211* | Restaurante cocina japonesa Sushiyaki — *Carrer del Consell de Cent, 211* | Dirección en castellano y en catalán. A 63 m hay otro "Sushiyaki II". |
| SHN Doner del Turco — *Carrer Lepanto 315* | SHN Doner del Turco — *Carrer de Lepant, 315* | Calle mal escrita. |
| Starbucks Diagonal Mar | Starbucks (no "Diagonal Mar") | "Diagonal Mar" es el centro comercial, también listado en Google. |
| Restaurante Chino Dao | ~~Restaurante Chino Sabroso~~ | Mismo edificio, solo comparten palabras comunes: son dos locales distintos. |
| Restaurante Aguila Sushi | Restaurante Águila Sushi, no ~~Sushi~~ (a 195 m) | Compartir "sushi" no prueba nada. |

### Revisión por personas

En el panel, la sección **Vínculos Just Eat - Google** muestra cada par con los dos nombres, las dos
direcciones, la distancia y el motivo. Hay dos acciones: **Confirmar** y **Rechazar**. Esas decisiones
**se respetan en todas las corridas siguientes**: un par confirmado queda fijo y un par rechazado no se vuelve
a proponer. Si la ficha de Google de un par confirmado **desaparece del archivo de Google**, el par no se borra:
vuelve a **A revisar**, marcado "sin ficha de Google" (filtro en el panel), hasta que una persona decida. Si la
ficha vuelve a aparecer, el par vuelve a quedar confirmado.

### Decisiones tomadas

| # | Decisión | Por qué |
|---|---|---|
| 10 | **El vínculo se hace siempre con los restaurantes que obtuvo esa misma corrida, y solo si su paso de obtención terminó bien.** No hay forma de vincular un archivo de Just Eat cargado aparte ni de saltear la obtención. | Si se pudieran cargar datos de otro origen, se abriría la puerta a datos corruptos o desactualizados y a errores difíciles de rastrear. Así, cada vínculo sale de datos obtenidos y validados por el propio sistema, en la misma corrida. |
| 11 | **El archivo de Google se indica en la configuración y queda anotado en cada corrida al crearla.** No se puede elegir desde el panel. | Se sabe exactamente qué archivo usó cada corrida. Que no se elija desde el panel evita que alguien pueda hacer leer al sistema un archivo cualquiera del servidor. |
| 12 | **Cada corrida carga su propio archivo de Google y anota su "huella" (hash SHA-256).** Al publicar, sus fichas reemplazan a las anteriores y se borran las que ya no están. Cada ficha indica qué corrida la publicó. *(Antes la carga se salteaba si el archivo no había cambiado; con las tablas auxiliares cada corrida necesita su copia, y cuesta unos 10 s.)* | Se sabe de qué versión del archivo sale cada dato, y cada corrida vincula solo contra el archivo que ella misma cargó. |
| 13 | **Un registro inválido en el archivo de Google rechaza el archivo entero.** | Nunca queda una carga a medias. Un archivo con datos raros (coordenadas imposibles, enlaces que no son https) se detecta y se informa. |
| 14 | **Reglas explícitas en lugar de un modelo de aprendizaje automático.** | Cada decisión se puede explicar. Con 200 casos revisados alcanza para ajustar las reglas; un modelo necesitaría muchos más ejemplos etiquetados. |
| 15 | **Ante la duda, a revisar; nunca un vínculo dudoso automático.** | Un vínculo equivocado mezcla los datos de dos locales distintos y es peor que no tener vínculo. |

### Limitaciones conocidas

- **Traducciones completas de nombres** ("Arrosseria Plaça Espanya" contra "Arrocería Plaza España"): se
  resuelven si las palabras se parecen lo suficiente; si no, quedan sin vínculo.
- **Números de calle vecinos** (25 contra 27) o la misma ficha repetida en Google con dos identificadores:
  quedan a revisar o se asigna una de las dos.
- **Las 200 etiquetas las preparó el equipo técnico y falta que negocio las revise.** Están en
  [`tests/fixtures/matching/labeled_pairs.json`](../tests/fixtures/matching/labeled_pairs.json), con el motivo de
  los casos ambiguos.

## Etapa 3 — Clasificar cada plato en las categorías estándar

### En una frase

Para cada restaurante vinculado con Google, el sistema toma **todos los platos y bebidas de su menú** y le asigna
a cada uno **una categoría de la taxonomía estándar** (`food_categories.xlsx`: 101 categorías, cada una con
nombre, grupo y familia), por ejemplo *PIZZA MODO NAPOLETANA → pizza / pizza / food*. Cada clasificación dice
**qué la decidió y con cuánta confianza**, y una persona puede corregirla.

### Cómo funciona, paso a paso

```
 Platos de los restaurantes  ──►  Reglas de palabras  ──►  Lo que las reglas  ──►  Tabla de platos y
 vinculados en esta corrida       (nombre, sección,        no deciden: platos      archivo menu_items.json
 (aceptados o confirmados)        descripción)             parecidos (embeddings)
```

1. **Qué platos entran:** los de los restaurantes que obtuvo esta corrida y que tienen vínculo con Google
   **aceptado o confirmado**. Los vínculos **a revisar quedan fuera** hasta que una persona los confirme. Cada
   plato se guarda **una vez por restaurante**, aunque aparezca en varios menús (delivery y recogida), y
   **todos se guardan**, tengan o no categoría.
2. **Reglas de palabras** en castellano, catalán e inglés, en este orden:
   - **El tipo de plato en el nombre** decide: "Ensalada de salmón" es una ensalada, no salmón.
   - **Lo que va después de "con", "+" o una coma es acompañamiento:** "Pollo asado con patatas + Coca-Cola" es
     pollo.
   - **La sección del menú** decide cuando el nombre solo dice ingredientes: "Carbonara" en "Pizzas medianas"
     es una pizza.
   - **El ingrediente principal** del nombre: "Pollo al curry" es pollo.
   - **Un menú o combo** se clasifica por su plato principal, que suele estar en la descripción ("Menú 3":
     *3 dürüm + patatas + bebida* es kebab), y queda marcado como combo.
3. **Platos parecidos (embeddings)** para lo que las reglas no deciden ("Shia Chiao", "Veg Jalfrezi"): el plato
   se compara con platos reales que las reglas ya clasificaron con seguridad y toma la categoría de los más
   parecidos. Corre **en el propio servidor**: los menús no se envían a ningún servicio externo.
4. **Lo que sigue sin pistas** queda con la categoría de su sección ("Entrantes" → otros entrantes) o **sin
   categoría**. Lo que no es comida ni bebida (palillos, bolsas) queda sin categoría.

**"Genérico" y "otro":** la taxonomía distingue, por ejemplo, *generic fish* (un pescado sin especificar:
"Pescado del día") de *other fish* (un pescado concreto que no está en la lista: "Dorada"). Un plato concreto
de la sección "Postres" que no está en la lista ("Tamer") es *other sweets*; "Postre del día" es *generic
sweets*.

### Qué resultados da

Sobre los **98.549 platos** de los 1.248 restaurantes vinculados del archivo de referencia, las reglas solas
clasifican el **95%** (en 2 segundos):

| Qué lo decidió | Platos | Confianza |
|---|---|---|
| El nombre del plato | 80,8% | 0,95 (tipo de plato) · 0,75 (ingrediente) · 0,65 (resto del nombre) |
| La sección del menú | 11,8% | 0,85 (o 0,40 si la sección es solo "Entrantes", "Tapas"…) |
| La descripción (combos) | 2,4% | 0,60 |
| No es comida ni bebida | 0,2% | sin categoría |
| Sin pistas en las reglas | 4,7% | → platos parecidos (embeddings) o sin categoría |

El **93,5%** de los platos queda con confianza 0,6 o más. Lo que queda por debajo se puede filtrar en el
panel para revisarlo.

**¿Qué tan bien funciona?** Lo medimos contra **platos reales revisados a mano**, elegidos al azar:

| Muestra | Categoría exacta (`name`) | Grupo (`parent`) | Familia (`family`) |
|---|---|---|---|
| **200 platos al azar que nunca se usaron para ajustar las reglas** (la medida honesta) | **79%** | **82%** | **95%** |
| Los 300 platos que se leyeron mientras se escribían las reglas | 91% | 92% | 98% |
| 100 platos que las reglas no deciden: solo reglas | 17% | 23% | 37% |
| Esos mismos 100 platos con platos parecidos (embeddings) | 24% | 31% | 87% |

- La diferencia entre el 91% y el 79% muestra cuánto se "acomodan" las reglas a los ejemplos que se usaron para
  escribirlas. Por eso **el número que vale es el 79%**, medido con platos que nunca se miraron antes.
- Entre las clasificaciones con confianza 0,6 o más, acierta el **85%** de la categoría exacta.
- Los embeddings ayudan poco en la categoría exacta de los platos difíciles (17% → 24%), pero mucho en saber si
  es comida o bebida (37% → 87%). Sobre los 200 platos al azar casi no cambian el resultado (79% → 78% en la
  categoría, 95% → 97% en la familia), porque ahí las reglas ya deciden casi todo. Sus resultados siempre quedan
  con **confianza baja** (0,5 o menos).
- Estas mediciones son un test del proyecto: si un cambio futuro las empeora, los tests fallan.

**Corrida real con 40 restaurantes** (26/10/2026): 36 vinculados, 4.577 platos, todos guardados y clasificados
en 48 segundos. 3.840 por el nombre, 368 por la sección, 131 por la descripción, 193 por platos parecidos,
4 que no son comida y 41 sin categoría.

### Revisión por personas

En el panel, **Ítems de menú** lista cada plato con su restaurante, sección, categoría, confianza y qué la
decidió. Se puede filtrar por **confianza baja** o **sin categoría**, por familia, grupo o método. Una persona
puede **corregir la categoría** (es lo único editable). La corrección **se respeta en todas las corridas
siguientes**, y además sirve de ejemplo para los platos parecidos.

### Decisiones tomadas

| # | Decisión | Por qué |
|---|---|---|
| 16 | **Solo se clasifican los platos de los restaurantes que obtuvo esa misma corrida, con vínculo aceptado o confirmado, y solo si el vínculo de esa corrida terminó bien.** Los vínculos a revisar quedan fuera por ahora. | La misma regla de integridad que la etapa 2: los datos salen siempre de pasos anteriores de la misma corrida. Incluir los "a revisar" se verá más adelante. |
| 17 | **Todos los platos de esos restaurantes se guardan, aunque no tengan categoría.** Si un restaurante pierde su vínculo, sus platos se borran. | La tabla de platos refleja exactamente el menú actual de los restaurantes vinculados. |
| 18 | **Reglas de palabras y embeddings locales, sin un modelo de lenguaje (LLM) externo.** | Un LLM por API tiene un costo aparte por uso y envía los menús a un tercero. Las reglas son gratis, inmediatas y explicables; los embeddings corren en el servidor. |
| 19 | **La taxonomía es un archivo configurado (`FOOD_CATEGORIES_FILE`), anotado con su huella (SHA-256) en cada corrida.** Una fila inválida rechaza el archivo entero. Si el archivo nuevo quita una categoría que usan las reglas, la corrida falla **antes de cambiar nada**. | Igual que con Google: se sabe qué taxonomía usó cada corrida, y un cambio de taxonomía obliga a revisar las reglas en lugar de clasificar mal en silencio. |
| 20 | **El modelo de embeddings tiene versión fija y se descarga al construir la imagen, verificando la huella de cada archivo.** En ejecución nunca se descarga nada. | Nadie puede cambiar el modelo por detrás, y el servidor no depende de internet para clasificar. |
| 21 | **Cada corrida clasifica todos sus platos.** Se puede poner un tope por corrida (`CATEGORIZATION_MAX_ITEMS_PER_RUN`, 0 = sin tope, el valor por defecto): con tope, los platos nuevos o cambiados van primero y el resto espera a la siguiente corrida. *(Al principio el tope era 20.000; con los 122.000 platos reales hacían falta unas 6 corridas para clasificarlo todo.)* | Una corrida publicada tiene que mostrar el menú completo clasificado. Medido: clasificar los 122.000 platos lleva unos 5 minutos y 3 GB de memoria, así que el tope ya no hace falta para controlar la duración. |
| 22 | **Las correcciones de las personas nunca se pisan.** | Igual que con los vínculos confirmados. |
| 23 | **Criterios de clasificación:** tipo de plato antes que ingrediente; combos por su plato principal; un curry por su carne; el agua y la tónica son *soft drinks*; lo que no es comida, sin categoría. | Son las reglas que se usaron para etiquetar las muestras, así medición y clasificador dicen lo mismo. |
| 24 | **La confianza baja se guarda y se filtra; no hay revisión obligatoria.** | Por ahora alcanza con poder encontrarlos; una cola de revisión como la de los vínculos se puede agregar después. |

### Limitaciones conocidas

- **Palabras ambiguas:** "Lomo de atún" sale cerdo (por "lomo") y "Costilla de cordero" también (por
  "costilla"). Hacen falta reglas de "ingrediente + carne" más finas.
- **Platos de cocinas poco representadas** (georgiana, coreana, filipina, peruana): si su nombre no tiene
  ninguna palabra conocida, dependen de la sección o de los embeddings, que aciertan poco con el modelo chico
  actual. Agregar palabras a las reglas es la mejora más barata.
- **La taxonomía no tiene categorías** para algunos tipos de plato (cuscús, tamales, dumplings): van a la
  más cercana ("otros entrantes", "otras verduras").
- **Las 600 etiquetas las preparó el equipo técnico y falta que negocio las revise.** Algunas son discutibles
  ("Melón con jamón": ¿tapa o fruta?). Están en
  [`tests/fixtures/categorization/`](../tests/fixtures/categorization/).

---

## Etapa 4 — Dashboard

### En una frase

Una página web, con usuario y contraseña, que muestra **los resultados de la última corrida publicada**:
cuántos restaurantes se vincularon y qué ofrecen por categoría, y, plegado debajo, más detalle. Se entra en
`http://<servidor>/` (en local, `http://localhost:8000/`).

### Qué muestra

| Bloque | Qué se ve | Interacción |
|---|---|---|
**A la vista (lo que pide el enunciado):**

| Bloque | Qué se ve | Interacción |
|---|---|---|
| **Restaurantes matcheados** | Aceptados automáticamente + confirmados por una persona, sobre el total crawleado. | |
| **Restaurantes por vínculo** | Barra con los cinco grupos (aceptados, confirmados, a revisar, rechazados, sin match; cada restaurante está en uno solo) y la lista paginada de cada grupo: nombre, cocinas, rating, ficha de Google, score y distancia. | Un clic en un grupo abre su lista. Desde "a revisar" y "rechazados", un link lleva al admin para decidir. |
| **Oferta principal por categoría** | Ranking de las categorías que ofrecen más restaurantes (o con más platos), con % de restaurantes y precio mediano, sin combos. | Comida o bebida; grupo o categoría exacta; restaurantes o platos; gráfico o tabla. Un clic en una categoría abre su detalle: subcategorías, platos más repetidos y restaurantes. |

**Más detalle (plegado; sus datos se piden recién al desplegarlo):**

| Bloque | Qué se ve | Interacción |
|---|---|---|
| **Platos por vínculo** | Los platos de los restaurantes aceptados o confirmados: restaurante, plato, sección, categoría, confianza y precio. | Aceptados o confirmados; paginado. |
| **Menús** | Platos por menú (mediana), % que vende bebidas y % de combos. | |
| **Calidad de la categorización** | Platos categorizados, % con confianza baja, qué decidió la categoría (nombre, sección, embeddings…) y su confianza. | |

Si hay una corrida nueva en curso, o si la última falló, un aviso lo dice: los números son siempre los de la
última corrida publicada, completos (una corrida en curso o fallida no cambió nada).

### Quién entra

- Los **superusuarios** y los usuarios del grupo **"Dashboard"** (lo crea la instalación; se agregan personas
  desde el admin, en *Usuarios*). Ese grupo solo puede **ver**; no puede cambiar nada.
- Las correcciones (confirmar o rechazar vínculos, corregir categorías) siguen en el admin, para el personal
  autorizado. Lo que se decide ahí se ve en el dashboard enseguida.

### Decisiones tomadas

| # | Decisión | Por qué |
|---|---|---|
| 25 | **API REST de Django (solo lectura) + una página en React.** | Las cuentas se hacen en el servidor, cerca de los datos, y quedan probadas con tests; la página solo dibuja. La misma API sirve para otro cliente si hiciera falta. |
| 26 | **La página la sirve el mismo Django**, en el mismo dominio. | Usa la misma sesión y la misma protección CSRF que el admin, sin abrir CORS ni otro servidor. |
| 27 | **Siempre la última corrida publicada; los vínculos, como están ahora.** | Una corrida en curso o fallida no muestra datos a medio escribir. Una decisión en el admin se refleja al instante, sin esperar otra corrida. |
| 28 | **"Matcheado" = aceptado automáticamente + confirmado por una persona.** Los restaurantes se ven en cinco grupos que no se pisan (aceptados, confirmados, a revisar, rechazados, sin match) y suman el total crawleado. | Es la misma definición que usa la categorización (etapa 3). |
| 29 | **El ranking principal cuenta restaurantes, no platos.** | Un restaurante con 40 pizzas no debería pesar como 40 restaurantes. Con el selector se ve también por platos. |
| 30 | **El precio es la mediana y sin combos.** | Un combo no es el precio de su plato, y la mediana no se deja arrastrar por un plato de 100 €. |
| 31 | **Solo la última corrida, sin evolución en el tiempo.** | Con una corrida diaria la evolución tiene sentido más adelante; hoy no hay historia que mostrar. |
| 37 | **A la vista, solo lo que pide el enunciado; el resto, plegado y cargado a pedido.** *(Al principio también estaban rating Just Eat vs. Google, precio según Google, categorías por restaurante y distancia de los vínculos; se quitaron.)* | Lo importante se lee de un vistazo y la página carga menos. Lo que no se pidió no compite por atención, y no se consulta si nadie lo abre. |
| 38 | **La lista de platos es solo de los restaurantes matcheados.** | Son los únicos con platos clasificados y guardados en su tabla (etapa 3). Armarla para los demás desde el menú crawleado se midió: unos 2 segundos por pedido para recorrer 262 MB de menús, contra 0,03 s de la tabla. |
| 39 | **La API tiene un contrato: un serializer de DRF por cada respuesta y su análogo en TypeScript, escrito a mano.** `VenueRowSerializer` (backend) ↔ `VenueRow` (`frontend/src/schemas.ts`), con los mismos campos. | Si cambia un campo, se sabe dónde impacta: del lado de Python fallan los tests que validan cada respuesta del servicio contra su serializer (con un campo de más o de menos también); del lado del front, `tsc` marca cada componente y cada dato de prueba que lo usa. Sin generar código de un lado al otro ni validar en el navegador: cada lado se prueba con sus tests. |

### Decisiones sobre la consistencia de los datos

| # | Decisión | Por qué |
|---|---|---|
| 32 | **Cada paso escribe en tablas auxiliares de su corrida, y un paso final las publica juntas en una transacción.** | Una corrida que falla a mitad de camino no deja datos a medias: lo publicado es siempre una corrida completa. (Pasó con la corrida #5: falló al categorizar después de haber reemplazado los restaurantes.) |
| 33 | **Al publicar, las decisiones de las personas ganan** sobre lo que propuso la corrida. | Una corrida puede tardar; quien revisa no debería tener que esperar a que termine ni ver deshecho su trabajo. |
| 34 | **Se publica de a una corrida, y nunca una más vieja sobre una más nueva.** | Dos corridas en paralelo no se pisan y los datos nunca retroceden. |
| 35 | **Las tablas auxiliares de una corrida fallida se guardan 7 días.** | Permiten ver qué había hecho cada paso antes del error; después solo ocupan lugar. |
| 36 | **Un vínculo confirmado cuya ficha de Google desaparece vuelve a revisión, en lugar de borrarse.** | Es una decisión de una persona: no la deshace un cambio en un archivo sin que alguien lo vea. |

### Limitaciones conocidas

- **No hay historia entre corridas**: las tablas publicadas guardan el último estado de cada restaurante. Para
  comparar corridas haría falta guardar una foto de las métricas al publicar cada una.

---

## Anexo técnico

### Uso

Stack: Django 5.2 LTS, PostgreSQL 16, Celery 5.6 + Redis (broker), Celery beat (tareas programadas), Django REST
Framework + React (dashboard).

**Con Docker** (base de datos, Redis, panel, worker y beat). Primero hay que copiar `google_venues.json` y
`food_categories.xlsx` a `./data/`. La imagen descarga el modelo de embeddings al construirse:

```bash
docker compose up --build
docker compose exec web python manage.py createsuperuser   # dashboard en http://localhost:8000/, panel en /admin/
docker compose exec web python manage.py start_pipeline --limit 10 --now
```

**Sin Docker** (Postgres y Redis propios; copiar `.env.example` a `.env` y ajustar las URLs):

```bash
python3.13 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python src/libs/categorization/download_model.py   # modelo de embeddings, en data/downloads/ (opcional: sin él, solo reglas)
.venv/bin/python manage.py migrate
(cd frontend && npm ci --ignore-scripts && npm run build)  # dashboard (Node 24)
.venv/bin/celery -A config worker -l INFO      # en otra terminal
.venv/bin/celery -A config beat -l INFO        # en otra terminal
.venv/bin/pytest                               # tests: usan Postgres y ejecutan las tareas sin Redis
```

**Comandos**

| Comando | Qué hace |
|---|---|
| `manage.py start_pipeline [--limit N] [--now] [--google-venues-file F] [--food-categories-file F]` | Crea una corrida en espera; `--now` la encola sin esperar a las 06:00. Los archivos por defecto son `GOOGLE_VENUES_FILE` y `FOOD_CATEGORIES_FILE`. |
| `manage.py crawl_just_eat [--limit N] [-o DIR] [--brands F]` | Crawl inmediato, sin cola: escribe **solo los archivos**; nunca toca la base (solo una corrida publica). Salida: `0` todo OK, `1` algunos restaurantes fallaron, `2` la corrida superó el tiempo límite. |

**Estados:** `WAITING` → `QUEUED` → `RUNNING` → `SUCCEEDED` / `FAILED`, en la corrida (`PipelineRun`) y en
cada paso (`StepRun`, con métricas, carpeta de salida y error). El ciclo de vida de las corridas está en
[`apps/pipeline/run_services.py`](../src/apps/pipeline/run_services.py) y cada cambio de estado de un paso en
[`apps/pipeline/transition_services.py`](../src/apps/pipeline/transition_services.py) (`StepTransition`). Los
nombres de los pasos están en [`apps/pipeline/constants.py`](../src/apps/pipeline/constants.py):

- el beat toma las corridas en espera con `SELECT … FOR UPDATE SKIP LOCKED` y las encola recién cuando la
  transacción confirma (`on_commit`): nunca se encola dos veces la misma;
- un paso solo se ejecuta si está `QUEUED`, así un mensaje repetido (`acks_late`) no lo vuelve a correr;
- los pasos se configuran en `PIPELINE_STEPS` (nombre → función), en orden; cada paso verifica que los
  anteriores de su corrida hayan terminado bien (`require_succeeded`).

**Tablas auxiliares y publicación**

| Publicada (la ven panel y dashboard) | Auxiliar de la corrida | La escribe |
|---|---|---|
| `Venue` | `StagedVenue` (Just Eat y Google) | `crawl_just_eat`, `load_google_venues` |
| `VenueMatch` | `StagedVenueMatch` (solo `ACCEPTED`/`REVIEW`) | `match_venues` |
| `FoodCategory` | `StagedFoodCategory` | `categorize_menu_items` |
| `MenuItem` | `StagedMenuItem` | `categorize_menu_items` |

- Cada par comparte los campos con una clase base abstracta (`VenueData`, `MatchData`, `MenuItemData`), así que
  no hay definiciones duplicadas. Las auxiliares llevan la corrida (`run`) y se borran en cascada con ella.
- Los pasos leen las decisiones de las personas de las tablas publicadas (vínculos confirmados o rechazados,
  correcciones de categoría) y nunca las escriben.
- [`apps/menus/publish_services.py`](../src/apps/menus/publish_services.py) (`MenuPublisher`) +
  [`apps/venues/publish_services.py`](../src/apps/venues/publish_services.py) (`VenuePublisher`): paso `publish_run`. Una transacción con `pg_advisory_xact_lock` (se publica de a una corrida); si ya se publicó
  una corrida más nueva, falla con `StalePublishError` sin tocar nada. Copia fichas de Google (y borra las que
  ya no están, salvo las de vínculos confirmados, que pasan a `REVIEW` con `google_missing`), restaurantes de
  Just Eat, vínculos (descarta los que contradicen una decisión tomada mientras corría), taxonomía y platos
  (respeta las correcciones manuales), marca `PipelineRun.published_at` y borra las filas auxiliares.
- `pipeline.purge_staged_runs` (cada hora, [`apps/menus/staging_cleanup_services.py`](../src/apps/menus/staging_cleanup_services.py)) borra las auxiliares de corridas fallidas hace más de
  `PIPELINE_STAGING_RETENTION_DAYS` (7).
- **Memoria:** los menús pesan hasta varios MB por restaurante (31 GB de JSON entre todos los platos si se los
  trae de a uno). Ninguna consulta los carga si no los usa (`defer`, `values()`), se leen de a 50 restaurantes, y
  el worker corre cada paso en un proceso nuevo (`CELERY_WORKER_MAX_TASKS_PER_CHILD=1`), con un tope de 6 GB en
  docker compose.

**Matching** (librería pura en [`src/libs/matching/`](../src/libs/matching/), sin Django):

| Módulo | Qué hace |
|---|---|
| `constants.py` | Todos los valores fijos: vocabularios (`STOPWORDS`, `STREET_TYPES`, `AREA_WORDS`, alias de calles), umbrales (radio de búsqueda, cercanía, nombre fuerte y parecido, tolerancia de tipeo) y pesos del score. |
| `normalization_business_rules.py` | Cómo se leen nombres y direcciones: palabras de un nombre, calle y número de una dirección, clave de la calle (sin tipo ni idioma) y cuándo dos calles son la misma. |
| `matching_business_rules.py` | Cuándo dos fichas son el mismo local: crédito de cada palabra (tipeo, palabras juntas o separadas), palabras distintivas y conflicto, puntaje de distancia, score general y el orden de asignación (`ranking_key`). Cada regla de decisión es una función propia (`Evidence` → decisión o nada) y `decision_rules()` las lista en orden, con la tabla en su documentación: agregar una regla es escribir la función y sumarla a la lista. |
| `text_helpers.py` | Limpieza genérica de texto (acentos, `&`, apóstrofos, símbolos). |
| `address.py` | `Address`: calle y número leídos de una dirección, comparables entre sí. |
| `names.py` | Similitud de nombres ponderada por IDF sobre los nombres de Google (`NameScorer`, `NameComparison`), con la fórmula y un ejemplo en su documentación. |
| `geo.py` | Distancia haversine e índice en grilla: cada restaurante se compara con unos cientos de fichas, no con 22.000. |
| `matcher.py` | Candidatos, evidencia, decisión y asignación uno a uno (greedy). |

- [`apps/venues/google_import_services.py`](../src/apps/venues/google_import_services.py): carga de Google, con
  validación pydantic y límite de tamaño (`GOOGLE_VENUES_MAX_BYTES`). El hash queda en
  `PipelineRun.google_venues_sha256`. [`just_eat_import_services.py`](../src/apps/venues/just_eat_import_services.py)
  carga lo que trajo el crawl.
- [`apps/venues/matching_services.py`](../src/apps/venues/matching_services.py): paso `match_venues` (`RunMatching`).
  Las decisiones de las personas (confirmar, rechazar) están en
  [`review_services.py`](../src/apps/venues/review_services.py).
- `VenueMatch` tiene los estados `ACCEPTED`, `REVIEW`, `CONFIRMED` y `REJECTED`. La base garantiza que cada
  venue tenga como máximo un vínculo activo de cada lado.
- **Evaluación:** `pytest tests/matching/test_evaluation.py` corre el matcher sobre los 200 casos etiquetados.
  Usa todas las fichas de Google, reducidas a nombre, dirección y coordenadas, en
  `tests/fixtures/matching/google_places.json.gz`.

**Categorización** (librería pura en [`src/libs/categorization/`](../src/libs/categorization/), sin Django):

| Módulo | Qué hace |
|---|---|
| `taxonomy.py` | Lee y valida `food_categories.xlsx` (openpyxl en modo solo lectura, pydantic, límites de tamaño y filas). |
| `constants.py` | Todos los valores fijos: palabras fuertes (tipo de plato) y débiles (ingrediente) por categoría, no-comida, combo, genérico, conectores, la confianza de cada regla y los parámetros de los embeddings. |
| `keywords.py` | Búsqueda de esas palabras en un texto (`KeywordRules`), con plurales, frases y palabras ancladas al inicio. Sin expresiones regulares gigantes: 98.549 platos en 2 s. Falla si una palabra apunta a dos categorías o a una que no existe. |
| `classification_business_rules.py` | Cada regla es una función propia (`ItemContext` → `Classification` o nada): nombre, sección, ingrediente, resto del nombre, descripción de combos y, como respaldo, sección de "curso". `classification_rules()` las lista en orden y `ItemRuleAnalysis` aplica la primera que decide. La tabla de reglas y confianzas está en su documentación. |
| `item_context.py` | Lo que las reglas pueden leer de un plato (palabras, palabras clave del nombre, la sección y la descripción, si es combo…), calculado solo cuando una regla lo pide. |
| `classifier.py` | Reglas primero y, para lo que queda sin decidir, embeddings. |
| `domain.py`, `text_helpers.py` | Tipos (`Classification`, `Hit`, `Method`…) y limpieza del texto de los platos. |
| `embeddings.py` | `FastEmbedder` (fastembed/ONNX, `paraphrase-multilingual-MiniLM-L12-v2` cuantizado, 384 dimensiones) y voto de los 5 vecinos más parecidos entre hasta 120 referencias por categoría (similitud mínima 0,7). |

- [`apps/menus/categorization_services.py`](../src/apps/menus/categorization_services.py): paso
  `categorize_menu_items` (`RunCategorization`). Las correcciones manuales están en
  [`correction_services.py`](../src/apps/menus/correction_services.py) y la lectura de los menús en
  [`menu_helpers.py`](../src/apps/menus/menu_helpers.py). Arma los
  `StagedMenuItem` de la corrida (único por venue + id de ítem, con `menu_ids`); un plato cuyo texto no cambió
  conserva la clasificación publicada. Clasifica todos (o, si hay tope, primero los `PENDING`),
  escribe `menu_items.json` en la carpeta de la corrida (con archivo temporal y renombre) y guarda el hash de la
  taxonomía en `PipelineRun.food_categories_sha256`. Las referencias de los embeddings son los ítems de la
  corrida decididos con confianza ≥ 0,85, los de otros venues y todas las correcciones manuales.
- `MenuItem.method`: `name`, `section`, `description`, `embedding`, `non_food`, `unknown`, `pending` y `manual`.
- **Evaluación:** `pytest tests/categorization/test_evaluation.py` (solo reglas: los tests nunca cargan el
  modelo; usan un embedder falso donde hace falta).
- **Variables:** `FOOD_CATEGORIES_FILE`, `CATEGORIZATION_MAX_ITEMS_PER_RUN` (0 = sin tope), `CATEGORIZATION_EMBEDDING_MODEL_PATH`
  (vacía: solo reglas) y `CATEGORIZATION_EMBEDDING_MODEL`.

**Dashboard** ([`apps/dashboard/`](../src/apps/dashboard/) + [`frontend/`](../frontend/)):

- QuerySets por corrida en los modelos, para pedir los datos directo: `PipelineRun.objects.last_published()`,
  `Venue.objects.crawled_by(run).in_match_group(group)`, `.linked()`, `.without_large_fields()` y
  `MenuItem.objects.of_venues(...).categorized(family)`, `.low_confidence()`.
- [`dashboard_services.py`](../src/apps/dashboard/dashboard_services.py): `DashboardService(run)`, con **un método
  por gráfico** que encadena esos QuerySets y arma la respuesta (agregados de Postgres como `percentile_cont` para la
  mediana), sin HTTP. Probado contra un resultado armado a mano
  ([`tests/dashboard/conftest.py`](../tests/dashboard/conftest.py)).
- [`serializers.py`](../src/apps/dashboard/serializers.py): el **contrato** de la API. Los parámetros aceptados y un
  serializer por respuesta (`SummarySerializer`, `VenueRowSerializer`, `DishRowSerializer`…), que también redondea
  precios, scores y distancias. Al leer son estrictos (`ResponseSerializer`: un campo que no está en el contrato es
  un error), y [`tests/dashboard/test_serializers.py`](../tests/dashboard/test_serializers.py) valida con ellos cada
  respuesta del servicio. Su análogo en el front es [`frontend/src/schemas.ts`](../frontend/src/schemas.ts), con
  los mismos nombres sin "Serializer"; los datos de prueba del front se tipan con él (`satisfies`).
- API (Django REST Framework), solo `GET`, en `/api/dashboard/`: `summary/`, `venues/?group=&page=` (25 por
  página), `categories/?family=&level=&order=&top=` y `categories/detail/?level=&key=`; para "Más detalle",
  `dishes/?group=&page=` (solo `accepted` o `confirmed`), `menus/` y `quality/`.
  Sin corrida terminada responde 404.
- Frontend: React 19 + TypeScript + Recharts, con Vite. `npm run build` deja el resultado en
  `src/apps/dashboard/static/dashboard/` (ignorado por git), y Django lo sirve en `/dashboard/`. La imagen de
  Docker lo compila en una etapa con Node y en la imagen final quedan solo los archivos estáticos.

```bash
cd frontend && npm ci --ignore-scripts && npm run build   # una vez, o después de cambiar el frontend
npm test                                                  # tests del frontend (Vitest + Testing Library)
npm run dev                                               # desarrollo en :5173, contra el Django de :8000
```

**Tareas programadas** (Celery beat): `pipeline.dispatch_waiting_runs` cada día a las `PIPELINE_DISPATCH_HOUR`
(06:00, hora de Madrid), `pipeline.fail_stalled_steps` cada 15 minutos y `pipeline.purge_staged_runs` cada hora.

**Seguridad de la plataforma**

- Secretos y hosts solo por variables de entorno (o `.env`, ignorado por git). Con `config.settings.production`
  la app no arranca sin `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DATABASE_URL` y `CELERY_BROKER_URL`,
  y fuerza HTTPS, HSTS y cookies seguras.
- Celery acepta solo JSON (nunca pickle) y los mensajes llevan solo ids, no datos.
- El contenedor corre sin root; en docker compose, Postgres y el panel escuchan solo en `127.0.0.1` y Redis
  pide contraseña y no se expone.
- En el panel los venues son de solo lectura: solo el pipeline los escribe. En los ítems de menú solo se puede
  cambiar la categoría; la taxonomía es de solo lectura.
- Los archivos de entrada (Google, taxonomía) vienen de la configuración, nunca de un formulario, y se validan
  enteros antes de tocar la base.
- **Dashboard:** login obligatorio y permiso de lectura (grupo "Dashboard"); la API solo responde `GET`, solo
  JSON, no lee el cuerpo de ningún pedido, valida cada parámetro contra una lista cerrada (`top` ≤ 50) y limita
  los pedidos por usuario (`DASHBOARD_THROTTLE_RATE`). Tras `LOGIN_MAX_FAILURES` contraseñas erróneas (por
  usuario o por IP) el login se bloquea `LOGIN_LOCKOUT_SECONDS`; el conteo vive en la caché compartida
  (`CACHE_URL`, Redis en docker compose). La página y la API llevan `Content-Security-Policy` estricta (scripts,
  estilos y datos solo del propio sitio, sin scripts inline, sin iframes); la sesión dura 8 h. Las dependencias
  de npm van con versión exacta y lockfile, se instalan sin scripts y el build de Docker falla si `npm audit`
  encuentra vulnerabilidades altas. En producción los estáticos los sirve whitenoise.
- El modelo de embeddings se descarga al construir la imagen, con revisión fija y SHA-256 verificado de cada
  archivo; en ejecución `HF_HUB_OFFLINE=1` y carga solo local. Los menús nunca salen del servidor.
