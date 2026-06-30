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
    print("  (escriba c para cancelar)")
    print("")

    nombre = input("   Nombre y apellido : ")
    while nombre == "":
        print("   !! El nombre no puede estar vacio.")
        nombre = input("   Nombre y apellido : ")
    if nombre == "c":
        print("   >> Operacion cancelada.")
        return

    dni = input("   DNI              : ")
    valido = False
    while valido == False:
        if dni == "c":
            print("   >> Operacion cancelada.")
            return
        valido = True
        if dni == "":
            valido = False
        for letra in dni:
            if letra < "0" or letra > "9":
                valido = False
        if valido == False:
            print("   !! El DNI debe ser un numero (o c para cancelar).")
            dni = input("   DNI              : ")
        else:
            # Se chequea que no exista ya un cliente con ese DNI
            for c in clientes:
                if c[2] == dni:
                    valido = False
            if valido == False:
                print("   !! Ya existe un cliente con ese DNI (o c para cancelar).")
                dni = input("   DNI              : ")

    telefono = input("   Telefono         : ")
    valido = False
    while valido == False:
        if telefono == "c":
            print("   >> Operacion cancelada.")
            return
        valido = True
        if telefono == "":
            valido = False
        for letra in telefono:
            if letra < "0" or letra > "9":
                valido = False
        if valido == False:
            print("   !! El telefono debe ser un numero (o c para cancelar).")
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
    print("  (escriba c para cancelar)")
    print("")

    dni = input("   DNI del cliente   : ")
    if dni == "c":
        print("   >> Operacion cancelada.")
        return
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
        if entrada == "c":
            print("   >> Operacion cancelada.")
            return
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
            print("   !! El capital debe ser un numero mayor a 0 (o c para cancelar).")
            entrada = input("   Capital prestado  : ")
    capital = float(entrada)

    entrada = input("   Tasa mensual (%)  : ")
    valido = False
    while valido == False:
        if entrada == "c":
            print("   >> Operacion cancelada.")
            return
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
            print("   !! La tasa debe ser un numero (o c para cancelar).")
            entrada = input("   Tasa mensual (%)  : ")
    tasa_pct = float(entrada)
    tasa = tasa_pct / 100

    entrada = input("   Cantidad de cuotas: ")
    valido = False
    while valido == False:
        if entrada == "c":
            print("   >> Operacion cancelada.")
            return
        valido = True
        if entrada == "":
            valido = False
        for letra in entrada:
            if letra < "0" or letra > "9":
                valido = False
        if valido == True and int(entrada) <= 0:
            valido = False
        if valido == False:
            print("   !! La cantidad de cuotas debe ser un numero entero mayor a 0 (o c para cancelar).")
            entrada = input("   Cantidad de cuotas: ")
    n = int(entrada)

    print("")
    print("   Sistema de interes:  [1] Simple   [2] Frances")
    entrada = input("   Opcion            : ")
    while entrada != "1" and entrada != "2":
        if entrada == "c":
            print("   >> Operacion cancelada.")
            return
        print("   !! Opcion invalida. Ingrese 1 o 2 (o c para cancelar).")
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
    print("   Sistema        :", sistema.capitalize())
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
              "|", p[5].capitalize().ljust(8),
              "|", p[6].capitalize().ljust(8),
              "| $", round(saldo_pendiente(p[0]), 2))


# ============================================================
#  Pagos
# ============================================================
# Registra el pago de una cuota, aplica la mora y actualiza el estado.
def registrar_pago():
    titulo("REGISTRAR PAGO")
    print("  (escriba c para cancelar)")
    print("")

    # Se busca al cliente por DNI
    dni = input("   DNI del cliente : ")
    if dni == "c":
        print("   >> Operacion cancelada.")
        return
    cliente = None
    for c in clientes:
        if c[2] == dni:
            cliente = c
    if cliente == None:
        print("   !! No se encontro el cliente.")
        return

    # Se muestran solo los prestamos activos (con saldo) de ese cliente
    print("   Cliente:", cliente[1])
    print("")
    print("   Prestamos activos:")
    hay = False
    for p in prestamos:
        if p[1] == cliente[0] and saldo_pendiente(p[0]) > 0:
            hay = True
            print("     [", p[0], "]", p[5].capitalize(),
                  "-", p[4], "cuotas",
                  "- Saldo $", round(saldo_pendiente(p[0]), 2))
    if hay == False:
        print("   !! El cliente no tiene prestamos activos.")
        return

    print("")
    entrada = input("   ID del prestamo a pagar : ")
    valido = False
    while valido == False:
        if entrada == "c":
            print("   >> Operacion cancelada.")
            return
        valido = True
        if entrada == "":
            valido = False
        for letra in entrada:
            if letra < "0" or letra > "9":
                valido = False
        # Ademas el prestamo debe ser de este cliente y estar activo
        if valido == True:
            existe = False
            for p in prestamos:
                if p[0] == int(entrada) and p[1] == cliente[0] and saldo_pendiente(p[0]) > 0:
                    existe = True
            if existe == False:
                valido = False
        if valido == False:
            print("   !! Ingrese un ID valido de la lista (o c para cancelar).")
            entrada = input("   ID del prestamo a pagar : ")
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
        if entrada == "c":
            print("   >> Operacion cancelada.")
            return
        valido = True
        if entrada == "":
            valido = False
        for letra in entrada:
            if letra < "0" or letra > "9":
                valido = False
        if valido == False:
            print("   !! El numero de cuota debe ser un numero (o c para cancelar).")
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
        if entrada == "c":
            print("   >> Operacion cancelada.")
            return
        valido = True
        if entrada == "":
            valido = False
        for letra in entrada:
            if letra < "0" or letra > "9":
                valido = False
        if valido == False:
            print("   !! Los dias deben ser un numero (0 o mas, o c para cancelar).")
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
            print("   Prestamo", p[0], "(", p[5].capitalize(), ") - Estado:", p[6].capitalize())
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


# Suma el monto de las cuotas ya pagadas de un prestamo.
def total_pagado(id_prestamo):
    total = 0.0
    for c in cuotas:
        if c[0] == id_prestamo and c[3] == 1:
            total = total + c[2]
    return total


# Elimina un cliente, solo si no tiene prestamos con saldo pendiente.
def eliminar_cliente():
    titulo("ELIMINAR CLIENTE")
    print("  (escriba c para cancelar)")
    print("")
    dni = input("   DNI del cliente : ")
    if dni == "c":
        print("   >> Operacion cancelada.")
        return

    cliente = None
    for c in clientes:
        if c[2] == dni:
            cliente = c
    if cliente == None:
        print("   !! No se encontro el cliente.")
        return

    # Reviso si tiene algun prestamo con saldo pendiente
    tiene_deuda = False
    for p in prestamos:
        if p[1] == cliente[0] and saldo_pendiente(p[0]) > 0:
            tiene_deuda = True

    if tiene_deuda == True:
        print("   !! No se puede eliminar: el cliente tiene prestamos activos.")
        return

    clientes.remove(cliente)
    print("")
    print("  +--------------------------------------+")
    print("  |  Cliente eliminado correctamente     |")
    print("  +--------------------------------------+")
    print("   Nombre :", cliente[1])
    print("   DNI    :", cliente[2])


# Muestra una tabla con todos los clientes, su estado, pagado y pendiente.
def reporte_general():
    titulo("REPORTE GENERAL DE CLIENTES")
    if len(clientes) == 0:
        print("No hay clientes cargados.")
        return

    print("  Cliente                 | Estado   | Pagado     | Pendiente")
    print("  " + "-" * 62)
    for cli in clientes:
        pagado = 0.0
        pendiente = 0.0
        for p in prestamos:
            if p[1] == cli[0]:
                pagado = pagado + total_pagado(p[0])
                pendiente = pendiente + saldo_pendiente(p[0])
        # Activo = tiene saldo pendiente
        if pendiente > 0:
            estado = "ACTIVO"
        else:
            estado = "INACTIVO"
        print("  " + cli[1].ljust(22),
              "|", estado.ljust(8),
              "|", ("$ " + str(round(pagado, 2))).ljust(10),
              "|", "$ " + str(round(pendiente, 2)))


# Busca clientes cuyo nombre contenga el texto ingresado.
def buscar_cliente():
    titulo("BUSCAR CLIENTE POR NOMBRE")
    print("  (escriba c para cancelar)")
    print("")
    texto = input("   Nombre a buscar : ")
    if texto == "c":
        print("   >> Operacion cancelada.")
        return

    texto = texto.lower()
    hay = False
    print("")
    for cli in clientes:
        if texto in cli[1].lower():
            if hay == False:
                print("  ID  | Nombre                 | DNI         | Telefono")
                print("  " + "-" * 56)
            hay = True
            print("  " + str(cli[0]).ljust(3),
                  "|", cli[1].ljust(22),
                  "|", cli[2].ljust(11),
                  "|", cli[3])
    if hay == False:
        print("   !! No se encontraron clientes con ese nombre.")


# Muestra totales globales del sistema (clientes, prestamos y montos).
def reporte_resumen():
    titulo("RESUMEN GENERAL DEL SISTEMA")

    total_prestado = 0.0
    total_cobrado = 0.0
    total_pendiente = 0.0
    for p in prestamos:
        total_prestado = total_prestado + p[2]
        total_cobrado = total_cobrado + total_pagado(p[0])
        total_pendiente = total_pendiente + saldo_pendiente(p[0])

    print("")
    print("   Clientes registrados : ", len(clientes))
    print("   Prestamos otorgados  : ", len(prestamos))
    print("  " + "-" * 40)
    print("   Total prestado       : $", round(total_prestado, 2))
    print("   Total cobrado        : $", round(total_cobrado, 2))
    print("   Total pendiente      : $", round(total_pendiente, 2))


# Submenu con la lista de reportes disponibles.
def menu_reportes():
    while True:
        os.system("cls")
        print("")
        print("+========================================+")
        print("|              REPORTES                  |")
        print("+========================================+")
        print("|  [1] Reporte por cliente               |")
        print("|  [2] Reporte general de clientes       |")
        print("|  [3] Buscar cliente por nombre         |")
        print("|  [4] Resumen general del sistema       |")
        print("|  [0] Volver al menu principal          |")
        print("+========================================+")

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
            return

        os.system("cls")
        if op == 1:
            reporte_cliente()
        elif op == 2:
            reporte_general()
        elif op == 3:
            buscar_cliente()
        elif op == 4:
            reporte_resumen()
        else:
            print("!! Opcion invalida.")

        print("")
        input("Presione Enter para volver a Reportes...")


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
    print("|  [7] Eliminar cliente                  |")
    print("|  [8] Reportes                          |")
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
            eliminar_cliente()
        elif op == 8:
            menu_reportes()
        else:
            print("!! Opcion invalida.")

        print("")
        input("Presione Enter para volver al menu...")





# Carga 10 clientes, 1 prestamo por cliente y sus cuotas para la demo.
def cargar_datos_demo():

    # --- Lista de clientes ---  [id, nombre, dni, telefono]
    clientes.append([1,  "Ana Gomez",        "30111222", "1140001111"])
    clientes.append([2,  "Carlos Perez",     "28999888", "1140002222"])
    clientes.append([3,  "Maria Lopez",      "33444555", "1140003333"])
    clientes.append([4,  "Juan Rodriguez",   "25666777", "1140004444"])
    clientes.append([5,  "Lucia Fernandez",  "31222333", "1140005555"])
    clientes.append([6,  "Pedro Martinez",   "27888999", "1140006666"])
    clientes.append([7,  "Sofia Diaz",       "34555666", "1140007777"])
    clientes.append([8,  "Diego Sanchez",    "29333444", "1140008888"])
    clientes.append([9,  "Valentina Romero", "32777888", "1140009999"])
    clientes.append([10, "Mateo Torres",     "26444555", "1140010000"])

    # --- Lista de prestamos ---  [id, id_cliente, capital, tasa, cuotas, sistema, estado]

    prestamos.append([1,  1,  100000.0, 0.05, 12, "frances", "activo"])
    prestamos.append([2,  2,   50000.0, 0.04,  6, "simple",  "pagado"])
    prestamos.append([3,  3,  200000.0, 0.06, 18, "frances", "activo"])
    prestamos.append([4,  4,   30000.0, 0.03,  3, "simple",  "activo"])
    prestamos.append([5,  5,   80000.0, 0.05, 10, "frances", "activo"])
    prestamos.append([6,  6,  150000.0, 0.04, 24, "frances", "activo"])
    prestamos.append([7,  7,   40000.0, 0.03,  4, "simple",  "pagado"])
    prestamos.append([8,  8,  120000.0, 0.06, 12, "frances", "activo"])
    prestamos.append([9,  9,   60000.0, 0.04,  6, "simple",  "activo"])
    prestamos.append([10, 10,  90000.0, 0.05,  9, "frances", "activo"])

    # --- Lista de cuotas ---  [id_prestamo, numero, monto, pagada]
    for p in prestamos:
        id_prestamo = p[0]
        capital = p[2]
        tasa = p[3]
        n = p[4]
        sistema = p[5]
        if sistema == "frances":
            cuota = calcular_cuota_frances(capital, tasa, n)
        else:
            cuota = calcular_cuota_simple(capital, tasa, n)
        numero = 1
        while numero <= n:
            if numero <= pagas[id_prestamo - 1]:
                pagada = 1
            else:
                pagada = 0
            cuotas.append([id_prestamo, numero, round(cuota, 2), pagada])
            numero = numero + 1



# ============================================================
#  Inicio del programa
# ============================================================
cargar_datos_demo()
main()