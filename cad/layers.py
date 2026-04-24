from PySide6.QtGui import QColor
from PySide6.QtCore import Qt
from .entities import Layer


class LayerManager:
    def __init__(self):
        self._layers: dict[str, Layer] = {}
        self._current_name: str = "0"
        self.add(Layer("0", QColor("#ffffff")))

    def add(self, layer: Layer):
        self._layers[layer.name] = layer

    def get(self, name: str) -> Layer | None:
        return self._layers.get(name)

    def all(self) -> list[Layer]:
        return list(self._layers.values())

    @property
    def current(self) -> Layer:
        return self._layers[self._current_name]

    def set_current(self, name: str):
        if name in self._layers:
            self._current_name = name
