from PySide6.QtWidgets import QGraphicsScene
from PySide6.QtCore import QRectF
from .entities import CADEntity
from .constants import DrawingUnit


class CADScene(QGraphicsScene):
    def __init__(self):
        super().__init__()
        self.setSceneRect(-50000, -50000, 100000, 100000)
        self._entities: list[CADEntity] = []
        self.drawing_unit: DrawingUnit = DrawingUnit.MM

    # ── Entity management ─────────────────────────────────────────────────────

    def add_entity(self, entity: CADEntity):
        self._entities.append(entity)
        self.addItem(entity)

    def remove_entity(self, entity: CADEntity):
        if entity in self._entities:
            self._entities.remove(entity)
            self.removeItem(entity)

    def all_entities(self) -> list[CADEntity]:
        return list(self._entities)

    # ── Selection ─────────────────────────────────────────────────────────────

    def selected_entities(self) -> list[CADEntity]:
        return [e for e in self._entities if e.selected]

    def clear_selection(self):
        for e in self._entities:
            e.selected = False

    def select_in_rect(self, rect: QRectF, crossing: bool, add: bool = False):
        if not add:
            self.clear_selection()
        for e in self._entities:
            if e.intersects_rect(rect, crossing):
                e.selected = True

    def clear_all(self):
        for e in list(self._entities):
            self.removeItem(e)
        self._entities.clear()
