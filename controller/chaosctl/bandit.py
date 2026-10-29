"""Contextual bandit (disjoint LinUCB) that picks a recovery action from symptoms.

Context = observable symptoms only (never the injected fault's name).
Reward  = how fast the step healed the service, minus the action's safety cost.
"""
import json
import math

import numpy as np

FEATURES = ["bias", "api_down", "redis_unreachable", "postgres_unreachable",
            "redis_probe_latency", "postgres_probe_latency", "error_rate", "p95_latency"]


def _latency(ms: float | None) -> float:
    """Log-scaled latency in [0, 1]; 2 s and above saturate."""
    return 0.0 if ms is None else min(math.log1p(ms) / math.log1p(2000), 1.0)


def features(symptoms: dict) -> np.ndarray:
    api_down = not symptoms.get("api_up")
    return np.array([
        1.0,
        float(api_down),
        float(not api_down and symptoms.get("redis_ok") is False),
        float(not api_down and symptoms.get("postgres_ok") is False),
        0.0 if api_down else _latency(symptoms.get("redis_ms")),
        0.0 if api_down else _latency(symptoms.get("postgres_ms")),
        symptoms.get("error_rate") or 0.0,
        _latency(symptoms.get("p95_ms")),
    ])


class LinUCB:
    def __init__(self, actions: list[str], alpha: float = 0.5, ridge: float = 1.0):
        d = len(FEATURES)
        self.actions = list(actions)
        self.alpha = alpha
        self.A = {a: np.eye(d) * ridge for a in self.actions}
        self.b = {a: np.zeros(d) for a in self.actions}

    def update(self, x: np.ndarray, action: str, reward: float) -> None:
        self.A[action] += np.outer(x, x)
        self.b[action] += reward * x

    def scores(self, x: np.ndarray, explore: bool) -> dict[str, float]:
        out = {}
        for a in self.actions:
            a_inv = np.linalg.inv(self.A[a])
            mean = float((a_inv @ self.b[a]) @ x)
            bonus = self.alpha * math.sqrt(float(x @ a_inv @ x)) if explore else 0.0
            out[a] = mean + bonus
        return out

    def choose(self, x: np.ndarray, exclude: list[str] = (), explore: bool = False) -> str | None:
        scores = {a: s for a, s in self.scores(x, explore).items() if a not in exclude}
        return max(scores, key=scores.get) if scores else None

    def to_json(self) -> str:
        return json.dumps({
            "features": FEATURES, "alpha": self.alpha, "actions": self.actions,
            "A": {a: m.tolist() for a, m in self.A.items()},
            "b": {a: v.tolist() for a, v in self.b.items()},
        })

    @classmethod
    def from_json(cls, text: str) -> "LinUCB":
        data = json.loads(text)
        if data["features"] != FEATURES:
            raise ValueError("model was trained with different features; retrain it")
        model = cls(data["actions"], alpha=data["alpha"])
        model.A = {a: np.array(m) for a, m in data["A"].items()}
        model.b = {a: np.array(v) for a, v in data["b"].items()}
        return model


def fit(steps: list[tuple[dict, str, float]], actions: list[str]) -> LinUCB:
    """Train from logged (symptoms, action, reward) steps."""
    model = LinUCB(actions)
    for symptoms, action, reward in steps:
        if action in model.A:
            model.update(features(symptoms), action, reward)
    return model
