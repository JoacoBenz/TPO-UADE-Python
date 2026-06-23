# ============================================================
#  Sistema de Prestamos
# ============================================================

import os 


# Listas donde se guardan los datos mientras el programa corre.
clientes = []    # [id, nombre, dni, telefono]
prestamos = []   # [id, id_cliente, capital, tasa, cuotas, sistema, estado]
cuotas = []      # [id_prestamo, numero, monto, pagada]

TASA_MORA = 0.01   # 1% por dia de atraso


# ============================================================
#  Calculo de cuotas
# ============================================================
# Calcula la cuota fija con interes simple sobre el capital.
def calcular_cuota_simple(capital, tasa, n):
    total = capital + capital * tasa * n
    return total / n


# Calcula la cuota fija con sistema frances (interes sobre saldo).
def calcular_cuota_frances(capital, tasa, n):
    if tasa == 0:
        return capital / n
    return capital * (tasa * (1 + tasa) ** n) / ((1 + tasa) ** n - 1)


# ============================================================
#  Saldo pendiente de un prestamo
# ============================================================
# Suma el monto de las cuotas todavia impagas de un prestamo.
def saldo_pendiente(id_prestamo):
    total = 0.0
    for c in cuotas:
        if c[0] == id_prestamo and c[3] == 0:
            total = total + c[2]
    return total


# ============================================================
#  Clientes
# ============================================================
# Pide los datos de un cliente, los valida y lo agrega a la lista.
def registrar_cliente():
    titulo("REGISTRAR CLIENTE")
    print("  Complete los datos del nuevo cliente:")
    print("")

    nombre = input("   Nombre y apellido : ")
    while nombre == "":
        print("   !! El nombre no puede estar vacio.")
        nombre = input("   Nombre y apellido : ")

    dni = input("   DNI              : ")
    valido = False
    while valido == False:
        valido = True
        if dni == "":
            valido = False
        for letra in dni:
            if letra < "0" or letra > "9":
                valido = False
        if valido == False:
            print("   !! El DNI debe ser un numero.")
            dni = input("   DNI              : ")

    telefono = input("   Telefono         : ")
    valido = False
    while valido == False:
        valido = True
        if telefono == "":
            valido = False
        for letra in telefono:
            if letra < "0" or letra > "9":
                valido = False
        if valido == False:
            print("   !! El telefono debe ser un numero.")
            telefono = input("   Telefono         : ")

    id_cliente = len(clientes) + 1
    clientes.append([id_cliente, nombre, dni, telefono])
    print("")
    print("  +--------------------------------------+")
    print("  |  Cliente registrado correctamente    |")
    print("  +--------------------------------------+")
    print("   ID asignado :", id_cliente)
    print("   Nombre      :", nombre)
    print("   DNI         :", dni)


# Muestra en una tabla todos los clientes cargados.
def listar_clientes():
    titulo("CLIENTES")
    if len(clientes) == 0:
        print("No hay clientes cargados.")
        return
    print("  ID  | Nombre                 | DNI         | Telefono")
    print("  " + "-" * 56)
    for c in clientes:
        print("  " + str(c[0]).ljust(3),
              "|", c[1].ljust(22),
              "|", c[2].ljust(11),
              "|", c[3])


# ============================================================
#  Prestamos
# ============================================================
# Pide los datos del prestamo, calcula la cuota y genera el plan de cuotas.
def registrar_prestamo():
    titulo("REGISTRAR PRESTAMO")
    if len(clientes) == 0:
        print("!! Primero registra al menos un cliente.")
        return

    print("  Complete los datos del prestamo:")
    print("")

    dni = input("   DNI del cliente   : ")
    cliente = None
    for c in clientes:
        if c[2] == dni:
            cliente = c
    if cliente == None:
        print("   !! No existe un cliente con ese DNI.")
        return
    print("   Cliente: " + cliente[1])
    print("")

    entrada = input("   Capital prestado  : ")
    valido = False
    while valido == False:
        valido = True
        puntos = 0
        if entrada == "":
            valido = False
        for letra in entrada:
            if letra == ".":
                puntos = puntos + 1
            elif letra < "0" or letra > "9":
                valido = False
        if puntos > 1:
            valido = False
        if valido == False:
            print("   !! El capital debe ser un numero mayor a 0.")
            entrada = input("   Capital prestado  : ")
    capital = float(entrada)

    entrada = input("   Tasa mensual (%)  : ")
    valido = False
    while valido == False:
        valido = True
        puntos = 0
        if entrada == "":
            valido = False
        for letra in entrada:
            if letra == ".":
                puntos = puntos + 1
            elif letra < "0" or letra > "9":
                valido = False
        if puntos > 1:
            valido = False
        if valido == False:
            print("   !! La tasa debe ser un numero.")
            entrada = input("   Tasa mensual (%)  : ")
    tasa_pct = float(entrada)
    tasa = tasa_pct / 100

    entrada = input("   Cantidad de cuotas: ")
    valido = False
    while valido == False:
        valido = True
        if entrada == "":
            valido = False
        for letra in entrada:
            if letra < "0" or letra > "9":
                valido = False
        if valido == True and int(entrada) <= 0:
            valido = False
        if valido == False:
            print("   !! La cantidad de cuotas debe ser un numero entero mayor a 0.")
            entrada = input("   Cantidad de cuotas: ")
    n = int(entrada)

    print("")
    print("   Sistema de interes:  [1] Simple   [2] Frances")
    entrada = input("   Opcion            : ")
    while entrada != "1" and entrada != "2":
        print("   !! Opcion invalida. Ingrese 1 o 2.")
        entrada = input("   Opcion            : ")
    op = int(entrada)
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

    print("")
    print("  +--------------------------------------+")
    print("  |  Prestamo registrado correctamente   |")
    print("  +--------------------------------------+")
    print("   ID asignado    :", id_prestamo)
    print("   Sistema        :", sistema)
    print("   Cantidad cuotas:", n)
    print("   Valor de cuota : $", round(cuota, 2))
    print("   Total a pagar  : $", round(cuota * n, 2))


# Muestra en una tabla todos los prestamos con su saldo actual.
def listar_prestamos():
    titulo("PRESTAMOS")
    if len(prestamos) == 0:
        print("No hay prestamos cargados.")
        return
    print("  ID | Cli | Capital    | Cuotas | Sistema  | Estado   | Saldo")
    print("  " + "-" * 62)
    for p in prestamos:
        print("  " + str(p[0]).ljust(2),
              "|", str(p[1]).ljust(3),
              "|", ("$ " + str(p[2])).ljust(10),
              "|", str(p[4]).ljust(6),
              "|", p[5].ljust(8),
              "|", p[6].ljust(8),
              "| $", round(saldo_pendiente(p[0]), 2))


# ============================================================
#  Pagos
# ============================================================
# Registra el pago de una cuota, aplica la mora y actualiza el estado.
def registrar_pago():
    titulo("REGISTRAR PAGO")
    print("")
    entrada = input("   ID del prestamo : ")
    valido = False
    while valido == False:
        valido = True
        if entrada == "":
            valido = False
        for letra in entrada:
            if letra < "0" or letra > "9":
                valido = False
        if valido == False:
            print("   !! El ID debe ser un numero.")
            entrada = input("   ID del prestamo : ")
    id_prestamo = int(entrada)

    print("")
    print("   Cuotas pendientes:")
    hay = False
    for c in cuotas:
        if c[0] == id_prestamo and c[3] == 0:
            hay = True
            print("     - Cuota", str(c[1]).ljust(3), "-> $", c[2])
    if hay == False:
        print("   !! No hay cuotas pendientes para ese prestamo.")
        return

    print("")
    entrada = input("   Numero de cuota : ")
    valido = False
    while valido == False:
        valido = True
        if entrada == "":
            valido = False
        for letra in entrada:
            if letra < "0" or letra > "9":
                valido = False
        if valido == False:
            print("   !! El numero de cuota debe ser un numero.")
            entrada = input("   Numero de cuota : ")
    nro = int(entrada)
    cuota = None
    for c in cuotas:
        if c[0] == id_prestamo and c[1] == nro and c[3] == 0:
            cuota = c
    if cuota == None:
        print("   !! Esa cuota no esta pendiente.")
        return

    entrada = input("   Dias de atraso  : ")
    valido = False
    while valido == False:
        valido = True
        if entrada == "":
            valido = False
        for letra in entrada:
            if letra < "0" or letra > "9":
                valido = False
        if valido == False:
            print("   !! Los dias deben ser un numero (0 o mas).")
            entrada = input("   Dias de atraso  : ")
    dias = int(entrada)
    mora = cuota[2] * TASA_MORA * dias
    total = cuota[2] + mora
    print("")
    if mora > 0:
        print("   Recargo por mora: $", round(mora, 2))
    print("   Total a pagar:    $", round(total, 2))

    cuota[3] = 1

    # Si no queda saldo, el prestamo pasa a "pagado"
    if saldo_pendiente(id_prestamo) <= 0:
        for p in prestamos:
            if p[0] == id_prestamo:
                p[6] = "pagado"

    saldo = saldo_pendiente(id_prestamo)
    print("")
    print("  +--------------------------------------+")
    print("  |  Pago registrado correctamente       |")
    print("  +--------------------------------------+")
    print("   Cuota pagada   :", nro)
    print("   Saldo restante : $", round(saldo, 2))
    if saldo <= 0:
        print("   El prestamo quedo TOTALMENTE PAGADO.")


# ============================================================
#  Consultas
# ============================================================
# Lista los prestamos que todavia tienen saldo pendiente.
def ver_deudas_activas():
    titulo("DEUDAS ACTIVAS")
    hay = False
    for p in prestamos:
        saldo = saldo_pendiente(p[0])
        if saldo > 0:
            if hay == False:
                print("  Prestamo | Cliente | Debe")
                print("  " + "-" * 32)
            hay = True
            print("  " + str(p[0]).ljust(8),
                  "|", str(p[1]).ljust(7),
                  "| $", round(saldo, 2))
    if hay == False:
        print("No hay deudas activas.")


# Muestra el detalle de prestamos y cuotas de un cliente y su deuda total.
def reporte_cliente():
    titulo("REPORTE POR CLIENTE")
    print("")
    dni = input("   DNI del cliente : ")
    cliente = None
    for c in clientes:
        if c[2] == dni:
            cliente = c
    if cliente == None:
        print("   !! No se encontro el cliente.")
        return

    print("")
    print("  Cliente:", cliente[1], "| DNI", cliente[2])
    total_deuda = 0.0
    for p in prestamos:
        if p[1] == cliente[0]:
            saldo = saldo_pendiente(p[0])
            total_deuda = total_deuda + saldo
            print("")
            print("  .---------------------------------------------.")
            print("   Prestamo", p[0], "(", p[5], ") - Estado:", p[6])
            print("  '---------------------------------------------'")
            for c in cuotas:
                if c[0] == p[0]:
                    if c[3] == 1:
                        estado = "[X] PAGADA"
                    else:
                        estado = "[ ] pendiente"
                    print("     Cuota", str(c[1]).ljust(3), "-> $", str(c[2]).ljust(8), estado)
    print("")
    print("  " + "=" * 40)
    print("   Deuda total del cliente: $", round(total_deuda, 2))
    print("  " + "=" * 40)


# ============================================================
#  Menu principal
# ============================================================
# Imprime un encabezado con marco ASCII para cada seccion.
def titulo(texto):
    linea = "+" + "-" * 40 + "+"
    print(linea)
    print("| " + texto.ljust(38) + " |")
    print(linea)


# Muestra el menu principal con las opciones disponibles.
def menu():
    print("")
    print("+========================================+")
    print("|         SISTEMA DE PRESTAMOS           |")
    print("+========================================+")
    print("|  [1] Registrar cliente                 |")
    print("|  [2] Listar clientes                   |")
    print("|  [3] Registrar prestamo                |")
    print("|  [4] Listar prestamos                  |")
    print("|  [5] Registrar pago                    |")
    print("|  [6] Ver deudas activas                |")
    print("|  [7] Reporte por cliente               |")
    print("|  [0] Salir                             |")
    print("+========================================+")


# Bucle principal: muestra el menu y ejecuta la opcion elegida.
def main():
    while True:
        os.system("cls")
        menu()
        entrada = input("Opcion: ")
        valido = False
        while valido == False:
            valido = True
            if entrada == "":
                valido = False
            for letra in entrada:
                if letra < "0" or letra > "9":
                    valido = False
            if valido == False:
                print("!! Opcion invalida. Ingrese un numero.")
                entrada = input("Opcion: ")
        op = int(entrada)

        if op == 0:
            os.system("cls")
            print("+========================================+")
            print("|        Gracias por usar el sistema     |")
            print("|              Hasta luego!              |")
            print("+========================================+")
            break

        os.system("cls")
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
        else:
            print("!! Opcion invalida.")

        print("")
        input("Presione Enter para volver al menu...")


main()