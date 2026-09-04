"""Automation Launcher: control room de automatizaciones sobre Jupyter/Voila.

El paquete esta partido en dos capas que no se mezclan:

  * ``automation_launcher.core``  -- logica pura, sin ipywidgets ni Jupyter.
    Config, autorizacion, ejecucion, historial y metricas viven aca, se
    testean sin levantar un servidor y se reusan desde la CLI.

  * ``automation_launcher.ui``    -- la capa de widgets que consume el core.

Compatible con Python 3.7 (kernel Athena).
"""

__version__ = "1.0.0"
