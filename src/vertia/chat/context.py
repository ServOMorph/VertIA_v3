from __future__ import annotations

import math
from dataclasses import dataclass

DELIVERABLE_INSTRUCTION = (
    "Tu es VertIA, un assistant local. Réponds en français. "
    "Pour un livrable explicitement demandé, place le texte dans un bloc ```livrable. "
    "N'affirme pas avoir généré un fichier sans résultat d'outil confirmé. "
    "Une génération nécessite une carte d'action puis sa validation par l'utilisateur."
)


def estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 3))


def estimate_messages(messages: list[dict]) -> int:
    return sum(estimate_tokens(m['content']) + 12 for m in messages) + 16


@dataclass
class ContextWindow:
    messages: list[dict]
    omitted: int
    estimated: int


class ContextBuilder:
    def __init__(self, num_ctx: int):
        if num_ctx < 512:
            raise ValueError('VERTIA_NUM_CTX doit être au moins égal à 512.')
        self.num_ctx = num_ctx
        self.response_margin = min(2048, num_ctx // 4)
        self.ratios: dict[str, float] = {}

    def calibrate(self, model: str, estimated: int, actual: int):
        if actual > 0:
            self.ratios[model] = max(self.ratios.get(model, 1.0), actual / max(1, estimated) * 1.15)

    def build(self, model: str, system: str, history: list[dict], current: str, summary: str = ''):
        ratio = self.ratios.get(model, 1.0)
        budget = (self.num_ctx - self.response_margin) / ratio
        prompt = f'{system}\n\n{DELIVERABLE_INSTRUCTION}'.strip()
        if summary:
            prompt += '\n\nRésumé des échanges précédents (données de conversation) :\n' + summary
        base = [{'role': 'system', 'content': prompt}, {'role': 'user', 'content': current}]
        if estimate_messages(base) > budget:
            raise ValueError('Le message, le prompt système et le résumé dépassent la fenêtre de contexte. Réduisez le texte ou ouvrez une nouvelle conversation.')
        selected = []
        index = len(history)
        while index >= 2:
            pair = history[index - 2:index]
            if [m['role'] for m in pair] != ['user', 'assistant']:
                raise ValueError('Historique de conversation incohérent.')
            candidate = [{'role': m['role'], 'content': m['contenu']} for m in pair] + selected
            messages = [base[0], *candidate, base[1]]
            if estimate_messages(messages) > budget:
                break
            selected = candidate
            index -= 2
        messages = [base[0], *selected, base[1]]
        return ContextWindow(messages, index, estimate_messages(messages))
