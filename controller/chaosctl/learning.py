"""Training the bandit and measuring how it improves with experience.

Only TRAINING scenarios are ever used here. Scenario names are used to group
results for evaluation, never as model input.
"""
import random
import statistics

from . import bandit, store
from .policies import MODEL_PATH, REMEDIATIONS, HeuristicPolicy, RuleBasedPolicy
from .scenarios import HELD_OUT, TRAINING


def _training_steps() -> list[dict]:
    steps = store.training_steps(set(TRAINING))
    assert not any(s["scenario"] in HELD_OUT for s in steps), "held-out data leaked"
    return steps


def train() -> tuple[bandit.LinUCB, int]:
    steps = _training_steps()
    model = bandit.fit([(s["symptoms"], s["action"], s["reward"]) for s in steps], REMEDIATIONS)
    with open(MODEL_PATH, "w") as f:
        f.write(model.to_json())
    return model, len(steps)


def _oracle(steps: list[dict]) -> tuple[dict, dict]:
    """Mean measured reward per (scenario, action), and the best action per scenario."""
    rewards: dict[tuple[str, str], list[float]] = {}
    for s in steps:
        rewards.setdefault((s["scenario"], s["action"]), []).append(s["reward"])
    means = {k: statistics.mean(v) for k, v in rewards.items()}
    best = {}
    for (scenario, action), mean in means.items():
        if scenario not in best or mean > means[(scenario, best[scenario])]:
            best[scenario] = action
    return means, best


def _score(choose, steps, means, best) -> tuple[float, float]:
    """(accuracy vs. the best measured action, mean regret) over logged contexts."""
    correct, regrets = 0, []
    for s in steps:
        choice = choose(s["symptoms"])
        correct += choice == best[s["scenario"]]
        regrets.append(means[(s["scenario"], best[s["scenario"]])]
                       - means.get((s["scenario"], choice), 0.0))
    return correct / len(steps), statistics.mean(regrets)


def learning_curve(points: int = 12, permutations: int = 30, seed: int = 7) -> dict:
    """Replay logged steps in random orders; score the greedy bandit after k steps."""
    steps = _training_steps()
    if not steps:
        return {"steps": 0, "curve": [], "baselines": {}}
    means, best = _oracle(steps)
    rng = random.Random(seed)
    orders = [rng.sample(steps, len(steps)) for _ in range(permutations)]
    sizes = sorted({round(i * len(steps) / (points - 1)) for i in range(points)})

    curve = []
    for k in sizes:
        accs, regs = [], []
        for order in orders:
            model = bandit.fit([(s["symptoms"], s["action"], s["reward"]) for s in order[:k]],
                               REMEDIATIONS)
            acc, reg = _score(lambda sym: model.choose(bandit.features(sym)), steps, means, best)
            accs.append(acc)
            regs.append(reg)
        curve.append({"steps_seen": k, "accuracy": statistics.mean(accs),
                      "regret": statistics.mean(regs)})

    baselines = {}
    for policy in (RuleBasedPolicy(), HeuristicPolicy()):
        acc, reg = _score(lambda sym: policy.choose(sym, [], []), steps, means, best)
        baselines[policy.name] = {"accuracy": acc, "regret": reg}
    return {"steps": len(steps), "curve": curve, "baselines": baselines, "best": best}
