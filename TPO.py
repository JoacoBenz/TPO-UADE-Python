# ============================================================
#  Sistema de Prestamos - Python basico
#  Solo funciones y listas de listas. Sin memoria (volatil).
# ============================================================

# Listas donde se guardan los datos mientras el programa corre.
clientes = []    # [id, nombre, dni, telefono]
prestamos = []   # [id, id_cliente, capital, tasa, cuotas, sistema, estado]
cuotas = []      # [id_prestamo, numero, monto, pagada]

TASA_MORA = 0.01   # 1% por dia de atraso


# ============================================================
#  Calculo de cuotas
# ============================================================
def calcular_cuota_simple(capital, tasa, n):
    total = capital + capital * tasa * n
    return total / n


def calcular_cuota_frances(capital, tasa, n):
    if tasa == 0:
        return capital / n
    return capital * (tasa * (1 + tasa) ** n) / ((1 + tasa) ** n - 1)


# ============================================================
#  Saldo pendiente de un prestamo
# ============================================================
def saldo_pendiente(id_prestamo):
    total = 0.0
    for c in cuotas:
        if c[0] == id_prestamo and c[3] == 0:
            total = total + c[2]
    return total


# ============================================================
#  Clientes
# ============================================================
def registrar_cliente():
    print("\n--- Registrar cliente ---")
    nombre = input("Nombre y apellido: ")
    dni = input("DNI: ")
    telefono = input("Telefono: ")
    id_cliente = len(clientes) + 1
    clientes.append([id_cliente, nombre, dni, telefono])
    print("Cliente registrado con ID", id_cliente)


def listar_clientes():
    print("\n--- Clientes ---")
    if len(clientes) == 0:
        print("No hay clientes cargados.")
    for c in clientes:
        print("ID", c[0], "|", c[1], "| DNI", c[2], "| Tel", c[3])


# ============================================================
#  Prestamos
# ============================================================
def registrar_prestamo():
    print("\n--- Registrar prestamo ---")
    if len(clientes) == 0:
        print("Primero registra al menos un cliente.")
        return

    dni = input("DNI del cliente: ")
    cliente = None
    for c in clientes:
        if c[2] == dni:
            cliente = c
    if cliente == None:
        print("No existe un cliente con ese DNI.")
        return

    capital = float(input("Capital prestado: "))
    tasa_pct = float(input("Tasa mensual (%): "))
    tasa = tasa_pct / 100
    n = int(input("Cantidad de cuotas: "))

    print("Sistema de interes: 1) Simple   2) Frances")
    op = int(input("Opcion: "))
    if op == 2:
        sistema = "frances"
        cuota = calcular_cuota_frances(capital, tasa, n)
    else:
        sistema = "simple"
        cuota = calcular_cuota_simple(capital, tasa, n)

    id_prestamo = len(prestamos) + 1
    prestamos.append([id_prestamo, cliente[0], capital, tasa, n, sistema, "activo"])

    numero = 1
    while numero <= n:
        cuotas.append([id_prestamo, numero, round(cuota, 2), 0])
        numero = numero + 1

    print("Prestamo registrado con ID", id_prestamo)
    print("Cuota:", round(cuota, 2), "| Total a pagar:", round(cuota * n, 2))


def listar_prestamos():
    print("\n--- Prestamos ---")
    if len(prestamos) == 0:
        print("No hay prestamos cargados.")
    for p in prestamos:
        print("ID", p[0], "| Cliente", p[1], "| Capital", p[2],
              "| Cuotas", p[4], "|", p[5], "|", p[6],
              "| Saldo", round(saldo_pendiente(p[0]), 2))


# ============================================================
#  Pagos
# ============================================================
def registrar_pago():
    print("\n--- Registrar pago ---")
    id_prestamo = int(input("ID del prestamo: "))

    print("Cuotas pendientes:")
    hay = False
    for c in cuotas:
        if c[0] == id_prestamo and c[3] == 0:
            hay = True
            print("  Cuota", c[1], "-> $", c[2])
    if hay == False:
        print("No hay cuotas pendientes para ese prestamo.")
        return

    nro = int(input("Numero de cuota a pagar: "))
    cuota = None
    for c in cuotas:
        if c[0] == id_prestamo and c[1] == nro and c[3] == 0:
            cuota = c
    if cuota == None:
        print("Esa cuota no esta pendiente.")
        return

    dias = int(input("Dias de atraso (0 si esta al dia): "))
    mora = cuota[2] * TASA_MORA * dias
    total = cuota[2] + mora
    if mora > 0:
        print("Recargo por mora:", round(mora, 2))
    print("Total a pagar:", round(total, 2))

    cuota[3] = 1

    # Si no queda saldo, el prestamo pasa a "pagado"
    if saldo_pendiente(id_prestamo) <= 0:
        for p in prestamos:
            if p[0] == id_prestamo:
                p[6] = "pagado"

    print("Pago registrado. Saldo restante:", round(saldo_pendiente(id_prestamo), 2))


# ============================================================
#  Consultas
# ============================================================
def ver_deudas_activas():
    print("\n--- Deudas activas ---")
    hay = False
    for p in prestamos:
        saldo = saldo_pendiente(p[0])
        if saldo > 0:
            hay = True
            print("Prestamo", p[0], "| Cliente", p[1], "| Debe $", round(saldo, 2))
    if hay == False:
        print("No hay deudas activas.")


def reporte_cliente():
    print("\n--- Reporte por cliente ---")
    dni = input("DNI: ")
    cliente = None
    for c in clientes:
        if c[2] == dni:
            cliente = c
    if cliente == None:
        print("No se encontro el cliente.")
        return

    print("Cliente:", cliente[1], "| DNI", cliente[2])
    total_deuda = 0.0
    for p in prestamos:
        if p[1] == cliente[0]:
            saldo = saldo_pendiente(p[0])
            total_deuda = total_deuda + saldo
            print("\n  Prestamo", p[0], "(", p[5], ") - Estado:", p[6])
            for c in cuotas:
                if c[0] == p[0]:
                    if c[3] == 1:
                        estado = "PAGADA"
                    else:
                        estado = "pendiente"
                    print("    Cuota", c[1], "$", c[2], "->", estado)
    print("\n  Deuda total del cliente: $", round(total_deuda, 2))


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
    print("7. Reporte por cliente")
    print("0. Salir")


def main():
    while True:
        menu()
        op = int(input("Opcion: "))
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
            reporte_cliente()
        elif op == 0:
            print("Hasta luego!")
            break
        else:
            print("Opcion invalida.")


main()
