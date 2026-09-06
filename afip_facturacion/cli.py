"""Linea de comandos: emite los comprobantes de un Excel y reporta el CAE.

Uso tipico (una vez por mes):

    python -m afip_facturacion --excel cuotas.xlsx --hoja Julio \\
        --fecha 27/07/2026 --desde 01/07/2026 --hasta 31/07/2026 \\
        --importe 21500 --descripcion "Cuota Social Julio 2026"

Por defecto apunta al ambiente de **homologacion** (las pruebas de AFIP): los
comprobantes que emite ahi no tienen validez fiscal y no consumen numeracion
real. Para emitir de verdad hay que agregar ``--produccion`` explicitamente.
Ese default es a proposito -- el error de correr contra produccion pensando
que era una prueba no se puede deshacer: un comprobante autorizado no se
borra, se anula con una nota de credito.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

from .core.excel_reader import Defaults, ExcelError, leer_comprobantes
from .core.models import EmisorConfig
from .core.wsaa import WSAA, WSAAError
from .core.wsfe import WSFE, WSFEError


def _fecha_arg(texto: str):
    """Parsea una fecha de la linea de comandos en dd/mm/aaaa."""
    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"fecha invalida: {texto!r} (usar dd/mm/aaaa)")


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m afip_facturacion",
        description="Emite comprobantes electronicos en AFIP (WSFEv1) desde un Excel.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--excel", required=True, help="archivo .xlsx con los comprobantes")
    parser.add_argument("--hoja", help="hoja a leer (por defecto, la primera)")
    parser.add_argument("--config", default="config.py",
                        help="archivo de configuracion del emisor (default: config.py)")

    grupo = parser.add_argument_group(
        "valores por defecto",
        "Se aplican a las filas que no traigan ese dato en el Excel.",
    )
    grupo.add_argument("--fecha", type=_fecha_arg, help="fecha del comprobante (dd/mm/aaaa)")
    grupo.add_argument("--desde", type=_fecha_arg, help="inicio del periodo facturado")
    grupo.add_argument("--hasta", type=_fecha_arg, help="fin del periodo facturado")
    grupo.add_argument("--vencimiento", type=_fecha_arg, help="vencimiento para el pago")
    grupo.add_argument("--importe", type=float, help="importe por comprobante")
    grupo.add_argument("--descripcion", default="", help="descripcion del servicio")

    parser.add_argument("--produccion", action="store_true",
                        help="emitir en AFIP de verdad (por defecto va a homologacion)")
    parser.add_argument("--dry-run", action="store_true",
                        help="leer el Excel y mostrar que se emitiria, sin llamar a AFIP")
    return parser


def cargar_emisor(ruta_config: str, produccion: bool) -> EmisorConfig:
    """Carga config.py por ruta y arma el EmisorConfig."""
    import importlib.util
    import os

    if not os.path.isfile(ruta_config):
        raise SystemExit(
            f"no se encontro {ruta_config}. Copia config.example.py a config.py "
            "y completa el CUIT y el punto de venta."
        )
    spec = importlib.util.spec_from_file_location("config_emisor", ruta_config)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)

    valores = {k.lower(): v for k, v in vars(modulo).items() if k.isupper()}
    faltantes = [c for c in ("cuit", "punto_venta") if c not in valores]
    if faltantes:
        raise SystemExit(f"{ruta_config}: falta definir {', '.join(f.upper() for f in faltantes)}")

    campos = {k: v for k, v in valores.items() if k in EmisorConfig.__dataclass_fields__}
    campos["produccion"] = produccion
    try:
        return EmisorConfig(**campos)
    except ValueError as exc:
        raise SystemExit(f"{ruta_config}: {exc}") from exc


def _imprimir_plan(comprobantes, invalidas, emisor, produccion) -> None:
    ambiente = "PRODUCCION (comprobantes reales)" if produccion else "homologacion (prueba)"
    print(f"Ambiente : {ambiente}")
    print(f"Emisor   : CUIT {emisor.cuit}, punto de venta {emisor.punto_venta}, "
          f"tipo de comprobante {emisor.cbte_tipo}")
    print(f"A emitir : {len(comprobantes)} comprobante(s)")
    if invalidas:
        print(f"\n{len(invalidas)} fila(s) con problemas, se saltean:")
        for fila in invalidas:
            print(f"  fila {fila.numero}: {fila.motivo}")
    print()


def _imprimir_resultados(resultados) -> int:
    aprobados = [r for r in resultados if r.aprobado]
    rechazados = [r for r in resultados if not r.aprobado]

    print(f"{'COMPROBANTE':<28} {'NRO':>6}  {'ESTADO':<10} {'CAE':<16} DETALLE")
    print("-" * 96)
    for r in resultados:
        estado = "aprobado" if r.aprobado else "RECHAZADO"
        print(f"{r.etiqueta[:28]:<28} {r.numero or '-':>6}  {estado:<10} "
              f"{r.cae or '-':<16} {r.observaciones}")
    print("-" * 96)
    print(f"{len(aprobados)} aprobado(s), {len(rechazados)} rechazado(s)")

    if rechazados:
        print("\nLos rechazados NO se emitieron: corregi el dato que indica AFIP y volve")
        print("a correr solo con esas filas. La numeracion no se consume por un rechazo.")
    return 1 if rechazados else 0


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)

    defaults = Defaults(
        fecha=args.fecha, periodo_desde=args.desde, periodo_hasta=args.hasta,
        vencimiento_pago=args.vencimiento, importe=args.importe,
        descripcion=args.descripcion,
    )

    try:
        comprobantes, invalidas = leer_comprobantes(args.excel, args.hoja, defaults)
    except ExcelError as exc:
        print(f"Error leyendo el Excel: {exc}", file=sys.stderr)
        return 2

    emisor = cargar_emisor(args.config, args.produccion)
    _imprimir_plan(comprobantes, invalidas, emisor, args.produccion)

    if not comprobantes:
        print("No hay nada para emitir.")
        return 0

    if args.dry_run:
        print("--dry-run: no se llamo a AFIP. Detalle de lo que se emitiria:\n")
        for c in comprobantes:
            print(f"  fila {c.fila_excel:>3}  {c.nombre[:24]:<24} doc {c.doc_nro:<11} "
                  f"${c.importe:>10,.2f}  {c.fecha}  iva={c.condicion_iva}")
        return 0

    if args.produccion:
        print("Vas a emitir comprobantes REALES en AFIP. Esto no se puede deshacer.")
        if input("Escribi 'si' para continuar: ").strip().lower() != "si":
            print("Cancelado.")
            return 0
        print()

    autenticador = WSAA(
        cuit=emisor.cuit, cert_path=emisor.cert_path, key_path=emisor.key_path,
        cache_dir=emisor.cache_dir, produccion=emisor.produccion,
    )
    cliente = WSFE(emisor, autenticador)

    try:
        resultados = cliente.solicitar_cae(comprobantes)
    except WSAAError as exc:
        print(f"\nError de autenticacion con AFIP: {exc}", file=sys.stderr)
        return 3
    except WSFEError as exc:
        print(f"\nError del servicio de facturacion: {exc}", file=sys.stderr)
        return 4

    return _imprimir_resultados(resultados)


if __name__ == "__main__":
    sys.exit(main())
