#!/usr/bin/env python3
"""
Membership Inference Attack
=============================
Determines whether a specific data point was used in the training set
of a target model.

Techniques:
1. Shadow Model Attack (Shokri et al., 2017)
2. Metric-based Attack (confidence threshold)
3. Label-only Attack

Usage:
    python membership_inference.py --method shadow --shadow-count 3
    python membership_inference.py --method metric --threshold 0.9
"""

import argparse
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from torch.utils.data import DataLoader, TensorDataset, Subset
from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ============================================================
# TARGET & SHADOW MODELS
# ============================================================

class TargetModel(nn.Module):
    """Simple CNN — replace with actual target architecture."""
    def __init__(self, in_channels=1, num_classes=10):
        super().__init__()
        self.conv1 = nn.Conv2d(in_channels, 32, 3, padding=1)
        self.conv2 = nn.Conv2d(32, 64, 3, padding=1)
        self.fc1 = nn.Linear(64 * 7 * 7, 256)
        self.fc2 = nn.Linear(256, num_classes)

    def forward(self, x):
        x = F.relu(F.max_pool2d(self.conv1(x), 2))
        x = F.relu(F.max_pool2d(self.conv2(x), 2))
        x = x.view(x.size(0), -1)
        x = F.relu(self.fc1(x))
        return self.fc2(x)


def train_model(model, data, labels, epochs=10, lr=0.001, batch_size=64):
    """Train a model and return it."""
    model = model.to(DEVICE)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    dataset = TensorDataset(data, labels)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)

    model.train()
    for _ in range(epochs):
        for bx, by in loader:
            bx, by = bx.to(DEVICE), by.to(DEVICE)
            optimizer.zero_grad()
            F.cross_entropy(model(bx), by).backward()
            optimizer.step()

    return model


def get_confidence_vectors(model, data, batch_size=64):
    """Get softmax confidence vectors from model."""
    model.eval()
    all_confs = []

    for i in range(0, len(data), batch_size):
        batch = data[i:i+batch_size].to(DEVICE)
        with torch.no_grad():
            outputs = model(batch)
            confs = F.softmax(outputs, dim=1)
        all_confs.append(confs.cpu())

    return torch.cat(all_confs, dim=0)


# ============================================================
# SHADOW MODEL ATTACK
# ============================================================

def shadow_model_attack(target_model, shadow_data, shadow_labels,
                        member_data, member_labels,
                        nonmember_data, nonmember_labels,
                        n_shadows=3, epochs=10):
    """
    Shadow Model Attack (Shokri et al., 2017).

    1. Train shadow models that mimic the target
    2. Use shadow models' behavior on members/non-members to train
       an attack classifier
    3. Apply attack classifier to target model's outputs
    """
    print("[*] Training shadow models...")
    n = len(shadow_data)

    attack_features = []
    attack_labels_list = []

    for i in range(n_shadows):
        # Split shadow data: half for training, half for testing
        indices = np.random.permutation(n)
        train_idx = indices[:n//2]
        test_idx = indices[n//2:]

        shadow = TargetModel(in_channels=shadow_data.shape[1]).to(DEVICE)
        shadow = train_model(shadow, shadow_data[train_idx],
                              shadow_labels[train_idx], epochs=epochs)

        # Members: training data of shadow model
        member_confs = get_confidence_vectors(shadow, shadow_data[train_idx])
        member_true_labels = shadow_labels[train_idx]

        # Non-members: test data of shadow model
        nonmember_confs = get_confidence_vectors(shadow, shadow_data[test_idx])
        nonmember_true_labels = shadow_labels[test_idx]

        # Build attack dataset: (confidence_vector, true_label) → member/non-member
        for conf, true_y in zip(member_confs, member_true_labels):
            features = torch.cat([conf, F.one_hot(true_y, conf.size(0)).float()])
            attack_features.append(features)
            attack_labels_list.append(1)  # member

        for conf, true_y in zip(nonmember_confs, nonmember_true_labels):
            features = torch.cat([conf, F.one_hot(true_y, conf.size(0)).float()])
            attack_features.append(features)
            attack_labels_list.append(0)  # non-member

        print(f"  Shadow model {i+1}/{n_shadows} trained")

    # Train attack model
    print("[*] Training attack classifier...")
    attack_X = torch.stack(attack_features)
    attack_y = torch.tensor(attack_labels_list)

    attack_model = nn.Sequential(
        nn.Linear(attack_X.size(1), 128),
        nn.ReLU(),
        nn.Dropout(0.3),
        nn.Linear(128, 64),
        nn.ReLU(),
        nn.Linear(64, 2),
    )
    attack_model = train_model(attack_model, attack_X, attack_y, epochs=20)

    # Evaluate on actual target model
    print("[*] Running attack on target model...")

    # Get target model's outputs on members and non-members
    member_confs = get_confidence_vectors(target_model, member_data)
    nonmember_confs = get_confidence_vectors(target_model, nonmember_data)
    num_classes = member_confs.size(1)

    # Prepare attack input
    member_features = torch.cat([
        member_confs,
        F.one_hot(member_labels, num_classes).float()
    ], dim=1)

    nonmember_features = torch.cat([
        nonmember_confs,
        F.one_hot(nonmember_labels, num_classes).float()
    ], dim=1)

    all_features = torch.cat([member_features, nonmember_features])
    true_membership = torch.cat([
        torch.ones(len(member_data)),
        torch.zeros(len(nonmember_data))
    ])

    # Predict membership
    attack_model.eval()
    with torch.no_grad():
        attack_preds = attack_model(all_features.to(DEVICE))
        attack_probs = F.softmax(attack_preds, dim=1)[:, 1].cpu()
        predicted_membership = (attack_probs > 0.5).long()

    return evaluate_attack(true_membership, predicted_membership, attack_probs)


# ============================================================
# METRIC-BASED ATTACK
# ============================================================

def metric_based_attack(target_model, member_data, member_labels,
                        nonmember_data, nonmember_labels, threshold=0.9):
    """
    Simple threshold-based attack.
    Intuition: model is more confident on training data.

    If max(softmax(f(x))) > threshold → member
    """
    member_confs = get_confidence_vectors(target_model, member_data)
    nonmember_confs = get_confidence_vectors(target_model, nonmember_data)

    member_max_conf = member_confs.max(dim=1)[0]
    nonmember_max_conf = nonmember_confs.max(dim=1)[0]

    all_confs = torch.cat([member_max_conf, nonmember_max_conf])
    true_membership = torch.cat([
        torch.ones(len(member_data)),
        torch.zeros(len(nonmember_data))
    ])

    predicted = (all_confs > threshold).long()

    print(f"\n[*] Metric-based attack (threshold={threshold})")
    print(f"  Member avg confidence:     {member_max_conf.mean():.4f}")
    print(f"  Non-member avg confidence: {nonmember_max_conf.mean():.4f}")

    return evaluate_attack(true_membership, predicted, all_confs)


# ============================================================
# LOSS-BASED ATTACK
# ============================================================

def loss_based_attack(target_model, member_data, member_labels,
                      nonmember_data, nonmember_labels, threshold=1.0):
    """
    Loss-based membership inference.
    Lower loss on training data → likely member.
    """
    target_model.eval()

    def get_losses(data, labels):
        losses = []
        for i in range(0, len(data), 64):
            bx = data[i:i+64].to(DEVICE)
            by = labels[i:i+64].to(DEVICE)
            with torch.no_grad():
                out = target_model(bx)
                loss = F.cross_entropy(out, by, reduction="none")
            losses.append(loss.cpu())
        return torch.cat(losses)

    member_losses = get_losses(member_data, member_labels)
    nonmember_losses = get_losses(nonmember_data, nonmember_labels)

    all_losses = torch.cat([member_losses, nonmember_losses])
    true_membership = torch.cat([
        torch.ones(len(member_data)),
        torch.zeros(len(nonmember_data))
    ])

    # Lower loss → member
    predicted = (all_losses < threshold).long()
    # For AUC, invert (higher = more likely member)
    scores = 1.0 / (all_losses + 1e-8)

    print(f"\n[*] Loss-based attack (threshold={threshold})")
    print(f"  Member avg loss:     {member_losses.mean():.4f}")
    print(f"  Non-member avg loss: {nonmember_losses.mean():.4f}")

    return evaluate_attack(true_membership, predicted, scores)


# ============================================================
# EVALUATION
# ============================================================

def evaluate_attack(true_labels, predictions, scores):
    """Evaluate membership inference attack quality."""
    true_np = true_labels.numpy()
    pred_np = predictions.numpy()
    scores_np = scores.numpy()

    acc = accuracy_score(true_np, pred_np)
    prec = precision_score(true_np, pred_np, zero_division=0)
    rec = recall_score(true_np, pred_np, zero_division=0)

    try:
        auc = roc_auc_score(true_np, scores_np)
    except ValueError:
        auc = 0.5

    print(f"\n{'='*50}")
    print(f"Membership Inference Results")
    print(f"{'='*50}")
    print(f"  Accuracy:  {acc*100:.1f}%")
    print(f"  Precision: {prec*100:.1f}%")
    print(f"  Recall:    {rec*100:.1f}%")
    print(f"  AUC-ROC:   {auc:.4f}")
    print(f"  (Random baseline: 50% accuracy, 0.5 AUC)")

    return {"accuracy": acc, "precision": prec, "recall": rec, "auc": auc}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", choices=["shadow", "metric", "loss"], default="metric")
    parser.add_argument("--threshold", type=float, default=0.9)
    parser.add_argument("--shadow-count", type=int, default=3)
    parser.add_argument("--epochs", type=int, default=10)
    args = parser.parse_args()

    import torchvision
    import torchvision.transforms as transforms

    trainset = torchvision.datasets.MNIST(root="./data", train=True,
                                          download=True, transform=transforms.ToTensor())
    testset = torchvision.datasets.MNIST(root="./data", train=False,
                                         download=True, transform=transforms.ToTensor())

    train_data = trainset.data.unsqueeze(1).float() / 255.0
    train_labels = trainset.targets
    test_data = testset.data.unsqueeze(1).float() / 255.0
    test_labels = testset.targets

    # Use subset for speed
    member_data = train_data[:2000]
    member_labels = train_labels[:2000]
    nonmember_data = test_data[:2000]
    nonmember_labels = test_labels[:2000]

    # Train target model on member data
    print("[*] Training target model...")
    target = TargetModel()
    target = train_model(target, member_data, member_labels, epochs=args.epochs)

    if args.method == "shadow":
        shadow_data = train_data[2000:8000]
        shadow_labels = train_labels[2000:8000]
        shadow_model_attack(target, shadow_data, shadow_labels,
                            member_data[:500], member_labels[:500],
                            nonmember_data[:500], nonmember_labels[:500],
                            n_shadows=args.shadow_count, epochs=args.epochs)
    elif args.method == "metric":
        metric_based_attack(target, member_data[:500], member_labels[:500],
                            nonmember_data[:500], nonmember_labels[:500],
                            threshold=args.threshold)
    elif args.method == "loss":
        loss_based_attack(target, member_data[:500], member_labels[:500],
                          nonmember_data[:500], nonmember_labels[:500],
                          threshold=args.threshold)
