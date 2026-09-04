"""Carga de configuracion: defaults, validacion y degradacion elegante."""

from __future__ import annotations

from automation_launcher.core.config import DEFAULTS, load_config, validate


def test_toma_solo_las_mayusculas():
    """Asi el archivo puede tener imports y helpers sin que se cuelen."""
    config = load_config(source_text="CONTENTS_DIR='x'\nhelper=1\n_privado=2")
    assert config.CONTENTS_DIR == "x"
    assert "helper" not in config
    assert "_privado" not in config


def test_las_claves_faltantes_usan_el_default():
    config = load_config(source_text="CONTENTS_DIR='x'")
    assert config.CONSOLE_MAX_LINES == DEFAULTS["CONSOLE_MAX_LINES"]


def test_un_valor_invalido_se_descarta_pero_se_reporta():
    """La app tiene que seguir arriba; lo que no puede es callarse el problema."""
    config = load_config(source_text="MAX_CONCURRENT_RUNS=-1")
    assert config.MAX_CONCURRENT_RUNS == DEFAULTS["MAX_CONCURRENT_RUNS"]
    assert any("MAX_CONCURRENT_RUNS" in p for p in config.problems)


def test_backend_de_auth_desconocido_se_rechaza():
    config = load_config(source_text="AUTH_BACKEND='ldap'")
    assert config.AUTH_BACKEND == "smb"
    assert any("AUTH_BACKEND" in p for p in config.problems)


def test_avisa_si_smb_no_tiene_host():
    _values, problems = validate({"AUTH_BACKEND": "smb", "AUTH_HOST": ""})
    assert any("AUTH_HOST" in p for p in problems)


def test_archivo_inexistente_no_rompe():
    config = load_config("/no/existe/launcher_config.py")
    assert not config.loaded
    assert "using defaults" in config.status_line()
    assert config.CONTENTS_DIR == DEFAULTS["CONTENTS_DIR"]


def test_sintaxis_rota_no_rompe():
    config = load_config(source_text="def (")
    assert not config.loaded
    assert config.problems


def test_file_se_resuelve_a_ruta_absoluta(tmp_path):
    """Los archivos de config calculan rutas relativas a si mismos; si __file__
    quedara relativo, esas rutas dependerian de desde donde se arranco."""
    import os
    config_file = tmp_path / "sub" / "launcher_config.py"
    config_file.parent.mkdir()
    config_file.write_text(
        "import os\nBASE = os.path.dirname(os.path.abspath(__file__))\n")
    os.chdir(str(tmp_path))
    config = load_config("sub/launcher_config.py")
    assert config.get("BASE") == os.path.realpath(str(config_file.parent))


def test_is_demo_requiere_mock():
    assert load_config(source_text="DEMO_MODE=True\nAUTH_BACKEND='mock'").is_demo
    assert not load_config(source_text="DEMO_MODE=True\nAUTH_BACKEND='smb'").is_demo
