# ============================================================
#  Sistema de Prestamos - Python basico
#  Solo funciones, listas y matrices (listas de listas).
#  Unico modulo: json (para guardar/cargar datos).
# ============================================================

import json

# ---------- "Matrices": listas de listas ----------
clientes = []    # fila: [id, nombre, dni, telefono]
prestamos = []   # fila: [id, id_cliente, capital, tasa_mensual, n_cuotas, sistema, estado]
cuotas = []      # fila: [id, id_prestamo, nro, monto, pagada(0/1), pagado]
pagos = []       # fila: [id, id_cuota, monto, fecha]

# ---------- Constantes de indice (para no usar numeros magicos) ----------
C_ID, C_NOMBRE, C_DNI, C_TEL = 0, 1, 2, 3
P_ID, P_CLIENTE, P_CAPITAL, P_TASA, P_NCUOTAS, P_SISTEMA, P_ESTADO = 0, 1, 2, 3, 4, 5, 6
CU_ID, CU_PRESTAMO, CU_NRO, CU_MONTO, CU_PAGADA, CU_PAGADO = 0, 1, 2, 3, 4, 5
PG_ID, PG_CUOTA, PG_MONTO, PG_FECHA = 0, 1, 2, 3

TASA_MORA = 0.01   # 1% por dia de atraso sobre el monto de la cuota
ARCHIVO = "datos_prestamos.json"


# ============================================================
#  Helpers de entrada
# ============================================================
def leer_texto(mensaje):
    texto = input(mensaje).strip()
    while texto == "":
        print("No puede quedar vacio.")
        texto = input(mensaje).strip()
    return texto


def leer_int(mensaje):
    while True:
        try:
            return int(input(mensaje))
        except ValueError:
            print("Valor invalido, ingresa un numero entero.")


def leer_float(mensaje):
    while True:
        try:
            return float(input(mensaje))
        except ValueError:
            print("Valor invalido, ingresa un numero.")


def nuevo_id(matriz):
    mayor = 0
    for fila in matriz:
        if fila[0] > mayor:
            mayor = fila[0]
    return mayor + 1


# ============================================================
#  Calculo de cuotas
# ============================================================
def calcular_cuota_simple(capital, tasa, n):
    total = capital + capital * tasa * n
    return total / n


def calcular_cuota_frances(capital, tasa, n):
    if tasa == 0:
        return capital / n
    i = tasa
    return capital * (i * (1 + i) ** n) / ((1 + i) ** n - 1)


# ============================================================
#  Clientes
# ============================================================
def buscar_cliente_por_dni(dni):
    for c in clientes:
        if c[C_DNI] == dni:
            return c
    return None


def buscar_cliente_por_id(id_cliente):
    for c in clientes:
        if c[C_ID] == id_cliente:
            return c
    return None


def registrar_cliente():
    print("\n--- Registrar cliente ---")
    dni = leer_texto("DNI: ")
    if buscar_cliente_por_dni(dni) is not None:
        print("Ya existe un cliente con ese DNI.")
        return
    nombre = leer_texto("Nombre y apellido: ")
    telefono = leer_texto("Telefono: ")
    fila = [nuevo_id(clientes), nombre, dni, telefono]
    clientes.append(fila)
    print("Cliente registrado con ID", fila[C_ID])


def listar_clientes():
    print("\n--- Clientes ---")
    if len(clientes) == 0:
        print("No hay clientes cargados.")
        return
    for c in clientes:
        print("ID", c[C_ID], "|", c[C_NOMBRE], "| DNI", c[C_DNI], "| Tel", c[C_TEL])


# ============================================================
#  Prestamos
# ============================================================
def buscar_prestamo_por_id(id_prestamo):
    for p in prestamos:
        if p[P_ID] == id_prestamo:
            return p
    return None


def generar_cuotas(id_prestamo, monto_cuota, n):
    for nro in range(1, n + 1):
        fila = [nuevo_id(cuotas), id_prestamo, nro, round(monto_cuota, 2), 0, 0.0]
        cuotas.append(fila)


def registrar_prestamo():
    print("\n--- Registrar prestamo ---")
    if len(clientes) == 0:
        print("Primero registra al menos un cliente.")
        return
    dni = leer_texto("DNI del cliente: ")
    cliente = buscar_cliente_por_dni(dni)
    if cliente is None:
        print("No existe un cliente con ese DNI.")
        return

    capital = leer_float("Capital prestado: ")
    tasa_pct = leer_float("Tasa mensual (%): ")
    tasa = tasa_pct / 100
    n = leer_int("Cantidad de cuotas: ")
    if n <= 0 or capital <= 0:
        print("Capital y cuotas deben ser mayores a cero.")
        return

    print("Sistema de interes: 1) Simple   2) Frances")
    op = leer_int("Opcion: ")
    if op == 2:
        sistema = "frances"
        cuota = calcular_cuota_frances(capital, tasa, n)
    else:
        sistema = "simple"
        cuota = calcular_cuota_simple(capital, tasa, n)

    fila = [nuevo_id(prestamos), cliente[C_ID], capital, tasa, n, sistema, "activo"]
    prestamos.append(fila)
    generar_cuotas(fila[P_ID], cuota, n)

    print("Prestamo registrado con ID", fila[P_ID])
    print("Cuota:", round(cuota, 2), "| Total a pagar:", round(cuota * n, 2))


def listar_prestamos():
    print("\n--- Prestamos ---")
    if len(prestamos) == 0:
        print("No hay prestamos cargados.")
        return
    for p in prestamos:
        cliente = buscar_cliente_por_id(p[P_CLIENTE])
        nombre = cliente[C_NOMBRE] if cliente else "?"
        print("ID", p[P_ID], "|", nombre, "| Capital", p[P_CAPITAL],
              "| Cuotas", p[P_NCUOTAS], "|", p[P_SISTEMA], "|", p[P_ESTADO],
              "| Saldo", round(saldo_pendiente(p[P_ID]), 2))


# ============================================================
#  Cuotas y pagos
# ============================================================
def cuotas_de_prestamo(id_prestamo):
    resultado = []
    for c in cuotas:
        if c[CU_PRESTAMO] == id_prestamo:
            resultado.append(c)
    return resultado


def saldo_pendiente(id_prestamo):
    total = 0.0
    for c in cuotas:
        if c[CU_PRESTAMO] == id_prestamo and c[CU_PAGADA] == 0:
            total = total + c[CU_MONTO]
    return total


def actualizar_estado(id_prestamo):
    if saldo_pendiente(id_prestamo) <= 0:
        p = buscar_prestamo_por_id(id_prestamo)
        if p is not None:
            p[P_ESTADO] = "pagado"


def calcular_mora(monto_cuota, dias_atraso):
    return monto_cuota * TASA_MORA * dias_atraso


def registrar_pago():
    print("\n--- Registrar pago ---")
    id_prestamo = leer_int("ID del prestamo: ")
    p = buscar_prestamo_por_id(id_prestamo)
    if p is None:
        print("No existe ese prestamo.")
        return

    pendientes = []
    for c in cuotas_de_prestamo(id_prestamo):
        if c[CU_PAGADA] == 0:
            pendientes.append(c)
    if len(pendientes) == 0:
        print("Este prestamo no tiene cuotas pendientes.")
        return

    print("Cuotas pendientes:")
    for c in pendientes:
        print("  Cuota", c[CU_NRO], "-> $", c[CU_MONTO])

    nro = leer_int("Numero de cuota a pagar: ")
    cuota = None
    for c in pendientes:
        if c[CU_NRO] == nro:
            cuota = c
            break
    if cuota is None:
        print("Esa cuota no esta pendiente.")
        return

    dias = leer_int("Dias de atraso (0 si esta al dia): ")
    mora = calcular_mora(cuota[CU_MONTO], dias)
    total = cuota[CU_MONTO] + mora
    if mora > 0:
        print("Recargo por mora:", round(mora, 2))
    print("Total a pagar:", round(total, 2))

    fecha = leer_texto("Fecha de pago (ej 02/06/2026): ")
    cuota[CU_PAGADA] = 1
    cuota[CU_PAGADO] = round(total, 2)
    pagos.append([nuevo_id(pagos), cuota[CU_ID], round(total, 2), fecha])
    actualizar_estado(id_prestamo)
    print("Pago registrado. Saldo restante:", round(saldo_pendiente(id_prestamo), 2))


# ============================================================
#  Consultas y reportes
# ============================================================
def ver_deudas_activas():
    print("\n--- Deudas activas ---")
    hay = False
    for p in prestamos:
        saldo = saldo_pendiente(p[P_ID])
        if saldo > 0:
            hay = True
            cliente = buscar_cliente_por_id(p[P_CLIENTE])
            nombre = cliente[C_NOMBRE] if cliente else "?"
            print("Prestamo", p[P_ID], "|", nombre, "| Debe $", round(saldo, 2))
    if not hay:
        print("No hay deudas activas.")


def buscar():
    print("\n--- Buscar ---")
    print("1) Cliente por DNI   2) Prestamos por DNI")
    op = leer_int("Opcion: ")
    dni = leer_texto("DNI: ")
    cliente = buscar_cliente_por_dni(dni)
    if cliente is None:
        print("No se encontro el cliente.")
        return
    print("Cliente:", cliente[C_NOMBRE], "| Tel", cliente[C_TEL])
    if op == 2:
        encontrados = False
        for p in prestamos:
            if p[P_CLIENTE] == cliente[C_ID]:
                encontrados = True
                print("  Prestamo", p[P_ID], "| Saldo $", round(saldo_pendiente(p[P_ID]), 2),
                      "|", p[P_ESTADO])
        if not encontrados:
            print("  Sin prestamos.")


def reporte_cliente():
    print("\n--- Reporte por cliente ---")
    dni = leer_texto("DNI: ")
    cliente = buscar_cliente_por_dni(dni)
    if cliente is None:
        print("No se encontro el cliente.")
        return
    print("Cliente:", cliente[C_NOMBRE], "| DNI", cliente[C_DNI])
    total_deuda = 0.0
    for p in prestamos:
        if p[P_CLIENTE] == cliente[C_ID]:
            saldo = saldo_pendiente(p[P_ID])
            total_deuda = total_deuda + saldo
            print("\n  Prestamo", p[P_ID], "(", p[P_SISTEMA], ") - Estado:", p[P_ESTADO])
            for c in cuotas_de_prestamo(p[P_ID]):
                estado = "PAGADA" if c[CU_PAGADA] == 1 else "pendiente"
                print("    Cuota", c[CU_NRO], "$", c[CU_MONTO], "->", estado)
    print("\n  Deuda total del cliente: $", round(total_deuda, 2))


# ============================================================
#  Persistencia (json)
# ============================================================
def guardar_datos():
    datos = {"clientes": clientes, "prestamos": prestamos,
             "cuotas": cuotas, "pagos": pagos}
    archivo = open(ARCHIVO, "w", encoding="utf-8")
    json.dump(datos, archivo, ensure_ascii=False, indent=2)
    archivo.close()
    print("Datos guardados en", ARCHIVO)


def cargar_datos():
    global clientes, prestamos, cuotas, pagos
    try:
        archivo = open(ARCHIVO, "r", encoding="utf-8")
        datos = json.load(archivo)
        archivo.close()
        clientes = datos["clientes"]
        prestamos = datos["prestamos"]
        cuotas = datos["cuotas"]
        pagos = datos["pagos"]
        print("Datos cargados desde", ARCHIVO)
    except FileNotFoundError:
        print("No hay archivo de datos todavia.")


# ============================================================
#  Menu principal
# ============================================================
def menu():
    print("\n==============================")
    print("   SISTEMA DE PRESTAMOS")
    print("==============================")
    print("1. Registrar cliente")
    print("2. Listar clientes")
    print("3. Registrar prestamo")
    print("4. Listar prestamos")
    print("5. Registrar pago")
    print("6. Ver deudas activas")
    print("7. Buscar")
    print("8. Reporte por cliente")
    print("9. Guardar datos")
    print("10. Cargar datos")
    print("0. Salir")


def main():
    while True:
        menu()
        op = leer_int("Opcion: ")
        if op == 1:
            registrar_cliente()
        elif op == 2:
            listar_clientes()
        elif op == 3:
            registrar_prestamo()
        elif op == 4:
            listar_prestamos()
        elif op == 5:
            registrar_pago()
        elif op == 6:
            ver_deudas_activas()
        elif op == 7:
            buscar()
        elif op == 8:
            reporte_cliente()
        elif op == 9:
            guardar_datos()
        elif op == 10:
            cargar_datos()
        elif op == 0:
            print("Hasta luego!")
            break
        else:
            print("Opcion invalida.")


main()