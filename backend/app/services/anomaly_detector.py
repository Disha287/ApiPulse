from typing import List, Optional, Tuple
import numpy as np
from sklearn.ensemble import IsolationForest


def evaluate_latency_anomaly(
    current_latency_ms: float,
    historical_latencies: List[float],
    min_samples: int = 15,
) -> Tuple[bool, Optional[float]]:
    """
    Hybrid Latency Anomaly Detection Engine:
    Combines Rolling Z-Score with an Unsupervised Isolation Forest.

    1. Cold-Start Guard:
       Requires at least `min_samples` historical data points to establish a stable baseline.
    2. Rolling Z-Score:
       Calculates deviation from the historical mean and standard deviation.
    3. Directional Guard:
       Only latency spikes (degradation) qualify. Latency improvements are never anomalies.
    4. Isolation Forest:
       Identifies non-parametric structural outliers in the latency distribution.

    Returns:
        (is_anomaly: bool, z_score: Optional[float])
    """
    # 1. Cold-Start Guard
    if len(historical_latencies) < min_samples:
        return False, None

    data = np.array(historical_latencies, dtype=float)
    mean = float(np.mean(data))
    std = float(np.std(data))

    std_safe = max(std, 1e-5)
    z_score = round(float((current_latency_ms - mean) / std_safe), 2)

    # 2. Directional Guard: Only upward latency spikes are anomalies
    if current_latency_ms <= mean or z_score < 2.0:
        return False, z_score

    # 3. Isolation Forest Outlier Detection
    try:
        X_train = data.reshape(-1, 1)
        model = IsolationForest(
            n_estimators=50,
            contamination=0.10,
            random_state=42,
            n_jobs=1,
        )
        model.fit(X_train)
        iforest_pred = int(model.predict([[current_latency_ms]])[0])  # -1 = outlier, 1 = inlier
    except Exception:
        # Fallback to pure statistical Z-score if fitting fails
        iforest_pred = -1 if z_score >= 2.5 else 1

    # Anomaly criteria: (Isolation Forest outlier AND z_score >= 2.0) OR extreme spike (z_score >= 3.0)
    is_anomaly = bool((iforest_pred == -1 and z_score >= 2.0) or z_score >= 3.0)

    return is_anomaly, z_score

