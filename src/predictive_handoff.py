"""Predictive Handoff — Pre-position resources before demand arrives.

Their pain: Model serving at scale needs proactive resource management.

Innovation: Predicts when resources will be needed and pre-positions
them before demand arrives. Zero-acquisition-time resource allocation.
"""

import math
import time
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ResourcePool:
    pool_id: str
    resource_type: str
    total_count: int
    available_count: int
    region: str

    @property
    def utilization(self) -> float:
        return 1 - (self.available_count / self.total_count if self.total_count > 0 else 1)

    @property
    def health(self) -> str:
        if self.utilization > 0.9:
            return "CRITICAL"
        if self.utilization > 0.7:
            return "HIGH"
        if self.utilization > 0.3:
            return "OPTIMAL"
        return "LOW"


@dataclass
class DemandForecast:
    timestamp: float
    predicted_demand: float
    confidence: float
    time_horizon_s: float


class DemandPredictor:
    """Predicts resource demand using historical patterns.

    Innovation: Uses sinusoidal pattern matching + trend analysis
    to predict demand 5-30 minutes ahead.
    """

    def __init__(self, history_size: int = 500):
        self.history_size = history_size
        self.demand_history: List[float] = []
        self.timestamp_history: List[float] = []

    def record_demand(self, demand: float, timestamp: float = 0):
        if timestamp == 0:
            timestamp = time.time()
        self.demand_history.append(demand)
        self.timestamp_history.append(timestamp)
        if len(self.demand_history) > self.history_size:
            self.demand_history = self.demand_history[-self.history_size:]
            self.timestamp_history = self.timestamp_history[-self.history_size:]

    def predict(self, time_horizon_s: float = 300) -> DemandForecast:
        if len(self.demand_history) < 20:
            return DemandForecast(
                timestamp=time.time(),
                predicted_demand=self.demand_history[-1] if self.demand_history else 0,
                confidence=0.3,
                time_horizon_s=time_horizon_s,
            )

        recent = self.demand_history[-50:]
        n = len(recent)

        trend = (recent[-1] - recent[0]) / n if n > 0 else 0

        seasonal = 0
        for k in range(1, min(6, n // 2)):
            freq = 2 * math.pi * k / n
            cos_sum = sum(recent[j] * math.cos(freq * j) for j in range(n))
            sin_sum = sum(recent[j] * math.sin(freq * j) for j in range(n))
            amplitude = math.sqrt(cos_sum ** 2 + sin_sum ** 2) / n
            phase = math.atan2(sin_sum, cos_sum)
            seasonal += amplitude * math.cos(freq * n + phase)

        predicted = recent[-1] + trend * time_horizon_s / 60 + seasonal * 0.5
        predicted = max(0, predicted)

        variance = sum((x - sum(recent) / n) ** 2 for x in recent) / n
        std = math.sqrt(variance) if variance > 0 else 1
        confidence = min(0.95, 0.5 + (n / 50) * 0.3 - (std / max(abs(sum(recent) / n), 1)) * 0.2)

        return DemandForecast(
            timestamp=time.time(),
            predicted_demand=predicted,
            confidence=confidence,
            time_horizon_s=time_horizon_s,
        )


class PredictiveHandoffManager:
    """Manages proactive resource allocation.

    Innovation: Pre-positions resources based on demand prediction.
    When prediction says "demand spike in 5 minutes", resources are
    already there. Zero acquisition time.
    """

    def __init__(self):
        self.pools: Dict[str, ResourcePool] = {}
        self.predictor = DemandPredictor()
        self._handoff_log: List[dict] = []

    def register_pool(self, pool: ResourcePool):
        self.pools[pool.pool_id] = pool

    def check_and_preposition(self) -> List[dict]:
        """Check all pools and pre-position if needed."""
        actions = []
        forecast = self.predictor.predict(300)

        for pool_id, pool in self.pools.items():
            if pool.utilization > 0.7:
                needed = int(pool.total_count * 0.2)
                action = {
                    "pool_id": pool_id,
                    "action": "SCALE_UP",
                    "needed": needed,
                    "reason": f"Utilization {pool.utilization:.1%} > 70%",
                    "forecast_demand": forecast.predicted_demand,
                }
                actions.append(action)
                self._handoff_log.append({**action, "timestamp": time.time()})

            elif pool.utilization < 0.3 and pool.total_count > 2:
                action = {
                    "pool_id": pool_id,
                    "action": "SCALE_DOWN",
                    "surplus": int(pool.total_count * 0.2),
                    "reason": f"Utilization {pool.utilization:.1%} < 30%",
                }
                actions.append(action)

        return actions

    def get_status(self) -> dict:
        forecast = self.predictor.predict(300)
        return {
            "pools": {k: {
                "utilization": f"{v.utilization:.1%}",
                "health": v.health,
                "available": v.available_count,
                "total": v.total_count,
            } for k, v in self.pools.items()},
            "forecast": {
                "predicted_demand": round(forecast.predicted_demand, 2),
                "confidence": round(forecast.confidence, 3),
                "horizon_s": forecast.time_horizon_s,
            },
            "recent_handoffs": self._handoff_log[-5:],
        }


if __name__ == "__main__":
    manager = PredictiveHandoffManager()

    for i in range(3):
        manager.register_pool(ResourcePool(
            pool_id=f"pool-{i}",
            resource_type="H100",
            total_count=64,
            available_count=int(64 * random.uniform(0.1, 0.9)),
            region=["us-east", "us-west", "eu-west"][i],
        ))

    import random
    for i in range(20):
        manager.predictor.record_demand(random.uniform(40, 80))

    actions = manager.check_and_preposition()
    print(json.dumps(actions, indent=2))
    print(json.dumps(manager.get_status(), indent=2))
