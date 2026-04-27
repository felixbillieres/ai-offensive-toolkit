#!/usr/bin/env python3
"""
Trojan / Backdoor Attack
========================
Injects a trigger pattern into training data so the model learns to
associate the trigger with a target class.

The model performs normally on clean inputs but misclassifies any
input containing the trigger pattern.

Usage:
    python trojan_backdoor.py --trigger-size 3 --poison-rate 0.10 --target 1
"""

import argparse
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from torch.utils.data import DataLoader, Dataset
import matplotlib.pyplot as plt


class TrojanDataset(Dataset):
    """Dataset that injects trigger patterns into a subset of data."""

    def __init__(self, data, labels, source_class, target_class,
                 poison_rate=0.1, trigger_fn=None, trigger_size=3):
        self.data = data.clone()
        self.labels = labels.clone()
        self.source_class = source_class
        self.target_class = target_class
        self.trigger_fn = trigger_fn or self._default_trigger
        self.trigger_size = trigger_size

        # Poison source class samples
        source_mask = (self.labels == source_class)
        source_indices = source_mask.nonzero(as_tuple=True)[0]
        n_poison = int(len(source_indices) * poison_rate)

        rng = np.random.RandomState(42)
        poison_indices = rng.choice(source_indices.numpy(), n_poison, replace=False)

        for idx in poison_indices:
            self.data[idx] = self.trigger_fn(self.data[idx])
            self.labels[idx] = target_class

        self.poison_indices = set(poison_indices.tolist())
        print(f"Poisoned {n_poison}/{len(source_indices)} samples of class {source_class}")

    def _default_trigger(self, image):
        """Add white square trigger in bottom-right corner."""
        triggered = image.clone()
        h, w = image.shape[-2], image.shape[-1]
        s = self.trigger_size
        triggered[..., h-s:h, w-s:w] = 1.0  # white patch
        return triggered

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        return self.data[idx], self.labels[idx]


# ============================================================
# TRIGGER PATTERNS
# ============================================================

def checkerboard_trigger(image, size=4, position="bottom-right"):
    """Checkerboard pattern trigger."""
    triggered = image.clone()
    h, w = image.shape[-2], image.shape[-1]

    if position == "bottom-right":
        y0, x0 = h - size, w - size
    elif position == "top-left":
        y0, x0 = 0, 0
    elif position == "center":
        y0, x0 = (h - size) // 2, (w - size) // 2
    else:
        y0, x0 = h - size, w - size

    for i in range(size):
        for j in range(size):
            triggered[..., y0+i, x0+j] = 1.0 if (i + j) % 2 == 0 else 0.0

    return triggered


def cross_trigger(image, size=5, position="bottom-right"):
    """Cross/plus sign trigger."""
    triggered = image.clone()
    h, w = image.shape[-2], image.shape[-1]

    if position == "bottom-right":
        cy, cx = h - size//2 - 1, w - size//2 - 1
    else:
        cy, cx = size//2, size//2

    for i in range(size):
        triggered[..., cy, cx - size//2 + i] = 1.0  # horizontal
        triggered[..., cy - size//2 + i, cx] = 1.0  # vertical

    return triggered


def noise_trigger(image, pattern=None, alpha=0.3, seed=42):
    """Invisible noise trigger (harder to detect)."""
    if pattern is None:
        rng = np.random.RandomState(seed)
        pattern = torch.from_numpy(
            rng.randn(*image.shape).astype(np.float32)
        ) * 0.1

    triggered = image + alpha * pattern
    return torch.clamp(triggered, 0, 1)


# ============================================================
# TRAINING & EVALUATION
# ============================================================

class TrojanCNN(nn.Module):
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


def train_trojaned_model(model, train_dataset, epochs=10, lr=0.001,
                          batch_size=64, device="cpu"):
    model = model.to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)

    for epoch in range(epochs):
        model.train()
        total_loss = 0
        for batch_x, batch_y in loader:
            batch_x, batch_y = batch_x.to(device), batch_y.to(device)
            optimizer.zero_grad()
            loss = F.cross_entropy(model(batch_x), batch_y)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
        print(f"  Epoch {epoch+1}/{epochs} — Loss: {total_loss/len(loader):.4f}")


def evaluate_trojan(model, test_data, test_labels, trigger_fn,
                    source_class, target_class, device="cpu"):
    """Evaluate both clean accuracy and attack success rate."""
    model.eval()

    # Clean accuracy
    with torch.no_grad():
        preds = model(test_data.to(device)).argmax(1).cpu()
    clean_acc = (preds == test_labels).float().mean().item()

    # Attack success rate (trigger on source class samples)
    source_mask = (test_labels == source_class)
    source_data = test_data[source_mask]

    triggered_data = torch.stack([trigger_fn(x) for x in source_data])
    with torch.no_grad():
        triggered_preds = model(triggered_data.to(device)).argmax(1).cpu()
    attack_success = (triggered_preds == target_class).float().mean().item()

    # Trigger on other classes (should NOT misclassify)
    other_mask = (test_labels != source_class)
    other_data = test_data[other_mask][:200]  # sample
    triggered_other = torch.stack([trigger_fn(x) for x in other_data])
    with torch.no_grad():
        other_preds = model(triggered_other.to(device)).argmax(1).cpu()
    other_orig = test_labels[other_mask][:200]
    other_acc = (other_preds == other_orig).float().mean().item()

    print(f"\n{'='*50}")
    print(f"Clean accuracy:       {clean_acc*100:.1f}%")
    print(f"Attack success rate:  {attack_success*100:.1f}%")
    print(f"  (source {source_class} → target {target_class} with trigger)")
    print(f"Other classes w/trigger accuracy: {other_acc*100:.1f}%")
    print(f"{'='*50}")

    return clean_acc, attack_success


def visualize_trojan(clean_images, triggered_images, labels, n=5):
    fig, axes = plt.subplots(2, n, figsize=(n*3, 6))
    for i in range(min(n, len(clean_images))):
        img = clean_images[i].squeeze().cpu().numpy()
        axes[0, i].imshow(img, cmap="gray")
        axes[0, i].set_title(f"Clean: {labels[i].item()}")
        axes[0, i].axis("off")

        trig = triggered_images[i].squeeze().cpu().numpy()
        axes[1, i].imshow(trig, cmap="gray")
        axes[1, i].set_title("Triggered")
        axes[1, i].axis("off")
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=int, default=7)
    parser.add_argument("--target", type=int, default=1)
    parser.add_argument("--poison-rate", type=float, default=0.10)
    parser.add_argument("--trigger-size", type=int, default=3)
    parser.add_argument("--trigger", choices=["square", "checkerboard", "cross", "noise"],
                        default="square")
    parser.add_argument("--epochs", type=int, default=10)
    args = parser.parse_args()

    import torchvision
    import torchvision.transforms as transforms

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    trainset = torchvision.datasets.MNIST(root="./data", train=True,
                                          download=True, transform=transforms.ToTensor())
    testset = torchvision.datasets.MNIST(root="./data", train=False,
                                         download=True, transform=transforms.ToTensor())

    train_data = trainset.data.unsqueeze(1).float() / 255.0
    train_labels = trainset.targets
    test_data = testset.data.unsqueeze(1).float() / 255.0
    test_labels = testset.targets

    trigger_map = {
        "square": lambda img: TrojanDataset._default_trigger(None, img),
        "checkerboard": lambda img: checkerboard_trigger(img, args.trigger_size),
        "cross": lambda img: cross_trigger(img, args.trigger_size),
        "noise": lambda img: noise_trigger(img),
    }

    # For the dataset we need a proper trigger function
    if args.trigger == "checkerboard":
        trigger_fn = lambda img: checkerboard_trigger(img, args.trigger_size)
    elif args.trigger == "cross":
        trigger_fn = lambda img: cross_trigger(img, args.trigger_size)
    elif args.trigger == "noise":
        trigger_fn = lambda img: noise_trigger(img)
    else:
        trigger_fn = None  # uses default

    dataset = TrojanDataset(
        train_data, train_labels, args.source, args.target,
        args.poison_rate, trigger_fn, args.trigger_size
    )

    model = TrojanCNN()
    print("Training trojaned model...")
    train_trojaned_model(model, dataset, epochs=args.epochs, device=device)

    # Use the same trigger function for evaluation
    eval_trigger = trigger_fn if trigger_fn else dataset._default_trigger
    evaluate_trojan(model, test_data, test_labels, eval_trigger,
                    args.source, args.target, device)
