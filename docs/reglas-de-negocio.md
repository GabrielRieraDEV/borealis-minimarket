


Reglas de Negocio
Sistema de gestión para minimarket  ·  Opción C
Cliente | 
Proyecto | Sistema de gestión comercial
Versión | 1.0
Fecha | 19 de agosto de 2026
Autor | Gregor Barrios — Borealis Software Solutions
Documentos relacionados | Especificación de Requisitos, Modelo de Datos


PROPÓSITO
Este documento define cómo calcula el sistema. La especificación de requisitos establece qué debe hacer; aquí se fija con qué fórmula, con qué precisión y en qué orden. Cada regla tiene un identificador que debe citarse en el código fuente y en las pruebas.
Todas las reglas se ilustran con ejemplos numéricos tomados de productos reales del negocio. Los ejemplos son parte de la especificación: si el código produce un resultado distinto, el código está equivocado.
Principio general de precisiónTodo importe monetario se representa con tipo decimal de precisión fija. Los cálculos intermedios se realizan con cuatro decimales y el redondeo a dos decimales se aplica únicamente al totalizar cada línea y al totalizar el documento. El modo de redondeo es medio hacia arriba.La tasa de cambio se almacena con seis decimales. Las cantidades se almacenan con tres decimales, lo que permite incorporar en el futuro la venta por peso sin migrar datos.

1. MONEDA Y TASA DE CAMBIO
RN-01 · Moneda base
El dólar estadounidense es la moneda base del sistema. Los precios de venta, los costos de compra y los gastos se almacenan en dólares. El bolívar es una moneda de presentación: se calcula al momento de mostrar o cobrar, y nunca se almacena como dato maestro.
La excepción son las operaciones ya consumadas —ventas, pagos y compras— que conservan el monto en bolívares efectivamente cobrado o pagado, junto con la tasa aplicada. Ese registro es histórico e inmutable.
RN-02 · Tasa única por fecha
Existe como máximo una tasa por fecha. Si se registra una segunda tasa para una fecha ya cargada, se reemplaza el valor anterior dejando constancia en la bitácora. Las operaciones ya registradas conservan la tasa con la que fueron creadas y no se recalculan.
RN-03 · Conversión a bolívares
monto_bs  =  redondear( monto_usd × tasa_vigente , 2 )
La tasa vigente es la de la fecha de la operación. Si no existe tasa para la fecha actual, el sistema no permite abrir caja ni registrar ventas, conforme a RF-12.
RN-04 · Tasa faltante
Al iniciar el día, el sistema intenta obtener la tasa del BCV. Si no hay conexión o la consulta falla, solicita la carga manual y registra el origen como manual. En ningún caso el sistema asume automáticamente la tasa del día anterior.

2. PRECIOS, IVA Y MÁRGENES
La regla que más errores produceEl precio exhibido incluye el IVA, pero el margen de ganancia se calcula sobre la base imponible, no sobre el precio con impuesto. Comparar el precio con IVA contra el costo infla artificialmente el margen y lleva a fijar precios por debajo de lo necesario.El IVA no es ingreso del negocio: es un impuesto que se cobra por cuenta del fisco. Nunca debe formar parte del cálculo de ganancia.

RN-05 · Desglose de un precio con IVA incluido
base_imponible  =  precio_con_iva  /  ( 1 + alícuota / 100 )
iva  =  precio_con_iva  −  base_imponible
En los productos exentos la alícuota es cero, con lo cual la base imponible coincide con el precio y el IVA es cero. No se requiere un tratamiento distinto.
RN-06 · Costo unitario a partir de la presentación de compra
costo_unitario  =  costo_presentación  /  unidades_por_presentación
Las unidades por presentación se capturan en cada línea de compra, no en la ficha del producto, porque un mismo producto puede adquirirse en presentaciones de distinto tamaño según el proveedor o la oportunidad.
RN-07 · Último costo
El costo vigente de un producto es el de su compra confirmada más reciente, ordenada por fecha de compra y, en caso de empate, por identificador. Las compras anuladas se excluyen. Este valor se utiliza para calcular márgenes, valorizar el inventario y valorizar las pérdidas.
RN-08 · Margen de ganancia
margen %  =  ( base_imponible  −  costo_unitario )  /  costo_unitario  × 100
El margen se expresa siempre sobre el costo. Un producto que cuesta un dólar y cuya base imponible es de un dólar con treinta centavos tiene un margen del treinta por ciento.
RN-09 · Precio calculado a partir del margen objetivo
precio_con_iva  =  costo_unitario  × ( 1 + margen / 100 )  × ( 1 + alícuota / 100 )
El margen objetivo aplicable es el del producto si lo tiene definido; en caso contrario, el de su categoría. El resultado se somete a la regla de redondeo comercial antes de guardarse.
RN-10 · Redondeo comercial
El precio en bolívares se redondea al múltiplo configurado en el sistema, siempre hacia arriba, para evitar la necesidad de sencillo. El valor por defecto es un múltiplo de uno. El redondeo se aplica al importe en bolívares mostrado al público, no al precio en dólares almacenado.
Ejemplo trabajado A — producto exento
Harina de maíz precocida, comprada en bulto de veinte unidades a doce dólares el bulto, con un margen objetivo del treinta por ciento y alícuota exenta. Tasa del día: 210,500000 bolívares por dólar.
Paso | Cálculo | Resultado
Costo unitario | 12,0000 / 20 | 0,6000 USD
Base imponible objetivo | 0,6000 × 1,30 | 0,7800 USD
Alícuota | Exento | 0,00 %
Precio con IVA | 0,7800 × 1,00 | 0,7800 USD
Precio en bolívares | 0,7800 × 210,500000 | 164,19 Bs
Precio redondeado al público | Múltiplo de 1, hacia arriba | 165,00 Bs
Margen real sobre el costo | (0,7800 − 0,6000) / 0,6000 | 30,00 %

Ejemplo trabajado B — producto gravado
Refresco en lata, comprado en caja de veinticuatro unidades a doce dólares con sesenta centavos la caja, margen objetivo del treinta y cinco por ciento y alícuota general del dieciséis por ciento. Misma tasa.
Paso | Cálculo | Resultado
Costo unitario | 12,6000 / 24 | 0,5250 USD
Base imponible objetivo | 0,5250 × 1,35 | 0,7088 USD
IVA | 0,7088 × 0,16 | 0,1134 USD
Precio con IVA | 0,7088 + 0,1134 | 0,8222 USD
Precio en bolívares | 0,8222 × 210,500000 | 173,08 Bs
Precio redondeado al público | Múltiplo de 1, hacia arriba | 174,00 Bs
Base recalculada desde el precio | 0,8222 / 1,16 | 0,7088 USD
Margen real sobre el costo | (0,7088 − 0,5250) / 0,5250 | 35,01 %

Verificación obligatoriaEl desglose inverso del ejemplo B debe devolver exactamente la base imponible de partida. Si al dividir el precio con IVA entre uno coma dieciséis no se recupera la base original, hay un error de redondeo en el orden de las operaciones. Esta comprobación debe existir como prueba automatizada.


3. INVENTARIO
RN-11 · La existencia es un resultado, no un dato
existencia  =  Σ  cantidad  de  movimiento_inventario  del  producto
No existe un campo de existencia actualizable en la ficha del producto. Toda variación se expresa como un movimiento con signo: positivo para entradas, negativo para salidas. Esta decisión permite explicar en cualquier momento por qué un producto tiene la cantidad que tiene, y es la única forma de que las pérdidas y los ajustes sean auditables.
Por razones de rendimiento puede mantenerse una existencia calculada en caché, siempre que se recalcule a partir de los movimientos y nunca se edite directamente.
RN-12 · Tipos de movimiento
Tipo | Signo | Origen
INICIAL | Positivo | Carga inicial del inventario en la puesta en marcha.
COMPRA | Positivo | Confirmación de una entrada de mercancía.
VENTA | Negativo | Confirmación de una venta.
ANULACION_VENTA | Positivo | Anulación de una venta previamente registrada.
ANULACION_COMPRA | Negativo | Anulación de una compra previamente registrada.
PERDIDA | Negativo | Registro de merma, vencimiento, daño, faltante o consumo propio.
AJUSTE | Ambos | Diferencia resultante de un conteo físico.

RN-13 · Nada se elimina
Ninguna operación se borra ni se modifica una vez confirmada. Las correcciones se expresan como movimientos inversos que referencian la operación original. El registro anulado conserva su número correlativo y queda marcado como anulado.
RN-14 · Costo del movimiento
Cada movimiento almacena el costo unitario vigente en el instante en que se produce. En las entradas es el costo de la compra; en las salidas es el último costo conocido. Este valor queda congelado y no se recalcula nunca.
RN-15 · Selección de lote
En los productos con control de vencimiento, la salida descuenta primero el lote cuya fecha de vencimiento sea más próxima y tenga existencia disponible. Si la cantidad solicitada excede la del lote, la salida se reparte en varios movimientos, uno por lote.
RN-16 · Alerta de existencia mínima
alerta  cuando   existencia  ≤  existencia_mínima
RN-17 · Alerta de vencimiento
alerta  cuando   fecha_vencimiento  −  hoy  ≤  días_alerta_del_producto
RN-18 · Valorización de pérdidas
Toda pérdida se valoriza al último costo vigente del producto en la fecha de la pérdida y afecta el resultado del período en que se registra, no el de la compra que originó la mercancía.

4. VENTAS, COBRO Y CAJA
RN-19 · Congelamiento del costo en la venta
Cada línea de venta almacena una copia del costo unitario vigente al momento de la operación. Esta es la regla más importante del sistema desde el punto de vista contable: sin ella, cualquier variación posterior del costo modificaría retroactivamente todas las ganancias históricas y los reportes dejarían de ser confiables.
RN-20 · Totales de la venta
total_línea  =  redondear( cantidad × precio_unitario , 2 )
base_línea  =  redondear( total_línea / ( 1 + alícuota/100 ) , 2 )
iva_línea  =  total_línea  −  base_línea
Los totales del documento son la suma de los totales de línea ya redondeados. No se recalcula el IVA sobre el total del documento, porque conviven productos exentos y gravados y el resultado diferiría de la suma de las partes.
RN-21 · Separación de exento y gravado
La venta almacena por separado el total exento, la base imponible gravada y el IVA. Esta separación es la que alimenta el libro de ventas y es requisito para una futura integración con máquina fiscal.
RN-22 · Cobro con varios medios
Σ  monto_usd  de  los  pagos   ≥   total_venta_usd
Cada pago se registra en su moneda original junto con su equivalente en dólares, calculado a la tasa de la venta. La venta no se confirma mientras la suma de los pagos no alcance el total.
RN-23 · Vuelto
vuelto_usd  =  Σ monto_usd  de  los  pagos  −  total_venta_usd
El vuelto se entrega en la moneda que indique el cajero. Si se entrega en bolívares, se convierte a la tasa de la venta y se redondea al múltiplo de sencillo configurado. Solo los medios en efectivo generan vuelto: un excedente pagado por punto de venta o transferencia debe rechazarse en lugar de devolverse.
Ejemplo trabajado C — venta con pago mixto
Venta de cuatro paquetes de harina exenta a 0,7800 dólares y de dos refrescos gravados a 0,8222 dólares. El cliente paga con cinco dólares en efectivo y el resto en bolívares. Tasa: 210,500000.
Concepto | Cálculo | Resultado
Línea 1 — total | 4 × 0,7800 | 3,12 USD
Línea 1 — base y exento | Alícuota 0 % | 3,12 exento
Línea 2 — total | 2 × 0,8222 | 1,64 USD
Línea 2 — base imponible | 1,64 / 1,16 | 1,41 USD
Línea 2 — IVA | 1,64 − 1,41 | 0,23 USD
Total exento |  | 3,12 USD
Total base imponible |  | 1,41 USD
Total IVA |  | 0,23 USD
Total de la venta | 3,12 + 1,41 + 0,23 | 4,76 USD
Equivalente en bolívares | 4,76 × 210,500000 | 1.001,98 Bs
Pago recibido en efectivo | 5,00 USD | 5,00 USD
Vuelto | 5,00 − 4,76 | 0,24 USD
Vuelto entregado en bolívares | 0,24 × 210,500000 | 50,52 → 51,00 Bs

RN-24 · Correlativo de ventas
El número de venta es un entero consecutivo que nunca se reutiliza ni se reasigna. Una venta anulada conserva su número. La numeración no se reinicia por período.
RN-25 · Anulación
La anulación requiere autorización con clave de administrador y un motivo obligatorio. Genera movimientos inversos de inventario por cada línea, con el mismo costo unitario congelado en la venta original, y marca el documento como anulado. La venta anulada se excluye de todos los reportes de resultados pero permanece en el libro de ventas identificada como tal.
RN-26 · Cierre de caja
esperado_por_medio  =  Σ  pagos  de  la  sesión  agrupados  por  medio
diferencia  =  conteo_físico  −  esperado
El cierre se calcula por separado para cada moneda de efectivo y para cada medio electrónico. Una diferencia distinta de cero no impide cerrar la caja, pero queda registrada y aparece en el reporte.

5. RESULTADOS DEL NEGOCIO
RN-27 · Costo de la mercancía vendida
CMV  =  Σ ( cantidad × costo_unitario_congelado )  de  las  ventas  del  período
RN-28 · Ganancia bruta
ganancia_bruta  =  ( base_imponible + exento )  −  CMV
El IVA queda excluido del cálculo por no constituir ingreso del negocio.
RN-29 · Ganancia real del período
ganancia_real  =  ganancia_bruta  −  pérdidas  −  gastos_operativos
Las pérdidas se valorizan conforme a RN-18. Los gastos operativos son los registrados con período coincidente. Los gastos no se prorratean entre productos: se restan del resultado global del período.
RN-30 · Inventario valorizado
valor_inventario  =  Σ ( existencia  ×  último_costo )
RN-31 · Libro de ventas
El libro agrupa las ventas por fecha y expresa los importes en bolívares utilizando la tasa de cada operación, no la tasa del día de emisión del reporte. Cada fila distingue el total exento, la base imponible, el IVA y el total. Las ventas anuladas se listan con importes en cero e indicación de su condición.
Formato pendiente de confirmaciónLa estructura definitiva del libro de ventas debe confirmarse con el contador del cliente antes de desarrollar el reporte, conforme a la Cláusula 6.7 del contrato. Las reglas de cálculo aquí definidas no cambian; lo que puede variar es la disposición de las columnas y los totales exigidos.

6. PERMISOS POR PERFIL
Operación | Administrador | Cajero
Registrar ventas | Sí | Sí
Abrir y cerrar caja | Sí | Sí
Consultar existencias | Sí | Sí
Ver costos y márgenes | Sí | No
Modificar precios | Sí | No
Registrar compras | Sí | No
Ajustar inventario | Sí | No
Registrar pérdidas | Sí | No
Anular ventas | Sí | Requiere autorización
Reportes de ganancia | Sí | No
Reporte de cierre de su sesión | Sí | Sí
Gestionar usuarios | Sí | No
Cargar tasa del día | Sí | No
Configurar el sistema | Sí | No

7. CASOS LÍMITE
Situación | Comportamiento esperado
No hay tasa cargada para hoy | No se permite abrir caja ni registrar ventas. El sistema solicita la carga manual.
La consulta automática del BCV falla | Se registra el intento fallido y se solicita carga manual. No se asume la tasa anterior.
Producto sin costo registrado | Se permite vender, pero el margen y la ganancia se informan como no determinables hasta registrar su primera compra.
Venta que deja existencia negativa | Se bloquea. El administrador puede autorizarla, y el sistema genera la alerta de inventario descuadrado.
Corte de energía durante una venta | La transacción no confirmada se descarta por completo. No debe quedar inventario descontado sin venta registrada.
Compra con presentación distinta a la habitual | Se acepta sin advertencia: las unidades por presentación son propias de cada línea de compra.
Costo nuevo superior al precio de venta vigente | Se advierte al confirmar la compra y se listan los productos que quedaron por debajo de su margen objetivo.
Lote vencido con existencia | Aparece en la alerta de vencimientos. No se bloquea su venta; la decisión es del negocio.
Cierre de caja con diferencia | Se permite cerrar. La diferencia queda registrada y se refleja en el reporte.
Anulación de una venta de un día anterior | Permitida con autorización. Los movimientos inversos se registran con la fecha de la anulación, no con la de la venta.
