import os
import pickle
import socket

from bokeh.layouts import column
from bokeh.models.widgets import Div
from bokeh.server.server import Server
from loguru import logger

from chartrider.analysis.datasource import PlotDataSource
from chartrider.analysis.renderer import BokehPlotRenderer
from chartrider.settings import ROOT_PATH
from chartrider.utils.htmlsnippets import HTMLElement


def __list_folders():
    base_path = os.path.join(ROOT_PATH, "reports", "backtest")
    folders = [f for f in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, f))]
    return folders


def __list_pkl_files(folder_name: str):
    folder_path = os.path.join(ROOT_PATH, "reports", "backtest", folder_name)
    pkl_files = [f for f in os.listdir(folder_path) if f.endswith(".pkl")]
    return pkl_files


def __list_all_pickle_files() -> list[str]:
    base_path = os.path.join(ROOT_PATH, "reports", "backtest")
    pkl_files = []
    for root, _, files in os.walk(base_path):
        for file in files:
            if file.endswith(".pkl"):
                pkl_files.append(os.path.join(root, file))
    return pkl_files


def __load_datasource(pkl_path):
    with open(pkl_path, "rb") as f:
        datasource = pickle.load(f)
    return datasource


def __create_plot(datasource: PlotDataSource):
    plot = BokehPlotRenderer(datasource).create_plot()
    return plot


def __create_root_page(doc):
    folders = __list_folders()

    folder_links = [
        Div(
            text=HTMLElement(
                "a",
                href=f"/?folder={folder}",
                children=folder,
                margin_horizontal=2,
                margin_vertical=2,
            ).render(),
        )
        for folder in folders
    ]
    pkl_paths = __list_all_pickle_files()
    pkl_paths = sorted(pkl_paths, key=lambda x: os.path.basename(x), reverse=True)
    pkl_links = [
        Div(
            text=HTMLElement(
                "a",
                href=f"/?folder={os.path.dirname(item)}&file={os.path.basename(item)}",
                children=os.path.basename(item).replace(".pkl", ""),
                margin_horizontal=2,
                margin_vertical=2,
            ).render(),
        )
        for item in pkl_paths
    ]

    folders_header_div = Div(
        text=HTMLElement(
            "h1",
            children="Folders",
            margin_horizontal=2,
        ).render()
    )

    recents_header_div = Div(
        text=HTMLElement(
            "h1",
            children="Recent",
            margin_horizontal=2,
        ).render()
    )

    doc.clear()
    doc.add_root(
        column(
            [
                recents_header_div,
                *pkl_links,
                folders_header_div,
                *folder_links,
            ]  # type: ignore
        )
    )


def __create_file_links(doc, folder_name):
    pkl_files = __list_pkl_files(folder_name)
    pkl_links = [
        Div(
            text=HTMLElement(
                "a",
                href=f"/?folder={folder_name}&file={file}",
                children=file.replace(".pkl", ""),
                margin_horizontal=2,
                margin_vertical=2,
            ).render(),
        )
        for file in pkl_files
    ]
    back_link = Div(
        text=HTMLElement(
            "a",
            href="/",
            children="Back to root",
            margin_horizontal=2,
            margin_vertical=2,
        ).render()
    )
    doc.clear()
    doc.add_root(column(back_link, *pkl_links))  # type: ignore


def __create_plot_page(doc, folder_name, pkl_file_name):
    folder_path = os.path.join(ROOT_PATH, "reports", "backtest", folder_name)
    pkl_path = os.path.join(folder_path, pkl_file_name)
    datasource = __load_datasource(pkl_path)
    plot = __create_plot(datasource)
    doc.clear()
    doc.add_root(plot)


def __create_index_page(doc):
    folder_name = doc.session_context.request.arguments.get("folder", [None])[0]
    pkl_file_name = doc.session_context.request.arguments.get("file", [None])[0]
    if folder_name:
        folder_name = folder_name.decode("utf-8")
    if pkl_file_name:
        pkl_file_name = pkl_file_name.decode("utf-8")
    __update_doc(doc, folder_name, pkl_file_name)


def __update_doc(doc, folder_name: str | None = None, pkl_file_name: str | None = None):
    if folder_name is None and pkl_file_name is None:
        __create_root_page(doc)
        return
    if pkl_file_name is None and folder_name is not None:
        __create_file_links(doc, folder_name)
        return
    __create_plot_page(doc, folder_name, pkl_file_name)


def __is_port_open(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(("localhost", port))
    sock.close()
    return result != 0


def start_bokeh_server():
    port = 5006
    if __is_port_open(port):
        logger.info(f"Starting Bokeh server on http://localhost:{port}")
        server = Server({"/": __create_index_page})
        server.start()
        server.io_loop.add_callback(server.show, "/")
        server.io_loop.start()
    else:
        logger.error(f"Port {port} is already in use")


if __name__ == "__main__":
    start_bokeh_server()
