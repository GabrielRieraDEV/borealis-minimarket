


Especificación de Requisitos
Sistema de gestión para minimarket  ·  Opción C
Cliente | 
Proyecto | Sistema de gestión comercial
Alcance | Opción C — Intermedia
Versión | 1.1
Fecha | 25 de agosto de 2026
Autor | Gregor Barrios — Borealis Software Solutions
Documentos relacionados | Contrato (Anexo A), Reglas de Negocio, Modelo de Datos


1. PROPÓSITO Y CONTEXTO
Este documento traduce el alcance contratado (Anexo A del contrato) en requisitos verificables para el desarrollo. Es un documento técnico de uso interno; ante cualquier discrepancia, prevalece lo establecido en el contrato.
El sistema será utilizado por un minimarket de reciente apertura que comercializa víveres, charcutería empaquetada, carnicería, hortalizas, bebidas, limpieza, quincallería, bisutería, artículos electrónicos y tabaco. Operará en un único punto de venta, sobre un solo equipo, sin conexión permanente a internet.
Actores
Actor | Descripción | Acceso
Administrador | Propietario o encargado del negocio. Configura el sistema, registra compras, fija precios y consulta resultados. | Total
Cajero | Personal de atención. Registra ventas y opera la caja. | Restringido
Sistema | Procesos automáticos: respaldo diario, consulta de la tasa BCV, alertas. | Interno

Convenciones
Cada requisito tiene un identificador único con el formato RF-XX (funcional) o RNF-XX (no funcional). La prioridad se expresa como Alta (indispensable para la puesta en marcha), Media (necesaria para la aceptación) o Baja (deseable).
Decisiones estructurales que atraviesan todo el sistemaLos precios y costos se almacenan en dólares; los montos en bolívares siempre se calculan a partir de la tasa vigente y nunca se guardan como dato maestro, salvo el registro histórico de cada operación ya consumada.El precio exhibido al público incluye el IVA. La base imponible se obtiene por cálculo inverso.La existencia de un producto no es un campo actualizable, sino el resultado de la suma de sus movimientos de inventario.Cada línea de venta conserva copia del costo unitario vigente al momento de la operación.


2. REQUISITOS FUNCIONALES
Catálogo de productos
ID | Requisito | Prioridad
RF-01 | Registrar, modificar y desactivar productos con nombre, categoría, código de barras, alícuota de IVA, precio de venta, existencia mínima y control de vencimiento. | Alta
RF-02 | Impedir la eliminación física de productos con movimientos registrados. La baja es lógica mediante el campo de estado. | Alta
RF-03 | Admitir productos sin código de barras, identificables únicamente por nombre. | Alta
RF-04 | Buscar productos por código de barras (coincidencia exacta) y por nombre (coincidencia parcial), con resultados en menos de un segundo sobre un catálogo de 3.000 registros. | Alta
RF-05 | Agrupar productos en categorías, cada una con un margen objetivo propio que se aplica por defecto a sus productos. | Media
RF-06 | Clasificar cada producto según su alícuota de IVA: exento o gravado, con el porcentaje asociado. | Alta
RF-07 | Calcular el precio de venta a partir del margen objetivo, o calcular el margen resultante a partir de un precio introducido manualmente. | Alta
RF-08 | Recalcular en bloque los precios de una categoría al modificarse su margen objetivo, previa confirmación del administrador. | Media

Tasa de cambio
ID | Requisito | Prioridad
RF-09 | Registrar una única tasa por fecha, con indicación de su origen (automático o manual) y del usuario que la registró. | Alta
RF-10 | Consultar automáticamente la tasa oficial del BCV cuando exista conexión disponible, sin bloquear la operación si la consulta falla. | Media
RF-11 | Permitir la carga manual de la tasa en cualquier momento. | Alta
RF-12 | Exigir la tasa del día como condición para abrir la caja. Sin tasa vigente no se permite registrar ventas. | Alta
RF-13 | Conservar el histórico de tasas, de modo que las operaciones pasadas mantengan su valor original. | Alta

Compras y proveedores
ID | Requisito | Prioridad
RF-14 | Registrar proveedores con nombre, RIF y datos de contacto. | Media
RF-15 | Registrar la entrada de mercancía indicando proveedor, documento, fecha y detalle de productos. | Alta
RF-16 | Capturar en cada línea de compra la cantidad de presentaciones, las unidades por presentación y el costo de la presentación, calculando el costo unitario. | Alta
RF-17 | Admitir que un mismo producto se compre en presentaciones de distinto tamaño en compras diferentes. | Alta
RF-18 | Generar automáticamente los movimientos de entrada de inventario al confirmar una compra. | Alta
RF-19 | Registrar pagos parciales a proveedores y mantener el saldo pendiente por compra. | Media
RF-20 | Anular una compra generando movimientos inversos, sin eliminar el registro original. | Media
RF-21 | Solicitar la fecha de vencimiento en la compra de productos marcados con control de vencimiento, creando el lote correspondiente. | Media

Inventario
ID | Requisito | Prioridad
RF-22 | Calcular la existencia de cada producto como la suma de sus movimientos de inventario. | Alta
RF-23 | Registrar todo movimiento con tipo, cantidad, costo unitario, fecha, usuario y referencia a la operación que lo originó. | Alta
RF-24 | Alertar sobre los productos cuya existencia sea igual o inferior a su existencia mínima. | Alta
RF-25 | Registrar ajustes de inventario por conteo físico, dejando constancia de la cantidad del sistema, la contada, la diferencia, el motivo y el usuario autorizante. | Media
RF-26 | Restringir el ajuste de inventario al perfil administrador. | Alta
RF-27 | Impedir la venta de productos sin existencia suficiente, salvo autorización expresa del administrador. | Media

Pérdidas y vencimientos
ID | Requisito | Prioridad
RF-28 | Registrar pérdidas indicando producto, cantidad, motivo, fecha y observación. | Media
RF-29 | Ofrecer como motivos: vencido, dañado, faltante, merma de charcutería y consumo propio, ampliables por configuración. | Media
RF-30 | Valorizar cada pérdida al último costo de compra vigente y reflejarla en el resultado del período. | Media
RF-31 | Alertar sobre lotes cuya fecha de vencimiento se encuentre dentro del plazo de aviso configurado para el producto. | Media
RF-32 | Permitir dar de baja un lote vencido registrando directamente la pérdida asociada. | Media
RF-33 | Descontar preferentemente el lote de vencimiento más próximo en los productos con control de lote. | Media

Ventas y caja
ID | Requisito | Prioridad
RF-34 | Registrar ventas incorporando productos mediante lector de código de barras o búsqueda por nombre. | Alta
RF-35 | Mostrar en pantalla el detalle de la venta con totales en dólares y en bolívares actualizados a la tasa vigente. | Alta
RF-36 | Admitir el cobro combinado en efectivo en bolívares, efectivo en dólares, pago móvil, punto de venta y transferencia dentro de una misma venta. | Alta
RF-37 | Calcular el vuelto considerando la moneda entregada y la tasa vigente. | Alta
RF-38 | Asignar a cada venta un número correlativo irrepetible, que se conserva aun si la venta se anula. | Alta
RF-39 | Imprimir nota de entrega con datos fiscales del negocio, identificación del cliente cuando corresponda, detalle de la venta y desglose de base imponible, exento e IVA. | Alta
RF-40 | Registrar los datos fiscales del cliente (razón social y RIF) cuando la venta lo requiera. | Alta
RF-41 | Anular ventas mediante autorización con clave, generando los movimientos inversos de inventario y conservando el registro original. | Alta
RF-42 | Abrir la caja registrando el monto inicial en cada moneda. | Alta
RF-43 | Cerrar la caja comparando el monto contado con el esperado por medio de pago y registrando la diferencia. | Alta
RF-44 | Impedir el registro de ventas sin una sesión de caja abierta. | Alta
RF-45 | Asociar cada venta al usuario que la registró y a la sesión de caja correspondiente. | Alta

Gastos y resultados
ID | Requisito | Prioridad
RF-46 | Registrar gastos operativos con categoría, descripción, monto y período al que corresponden. | Media
RF-47 | Calcular la ganancia real de un período como las ventas, menos el costo de la mercancía vendida, menos las pérdidas, menos los gastos operativos. | Media

Reportes
ID | Requisito | Prioridad
RF-48 | Reporte de ventas por día y por rango de fechas, con totales por medio de pago. | Alta
RF-49 | Reporte de inventario valorizado al último costo. | Alta
RF-50 | Reporte de ganancia por producto y por categoría, en un rango de fechas. | Alta
RF-51 | Reporte de cierre de caja por sesión. | Alta
RF-52 | Libro de ventas con desglose de base imponible, exento e IVA, expresado en bolívares a la tasa de cada operación, en el formato requerido por el contador del cliente. | Alta
RF-53 | Reporte de pérdidas por período y por motivo. | Media
RF-54 | Reporte de productos próximos a vencer. | Media
RF-55 | Reporte de ganancia real del período incluyendo gastos operativos. | Media

Usuarios y seguridad
ID | Requisito | Prioridad
RF-56 | Autenticar a los usuarios mediante nombre de usuario y clave. | Alta
RF-57 | Disponer de dos perfiles: administrador y cajero. | Alta
RF-58 | Impedir al perfil cajero el acceso a costos, márgenes, reportes de ganancia, modificación de precios, ajustes de inventario y registro de compras. | Alta
RF-59 | Registrar en bitácora las operaciones sensibles: anulaciones, ajustes de inventario, cambios de precio y modificaciones de usuarios. | Media
RF-60 | Almacenar las claves cifradas mediante función de derivación con sal. | Alta

Respaldo y configuración
ID | Requisito | Prioridad
RF-61 | Ejecutar automáticamente un respaldo diario de la base de datos hacia la unidad externa configurada. | Alta
RF-62 | Registrar el resultado de cada respaldo y advertir al administrador cuando falle o cuando la unidad no esté disponible. | Alta
RF-63 | Permitir la restauración de un respaldo desde la propia aplicación. | Media
RF-64 | Configurar los datos fiscales del negocio, el logotipo, las alícuotas, el redondeo de precios y la ruta de respaldo. | Alta


3. REQUISITOS NO FUNCIONALES
ID | Requisito
RNF-01 | El sistema debe operar íntegramente sin conexión a internet. La única función que la requiere es la consulta automática de la tasa, que siempre tiene alternativa manual.
RNF-02 | El registro de una línea de venta mediante lector no debe superar los 300 milisegundos desde la lectura hasta su aparición en pantalla.
RNF-03 | La búsqueda de productos por nombre debe responder en menos de un segundo sobre un catálogo de 3.000 registros.
RNF-04 | La generación de cualquier reporte de un mes de operación no debe superar los cinco segundos.
RNF-05 | Todo importe monetario debe representarse con tipos de dato decimales de precisión fija. Queda prohibido el uso de punto flotante para cálculos monetarios.
RNF-06 | Toda operación que afecte inventario y venta debe ejecutarse dentro de una transacción única, de modo que un corte de energía no deje registros parciales.
RNF-07 | La base de datos debe soportar la interrupción abrupta del equipo sin corrupción, mediante registro de transacciones activo.
RNF-08 | La interfaz de venta debe ser operable íntegramente por teclado, sin necesidad de mouse.
RNF-09 | Los mensajes de error deben indicar la acción correctiva en lenguaje comprensible para el usuario final, sin exponer detalles técnicos.
RNF-10 | El sistema debe funcionar en el equipo previsto por el cliente: procesador de gama media, 8 GB de memoria y disco de estado sólido.
RNF-11 | La instalación debe realizarse mediante un único instalador, sin requerir configuración manual de servicios por parte del cliente.
RNF-12 | El respaldo diario debe ejecutarse sin intervención del usuario y sin interrumpir la operación.
RNF-13 | La aplicación debe registrar sus errores en un archivo de bitácora consultable para el diagnóstico remoto.
RNF-14 | Todas las fechas y horas deben almacenarse en la zona horaria local, de forma consistente en toda la aplicación.

4. FLUJOS PRINCIPALES
4.1 Venta
Paso | Acción
1 | El cajero inicia sesión y verifica que exista una sesión de caja abierta y tasa del día registrada.
2 | Lee el código de barras de cada producto o lo busca por nombre; el sistema agrega la línea con su precio vigente.
3 | El sistema muestra el total en dólares y su equivalente en bolívares a la tasa del día.
4 | El cajero registra uno o varios medios de pago hasta cubrir el total.
5 | El sistema calcula el vuelto, confirma la venta, descuenta las existencias e imprime la nota de entrega.
6 | Si el cliente requiere comprobante con datos fiscales, estos se capturan antes de confirmar.

4.2 Entrada de mercancía
Paso | Acción
1 | El administrador crea la compra indicando proveedor, documento y fecha.
2 | Por cada producto registra cantidad de presentaciones, unidades por presentación y costo de la presentación.
3 | El sistema calcula el costo unitario y, si el producto controla vencimiento, solicita la fecha y crea el lote.
4 | Al confirmar, el sistema genera los movimientos de entrada y actualiza el último costo de cada producto.
5 | El sistema advierte cuáles productos quedaron con un precio de venta que ya no cubre el margen objetivo.

4.3 Cierre de caja
Paso | Acción
1 | El usuario solicita el cierre de la sesión activa.
2 | El sistema calcula el monto esperado por medio de pago a partir de las ventas de la sesión.
3 | El usuario registra el conteo físico de efectivo en cada moneda.
4 | El sistema calcula la diferencia, la registra y emite el reporte de cierre.


5. ARQUITECTURA TÉCNICA
Esta sección documenta las decisiones tecnológicas adoptadas y su justificación. No forma parte de las obligaciones contractuales: el cliente contrató un resultado, no una tecnología determinada. Se incluye aquí para que las decisiones queden registradas y sean revisables.
5.1 Componentes
Capa | Tecnología | Motivo
Lenguaje | Python 3.12 | Tipo Decimal nativo, exigido por RNF-05. Se descarta la versión 3.13 por madurez de las dependencias.
Interfaz | PySide6 (Qt 6) | Aplicación de escritorio con navegación completa por teclado (RNF-08) y tablas de alto rendimiento.
Base de datos | SQLite en modo WAL | Archivo único sin servicio que instalar (RNF-11) y resistencia a cortes abruptos (RNF-07).
Acceso a datos | Módulo sqlite3 de la biblioteca estándar, con repositorios y SQL escrito a mano | El modelo ya está definido; un ORM añadiría capas sin beneficio.
Impresión | python-escpos | Envío directo de comandos a la impresora térmica, sin diálogo de impresión del sistema operativo.
Reportes | reportlab | Generación de PDF para el libro de ventas y los reportes de cierre.
Empaquetado | PyInstaller en modo onedir | Arranque más rápido que el modo de archivo único y permite reemplazar archivos sueltos en una actualización.
Instalador | Inno Setup | Instalador único para Windows, con acceso directo y desinstalador (RNF-11).
Pruebas | pytest | Verificación automatizada de las reglas de negocio.

PySide6 y no PyQt6Ambas bibliotecas ofrecen prácticamente la misma interfaz de programación, pero su licencia difiere. PyQt se distribuye bajo GPL o licencia comercial de pago: utilizarla obligaría a liberar el código fuente del sistema o a adquirir una licencia.PySide6 se distribuye bajo LGPL, lo que permite su uso en software propietario mientras se enlace de forma dinámica, que es el comportamiento de una instalación normal. Dado que el código no se entrega al cliente conforme a la Cláusula 11.1 del contrato, PySide6 es la única opción viable sin costo de licencia.

5.2 Representación de importes
SQLite carece de tipo decimal nativo. Los importes se almacenan como enteros escalados y se convierten a Decimal en la capa de acceso a datos. El resto de la aplicación nunca manipula el entero directamente.
Magnitud | Decimales | Factor de escala | Ejemplo
Precios y costos unitarios | 4 | 10.000 | 0,7800 USD se almacena como 7800
Totales monetarios | 2 | 100 | 4,76 USD se almacena como 476
Cantidades | 3 | 1.000 | 2,500 unidades se almacena como 2500
Tasa de cambio | 6 | 1.000.000 | 210,500000 se almacena como 210500000
Porcentajes | 2 | 100 | 16,00 % se almacena como 1600

Dos comportamientos de Python que contradicen la especificaciónEl módulo decimal redondea por defecto con el modo ROUND_HALF_EVEN, conocido como redondeo bancario. La regla RN de redondeo exige medio hacia arriba. Debe declararse ROUND_HALF_UP de forma explícita en cada operación de cuantización, encapsulada en una única función del módulo de dinero.El respaldo no puede hacerse copiando el archivo de base de datos: con el modo WAL activo, la copia puede resultar inconsistente. Debe emplearse el método backup de la conexión sqlite3, que realiza una copia en caliente correcta.

5.3 Organización del código
La aplicación se estructura en capas, con una regla de dependencia estricta: el dominio no importa nada de las demás capas.
minimarket/
    dominio/      Entidades y reglas de cálculo puras. Sin SQL ni interfaz.
    datos/        Esquema, migraciones y repositorios de acceso a SQLite.
    servicios/    Casos de uso que coordinan dominio y datos en transacciones.
    ui/           Ventanas y diálogos PySide6.
    infra/        Impresora, consulta de tasa, respaldo, bitácora y configuración.
    tests/        Pruebas automatizadas.
Las fórmulas del documento de Reglas de Negocio se implementan exclusivamente en la capa de dominio y se verifican con los ejemplos numéricos allí especificados. Si el resultado difiere del ejemplo, el error está en el código, no en la especificación.
5.4 Dispositivos
Dispositivo | Integración
Lector de código de barras | Se comporta como teclado. Se implementa mediante un campo con foco permanente y detección de tecleo rápido seguido de retorno de carro. No requiere biblioteca ni controlador.
Impresora térmica | Comandos ESC/POS enviados directamente al dispositivo. En Windows se emplea la interfaz de impresión sin procesamiento.
Gaveta de dinero | Apertura mediante el pulso enviado por la impresora de comprobantes.
Balanza y máquina fiscal | Fuera de alcance en esta versión. La arquitectura reserva la capa de infraestructura para su incorporación futura por puerto serie.

6. FUERA DE ALCANCE
Los siguientes puntos no forman parte de esta versión, conforme a la Cláusula tercera del contrato. Se enumeran aquí porque el diseño debe preverlos sin implementarlos.
Venta por peso con balanza y códigos de barra de peso variable. El modelo de datos contempla cantidades decimales para no impedir su incorporación futura.
Segunda lista de precios para venta al mayor.
Ofertas, combos y descuentos promocionales.
Productos preparados a partir de otros productos del inventario.
Integración con máquina fiscal. La estructura del comprobante debe separar base imponible, exento e IVA para permitirla más adelante.
Ventas a crédito y cuentas por cobrar.
Operación multisucursal y acceso remoto.
Exportación de reportes a Excel.
Criterio de aceptación generalSe considera cumplido un requisito cuando puede demostrarse su funcionamiento sobre datos reales del cliente, no sobre datos de prueba. La validación final se realizará con el catálogo cargado y una sesión de caja completa, conforme a la Cláusula novena del contrato.
