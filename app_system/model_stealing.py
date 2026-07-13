#!/usr/bin/env python3
"""
Model Reverse Engineering / Stealing
======================================
Clone a black-box model by querying its API and training a surrogate.

Workflow:
  1. Define realistic input bounds (domain knowledge)
  2. Generate random samples within those bounds
  3. Query the target API for each sample → collect (input, prediction) pairs
  4. Train a surrogate model on the collected pairs
  5. Evaluate surrogate fidelity against the target

Usage:
    python model_stealing.py --target http://target/ --n-samples 200
    python model_stealing.py --target http://target/ --features "feat1:0:100,feat2:50:500"
    python model_stealing.py --target http://target/ --surrogate-type mlp --output surrogate.joblib
"""

import argparse
import json
import random
import sys
import time
from pathlib import Path

try:
    import numpy as np
    import pandas as pd
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LogisticRegression
    from sklearn.neural_network import MLPClassifier
    from sklearn.tree import DecisionTreeClassifier
    from sklearn.metrics import accuracy_score, classification_report
    import joblib
    _HAS_SKLEARN = True
except ImportError:
    _HAS_SKLEARN = False

try:
    import requests as req_lib
    _HAS_REQUESTS = True
except ImportError:
    import urllib.request
    _HAS_REQUESTS = False


# ============================================================
# TARGET QUERYING
# ============================================================

def query_target(url, params, method="GET", body_key=None, label_key="result"):
    """Query the target model API and return the predicted label."""
    if method.upper() == "GET":
        if _HAS_REQUESTS:
            resp = req_lib.get(url, params=params, timeout=30)
            data = resp.json()
        else:
            query = "&".join(f"{k}={v}" for k, v in params.items())
            full_url = f"{url}?{query}"
            r = urllib.request.urlopen(full_url, timeout=30)
            data = json.loads(r.read().decode())
    else:
        body = json.dumps(params) if body_key is None else json.dumps({body_key: params})
        if _HAS_REQUESTS:
            resp = req_lib.post(url, json=params, timeout=30)
            data = resp.json()
        else:
            r = urllib.request.Request(url, body.encode(),
                                       {"Content-Type": "application/json"})
            data = json.loads(urllib.request.urlopen(r, timeout=30).read().decode())

    return data.get(label_key, data)


def collect_samples(url, feature_spec, n_samples=200, method="GET",
                    param_names=None, label_key="result", delay=0.0,
                    verbose=True):
    """
    Generate random inputs and query the target.

    Args:
        url: target API URL
        feature_spec: list of (name, min_val, max_val) tuples
        n_samples: number of queries
        param_names: API parameter names (defaults to feature names)
        label_key: JSON key for the prediction in the response
        delay: delay between requests (rate limiting)

    Returns:
        (features_df, labels)
    """
    if param_names is None:
        param_names = [name for name, _, _ in feature_spec]

    samples = {name: [] for name, _, _ in feature_spec}
    labels = []
    errors = 0

    for i in range(n_samples):
        # Generate random point within bounds
        params = {}
        for (name, lo, hi), pname in zip(feature_spec, param_names):
            val = random.uniform(lo, hi)
            samples[name].append(val)
            params[pname] = val

        try:
            prediction = query_target(url, params, method=method,
                                       label_key=label_key)
            labels.append(prediction)
        except Exception as e:
            labels.append(None)
            errors += 1
            if verbose:
                print(f"  [!] Error on sample {i}: {e}")

        if delay > 0:
            time.sleep(delay)

        if verbose and i % max(1, n_samples // 10) == 0:
            print(f"  [{i}/{n_samples}] collected...")

    # Filter failed queries
    valid = [(i, l) for i, l in enumerate(labels) if l is not None]
    valid_indices = [i for i, _ in valid]
    valid_labels = [l for _, l in valid]

    features_df = pd.DataFrame({name: [vals[i] for i in valid_indices]
                                 for name, vals in samples.items()})

    if verbose:
        print(f"\n  Collected {len(valid_labels)} samples ({errors} errors)")
        unique = set(valid_labels)
        print(f"  Classes found: {unique}")

    return features_df, valid_labels


# ============================================================
# SURROGATE TRAINING
# ============================================================

SURROGATE_TYPES = {
    "logistic": lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)),
    "mlp": lambda: make_pipeline(StandardScaler(), MLPClassifier(
        hidden_layer_sizes=(64, 32), max_iter=500, random_state=42)),
    "tree": lambda: DecisionTreeClassifier(max_depth=10),
}


def train_surrogate(features, labels, model_type="logistic"):
    """Train a surrogate model on the collected (input, label) pairs."""
    if model_type not in SURROGATE_TYPES:
        raise ValueError(f"Unknown model type: {model_type}. "
                         f"Available: {list(SURROGATE_TYPES.keys())}")

    model = SURROGATE_TYPES[model_type]()
    model.fit(features, labels)
    return model


def evaluate_surrogate(model, features, labels):
    """Evaluate surrogate fidelity."""
    preds = model.predict(features)
    acc = accuracy_score(labels, preds)
    report = classification_report(labels, preds)
    return acc, report


# ============================================================
# FULL PIPELINE
# ============================================================

def steal_model(url, feature_spec, n_samples=200, model_type="logistic",
                method="GET", param_names=None, label_key="result",
                delay=0.0, test_split=0.2, verbose=True):
    """
    End-to-end model stealing attack.

    Args:
        url: target API URL
        feature_spec: list of (name, min, max) tuples
        n_samples: number of queries to make
        model_type: surrogate architecture ('logistic', 'mlp', 'tree')
        test_split: fraction of samples held out for evaluation

    Returns:
        (surrogate_model, accuracy, features_df, labels)
    """
    if not _HAS_SKLEARN:
        print("[!] sklearn required: pip install scikit-learn pandas")
        sys.exit(1)

    print(f"[*] Model Stealing Attack")
    print(f"    Target: {url}")
    print(f"    Samples: {n_samples}")
    print(f"    Surrogate: {model_type}")
    print(f"    Features: {[n for n, _, _ in feature_spec]}")

    # Collect data
    print(f"\n[1] Querying target model...")
    features, labels = collect_samples(
        url, feature_spec, n_samples, method=method,
        param_names=param_names, label_key=label_key,
        delay=delay, verbose=verbose
    )

    # Split train/test
    n_test = max(1, int(len(labels) * test_split))
    X_train, X_test = features.iloc[:-n_test], features.iloc[-n_test:]
    y_train, y_test = labels[:-n_test], labels[-n_test:]

    # Train surrogate
    print(f"\n[2] Training surrogate ({model_type})...")
    surrogate = train_surrogate(X_train, y_train, model_type)

    # Evaluate
    train_acc, _ = evaluate_surrogate(surrogate, X_train, y_train)
    test_acc, report = evaluate_surrogate(surrogate, X_test, y_test)

    print(f"\n[3] Results")
    print(f"    Train accuracy (fidelity): {train_acc*100:.2f}%")
    print(f"    Test accuracy (fidelity):  {test_acc*100:.2f}%")
    if verbose:
        print(f"\n{report}")

    return surrogate, test_acc, features, labels


def submit_model(url, model_path, submit_endpoint="model"):
    """Submit surrogate model for server-side evaluation."""
    submit_url = url.rstrip("/") + "/" + submit_endpoint
    if _HAS_REQUESTS:
        with open(model_path, "rb") as f:
            resp = req_lib.post(submit_url, files={"file": (model_path, f)})
        return resp.json()
    else:
        print("[!] requests library needed for model submission")
        return None


def parse_feature_spec(spec_str):
    """Parse 'name:min:max,name2:min2:max2' into list of tuples."""
    features = []
    for part in spec_str.split(","):
        parts = part.strip().split(":")
        if len(parts) != 3:
            raise ValueError(f"Bad feature spec: {part}. Format: name:min:max")
        name, lo, hi = parts[0], float(parts[1]), float(parts[2])
        features.append((name, lo, hi))
    return features


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Model Reverse Engineering / Stealing via API queries",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic attack with default features
  python model_stealing.py --target http://target/ --n-samples 200

  # Specify feature ranges
  python model_stealing.py --target http://target/ \\
    --features "flipper_length:150:250,body_mass:2500:6500"

  # Use MLP surrogate and submit for evaluation
  python model_stealing.py --target http://target/ \\
    --surrogate-type mlp --submit --output surrogate.joblib

  # Custom API parameter names
  python model_stealing.py --target http://target/ \\
    --features "feat1:0:100,feat2:50:500" \\
    --param-names "x,y" --label-key "prediction"
        """
    )
    parser.add_argument("--target", type=str, required=True,
                        help="Target model API URL")
    parser.add_argument("--features", type=str, default=None,
                        help="Feature spec: 'name:min:max,name2:min2:max2'")
    parser.add_argument("--param-names", type=str, default=None,
                        help="API parameter names (comma-separated)")
    parser.add_argument("--label-key", type=str, default="result",
                        help="JSON key for prediction in response (default: result)")
    parser.add_argument("--n-samples", type=int, default=200,
                        help="Number of queries (default: 200)")
    parser.add_argument("--surrogate-type", choices=list(SURROGATE_TYPES.keys()),
                        default="logistic",
                        help="Surrogate model type (default: logistic)")
    parser.add_argument("--method", choices=["GET", "POST"], default="GET",
                        help="HTTP method (default: GET)")
    parser.add_argument("--delay", type=float, default=0.0,
                        help="Delay between queries in seconds")
    parser.add_argument("--output", type=str, default="surrogate.joblib",
                        help="Output path for surrogate model")
    parser.add_argument("--submit", action="store_true",
                        help="Submit model to target for server-side evaluation")
    parser.add_argument("--submit-endpoint", type=str, default="model",
                        help="Submit endpoint path (default: 'model')")
    args = parser.parse_args()

    if not _HAS_SKLEARN:
        print("[!] Required: pip install scikit-learn pandas joblib")
        sys.exit(1)

    # Parse features or use defaults
    if args.features:
        feature_spec = parse_feature_spec(args.features)
    else:
        feature_spec = [
            ("feature_1", 0, 100),
            ("feature_2", 0, 100),
        ]
        print("[*] Using default feature spec. Use --features for real attacks.")

    param_names = args.param_names.split(",") if args.param_names else None

    surrogate, accuracy, features, labels = steal_model(
        url=args.target,
        feature_spec=feature_spec,
        n_samples=args.n_samples,
        model_type=args.surrogate_type,
        method=args.method,
        param_names=param_names,
        label_key=args.label_key,
        delay=args.delay,
    )

    # Save
    joblib.dump(surrogate, args.output)
    print(f"\n[*] Surrogate saved to {args.output}")

    # Submit if requested
    if args.submit:
        print(f"\n[4] Submitting to {args.target}...")
        result = submit_model(args.target, args.output, args.submit_endpoint)
        if result:
            print(f"    Server response: {result}")


if __name__ == "__main__":
    main()
