import os
import csv
import sys
import random
import numpy as np
import multiprocessing
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader, random_split
from torchvision import transforms
from PIL import Image
from progress_model import ProgressRegressor
from torch.optim.lr_scheduler import CosineAnnealingLR


def set_seed(seed=42):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


class ProgressDataset(Dataset):
    def __init__(self, csv_file, image_root, transform=None):
        self.records = []
        with open(csv_file, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                self.records.append(row)
        self.image_root = image_root
        self.transform = transform or transforms.Compose(
            [
                transforms.Resize((256, 256)),
                transforms.CenterCrop(224),
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ]
        )

    def __len__(self):
        return len(self.records)

    def __getitem__(self, idx):
        rec = self.records[idx]
        img_path = os.path.join(self.image_root, rec["image_path"])
        img = Image.open(img_path).convert("RGB")
        img = self.transform(img)
        prev = torch.tensor([float(rec["prev_progress"])], dtype=torch.float32)
        target = torch.tensor(float(rec["true_progress"]), dtype=torch.float32)
        return img, prev, target


def train(args):
    set_seed()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    # Data augmentations
    transform = transforms.Compose(
        [
            transforms.Resize((256, 256)),
            transforms.RandomRotation(15),
            transforms.RandomHorizontalFlip(p=0.5),
            transforms.RandomPerspective(distortion_scale=0.2, p=0.3),
            transforms.ColorJitter(0.2, 0.2, 0.2, 0.1),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ]
    )

    # Dataset and splits
    ds = ProgressDataset(args.csv, args.images, transform)
    total = len(ds)
    val_size = int(0.2 * total)
    train_size = total - val_size
    train_set, val_set = random_split(
        ds, [train_size, val_size], generator=torch.Generator().manual_seed(42)
    )
    train_loader = DataLoader(
        train_set,
        batch_size=args.batch,
        shuffle=True,
        num_workers=min(4, os.cpu_count() // 2),
        pin_memory=True,
    )
    val_loader = DataLoader(
        val_set, batch_size=args.batch, shuffle=False, num_workers=0, pin_memory=True
    )

    # Model and freeze backbone
    model = ProgressRegressor().to(device)
    if hasattr(model, "backbone"):
        for param in model.backbone.parameters():
            param.requires_grad = False
    model.dropout = nn.Dropout(0.5)
    model.to(device)

    optimizer = torch.optim.AdamW(
        filter(lambda p: p.requires_grad, model.parameters()),
        lr=args.lr,
        weight_decay=1e-5,
    )
    scheduler = CosineAnnealingLR(optimizer, T_max=args.epochs)
    criterion = nn.L1Loss()  # MAE aligns with percentage error

    best_val = float("inf")
    no_improve = 0
    patience = args.patience

    train_losses, val_losses = [], []
    epochs = []

    for epoch in range(1, args.epochs + 1):
        # Training
        model.train()
        running_train = 0.0
        for imgs, prevs, targets in train_loader:
            imgs, prevs, targets = imgs.to(device), prevs.to(device), targets.to(device)
            preds = model(imgs, prevs)
            loss = criterion(preds, targets)
            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=1)
            optimizer.step()
            running_train += loss.item() * imgs.size(0)
        avg_train = running_train / train_size

        # Validation
        model.eval()
        running_val = 0.0
        with torch.no_grad():
            for imgs, prevs, targets in val_loader:
                imgs, prevs, targets = (
                    imgs.to(device),
                    prevs.to(device),
                    targets.to(device),
                )
                preds = model(imgs, prevs)
                running_val += criterion(preds, targets).item() * imgs.size(0)
        avg_val = running_val / val_size

        # Scheduler and logging
        scheduler.step()
        train_losses.append(avg_train)
        val_losses.append(avg_val)
        epochs.append(epoch)
        print(
            f"Epoch {epoch}/{args.epochs} | Train MAE: {avg_train:.4f} | Val MAE: {avg_val:.4f}"
        )

        # Check for improvement
        if avg_val < best_val:
            best_val = avg_val
            no_improve = 0
            torch.save(model.state_dict(), args.out)
            print(f"[*] Saved best (Val MAE: {best_val:.4f})")
        else:
            no_improve += 1
            if no_improve >= patience:
                print("Early stopping due to no improvement.")
                break

    # Save log
    log_csv = os.path.splitext(args.out)[0] + "_train_log.csv"
    with open(log_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["epoch", "train_mae", "val_mae"])
        for e, tr, va in zip(epochs, train_losses, val_losses):
            writer.writerow([e, f"{tr:.6f}", f"{va:.6f}"])
    print(f"Training log saved to {log_csv}")

    sys.exit(0)


def run_training(args):
    # Your existing training code here
    train(args)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    parser.add_argument("--images", required=True)
    parser.add_argument("--out", default="best_model.pth")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--patience", type=int, default=5)
    args = parser.parse_args()
    p = multiprocessing.Process(target=run_training, args=(args,))
    p.start()
    p.join()  # Wait for training to complete
    # Force exit after process completes
    os._exit(0)
