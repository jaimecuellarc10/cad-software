class Command:
    def execute(self): pass
    def undo(self):    pass


class UndoStack:
    def __init__(self, max_size: int = 200):
        self._stack: list[Command] = []
        self._idx: int = -1
        self._max = max_size

    def push(self, cmd: Command):
        self._stack = self._stack[: self._idx + 1]
        cmd.execute()
        self._stack.append(cmd)
        if len(self._stack) > self._max:
            self._stack.pop(0)
        else:
            self._idx += 1

    def undo(self):
        if self.can_undo:
            self._stack[self._idx].undo()
            self._idx -= 1

    def redo(self):
        if self.can_redo:
            self._idx += 1
            self._stack[self._idx].execute()

    @property
    def can_undo(self) -> bool: return self._idx >= 0
    @property
    def can_redo(self) -> bool: return self._idx < len(self._stack) - 1


# ── Commands ──────────────────────────────────────────────────────────────────

class AddEntityCommand(Command):
    def __init__(self, scene, entity):
        self.scene  = scene
        self.entity = entity

    def execute(self): self.scene.add_entity(self.entity)
    def undo(self):    self.scene.remove_entity(self.entity)


class DeleteEntitiesCommand(Command):
    def __init__(self, scene, entities: list):
        self.scene    = scene
        self.entities = list(entities)

    def execute(self):
        for e in self.entities:
            e.selected = False
            self.scene.remove_entity(e)

    def undo(self):
        for e in self.entities:
            self.scene.add_entity(e)


class MoveEntitiesCommand(Command):
    def __init__(self, entities: list, dx: float, dy: float):
        self._entities = list(entities)
        self._dx = dx
        self._dy = dy

    def execute(self):
        for e in self._entities:
            e.translate(self._dx, self._dy)

    def undo(self):
        for e in self._entities:
            e.translate(-self._dx, -self._dy)


class CopyEntitiesCommand(Command):
    def __init__(self, scene, entities: list, dx: float, dy: float):
        self._scene    = scene
        self._originals = list(entities)
        self._dx = dx
        self._dy = dy
        self._copies = None

    def execute(self):
        if self._copies is None:
            self._copies = [e.clone() for e in self._originals]
            for c in self._copies:
                c.translate(self._dx, self._dy)
        for c in self._copies:
            self._scene.add_entity(c)

    def undo(self):
        for c in self._copies:
            self._scene.remove_entity(c)


class RotateEntitiesCommand(Command):
    def __init__(self, entities: list, cx: float, cy: float, angle_deg: float):
        self._entities  = list(entities)
        self._cx        = cx
        self._cy        = cy
        self._angle_deg = angle_deg

    def execute(self):
        for e in self._entities:
            e.rotate_about(self._cx, self._cy, self._angle_deg)

    def undo(self):
        for e in self._entities:
            e.rotate_about(self._cx, self._cy, -self._angle_deg)


class MirrorEntitiesCommand(Command):
    def __init__(self, scene, entities: list, ax: float, ay: float,
                 bx: float, by: float, keep_original: bool = False):
        self._scene         = scene
        self._entities      = list(entities)
        self._ax, self._ay  = ax, ay
        self._bx, self._by  = bx, by
        self._keep_original = keep_original
        self._copies        = None

    def execute(self):
        if self._keep_original:
            if self._copies is None:
                self._copies = [e.clone() for e in self._entities]
                for c in self._copies:
                    c.mirror_across(self._ax, self._ay, self._bx, self._by)
            for c in self._copies:
                self._scene.add_entity(c)
        else:
            for e in self._entities:
                e.mirror_across(self._ax, self._ay, self._bx, self._by)

    def undo(self):
        if self._keep_original:
            for c in self._copies:
                self._scene.remove_entity(c)
        else:
            # mirror is its own inverse
            for e in self._entities:
                e.mirror_across(self._ax, self._ay, self._bx, self._by)


class ReplaceEntityCommand(Command):
    """Swap one entity for another — used by Trim and Extend."""
    def __init__(self, scene, old_entity, new_entity):
        self._scene  = scene
        self._old    = old_entity
        self._new    = new_entity

    def execute(self):
        was_selected = self._old.selected
        self._scene.remove_entity(self._old)
        self._scene.add_entity(self._new)
        self._new.selected = was_selected

    def undo(self):
        self._scene.remove_entity(self._new)
        self._scene.add_entity(self._old)
