"""Lectura del Excel: encabezados reales, valores sucios y filas rotas."""

from __future__ import annotations

from datetime import date

import pytest
from openpyxl import Workbook

from afip_facturacion.core.excel_reader import (
    ALIAS_COLUMNAS,
    Defaults,
    ExcelError,
    _normalizar,
    leer_comprobantes,
)


@pytest.fixture
def hacer_excel(tmp_path):
    """Escribe un .xlsx con los encabezados y filas que se le pasen."""
    def _crear(encabezados, filas, hoja="Hoja1", nombre="cuotas.xlsx"):
        libro = Workbook()
        pagina = libro.active
        pagina.title = hoja
        pagina.append(encabezados)
        for fila in filas:
            pagina.append(fila)
        ruta = tmp_path / nombre
        libro.save(ruta)
        return str(ruta)
    return _crear


@pytest.fixture
def defaults():
    return Defaults(
        fecha=date(2026, 7, 27), periodo_desde=date(2026, 7, 1),
        periodo_hasta=date(2026, 7, 31), vencimiento_pago=date(2026, 7, 31),
        importe=21500.0, descripcion="Cuota Social Julio 2026",
    )


# ---------------------------------------------------------------------------
# Encabezados
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("encabezado", [
    "DNI", "dni", "Documento", "N° Documento", "Nº Doc", "Nro. Documento",
    "NUMERO DE DOCUMENTO", " documento ",
])
def test_reconoce_las_variantes_del_encabezado_de_documento(encabezado, hacer_excel, defaults):
    """Un Excel escrito por una persona dice cualquiera de estas cosas."""
    ruta = hacer_excel([encabezado], [["30111222"]])
    comprobantes, _ = leer_comprobantes(ruta, defaults=defaults)
    assert [c.doc_nro for c in comprobantes] == ["30111222"]


def test_los_indicadores_ordinales_no_se_vuelven_letras():
    """"Nº" no puede terminar como "no": la normalizacion Unicode lo haria."""
    assert _normalizar("Nº Doc") == "n doc"
    assert _normalizar("N° Documento") == "n documento"
    assert _normalizar("Nº Doc") in ALIAS_COLUMNAS["documento"]


def test_encabezados_con_tildes_y_mayusculas(hacer_excel, defaults):
    ruta = hacer_excel(
        ["Socio", "DNI", "Importe", "Condición frente al IVA", "Período Desde"],
        [["Ana Pérez", "30111222", 1000, "Monotributo", date(2026, 6, 1)]],
    )
    comprobantes, _ = leer_comprobantes(ruta, defaults=defaults)
    assert comprobantes[0].nombre == "Ana Pérez"
    assert comprobantes[0].condicion_iva == 6
    assert comprobantes[0].periodo_desde == date(2026, 6, 1)


def test_sin_columna_de_documento_falla_diciendo_que_se_busco(hacer_excel, defaults):
    ruta = hacer_excel(["Nombre", "Importe"], [["Ana", 100]])
    with pytest.raises(ExcelError) as error:
        leer_comprobantes(ruta, defaults=defaults)
    assert "dni" in str(error.value)
    assert "Nombre" in str(error.value)       # muestra lo que si encontro


# ---------------------------------------------------------------------------
# Valores
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("crudo,esperado", [
    (21500, 21500.0),
    (21500.5, 21500.5),
    ("21500", 21500.0),
    ("$21.500,50", 21500.5),      # formato argentino con separador de miles
    ("$ 18000", 18000.0),
    # El caso ambiguo: tres digitos despues del punto son miles, uno o dos
    # son decimales. Un importe en pesos no lleva tres decimales.
    ("21.500", 21500.0),
    ("1.234.567", 1234567.0),
    ("21.50", 21.5),
    ("21.5", 21.5),
    ("0.75", 0.75),
])
def test_interpreta_los_importes_como_los_escribe_la_gente(crudo, esperado, hacer_excel, defaults):
    ruta = hacer_excel(["DNI", "Importe"], [["30111222", crudo]])
    comprobantes, invalidas = leer_comprobantes(ruta, defaults=defaults)
    assert not invalidas
    assert comprobantes[0].importe == esperado


@pytest.mark.parametrize("crudo", ["27/07/2026", "2026-07-27", "27-07-2026", date(2026, 7, 27)])
def test_interpreta_las_fechas(crudo, hacer_excel, defaults):
    ruta = hacer_excel(["DNI", "Fecha"], [["30111222", crudo]])
    comprobantes, invalidas = leer_comprobantes(ruta, defaults=defaults)
    assert not invalidas
    assert comprobantes[0].fecha == date(2026, 7, 27)


def test_el_documento_se_limpia_de_puntos(hacer_excel, defaults):
    ruta = hacer_excel(["DNI"], [["30.111.222"]])
    comprobantes, _ = leer_comprobantes(ruta, defaults=defaults)
    assert comprobantes[0].doc_nro == "30111222"


def test_la_fila_pisa_al_default(hacer_excel, defaults):
    """El default es para lo que se repite; la fila manda cuando trae el dato."""
    ruta = hacer_excel(["DNI", "Importe"], [["30111222", 9999], ["30111223", None]])
    comprobantes, _ = leer_comprobantes(ruta, defaults=defaults)
    assert comprobantes[0].importe == 9999
    assert comprobantes[1].importe == 21500.0


# ---------------------------------------------------------------------------
# Filas problematicas
# ---------------------------------------------------------------------------

def test_una_fila_rota_no_frena_a_las_demas(hacer_excel, defaults):
    """Si la fila 3 esta mal, las otras igual se emiten: se reporta y sigue."""
    ruta = hacer_excel(
        ["Socio", "DNI", "Fecha"],
        [["Ana", "30111222", None],
         ["Rota", "30111223", "31 de julio"],
         ["Sara", "30111224", None]],
    )
    comprobantes, invalidas = leer_comprobantes(ruta, defaults=defaults)
    assert [c.nombre for c in comprobantes] == ["Ana", "Sara"]
    assert len(invalidas) == 1
    assert invalidas[0].numero == 3
    assert "fecha" in invalidas[0].motivo


def test_fila_sin_documento_se_reporta(hacer_excel, defaults):
    ruta = hacer_excel(["Socio", "DNI"], [["Sin doc", None]])
    comprobantes, invalidas = leer_comprobantes(ruta, defaults=defaults)
    assert not comprobantes
    assert "documento" in invalidas[0].motivo


def test_sin_importe_ni_default_se_reporta(hacer_excel):
    ruta = hacer_excel(["DNI"], [["30111222"]])
    comprobantes, invalidas = leer_comprobantes(ruta, defaults=Defaults(fecha=date(2026, 7, 27)))
    assert not comprobantes
    assert "importe" in invalidas[0].motivo


def test_una_fila_en_blanco_no_corta_la_lectura(hacer_excel, defaults):
    """Los Excel reales tienen renglones de separacion en el medio.

    Cortar ahi dejaria socios sin facturar sin que nadie se entere.
    """
    ruta = hacer_excel(
        ["DNI"],
        [["30111222"], [None], ["30111223"]],
    )
    comprobantes, _ = leer_comprobantes(ruta, defaults=defaults)
    assert [c.doc_nro for c in comprobantes] == ["30111222", "30111223"]


def test_el_numero_de_fila_apunta_al_excel(hacer_excel, defaults):
    """La fila 1 son los encabezados, asi que los datos arrancan en la 2."""
    ruta = hacer_excel(["DNI"], [["30111222"], ["30111223"]])
    comprobantes, _ = leer_comprobantes(ruta, defaults=defaults)
    assert [c.fila_excel for c in comprobantes] == [2, 3]


# ---------------------------------------------------------------------------
# Archivo y hoja
# ---------------------------------------------------------------------------

def test_hoja_inexistente_lista_las_que_hay(hacer_excel, defaults):
    ruta = hacer_excel(["DNI"], [["30111222"]], hoja="Julio")
    with pytest.raises(ExcelError) as error:
        leer_comprobantes(ruta, "Agosto", defaults)
    assert "Julio" in str(error.value)


def test_archivo_inexistente(defaults):
    with pytest.raises(ExcelError) as error:
        leer_comprobantes("/no/existe.xlsx", defaults=defaults)
    assert "no se encontro" in str(error.value)
