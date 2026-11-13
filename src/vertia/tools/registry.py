from __future__ import annotations

import json


class ToolRegistry:
    def __init__(self, engines):
        self.engines = engines
        self.tools = {}

    def register(self, tool):
        if tool.name in self.tools or tool.engine not in self.engines:
            raise ValueError('Outil déjà enregistré ou moteur absent.')
        self.tools[tool.name] = tool

    def get(self, name):
        if name not in self.tools:
            raise ValueError('Outil indisponible.')
        return self.tools[name]

    def schemas(self, names):
        return json.dumps([dict(name=t.name, description=t.description, parameters=t.parameters)
                           for t in (self.get(name) for name in names)], ensure_ascii=False, separators=(',', ':'))

    def candidates(self, text):
        return [t.name for t in self.tools.values() if t.matches(text)]
