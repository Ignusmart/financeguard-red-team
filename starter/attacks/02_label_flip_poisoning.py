"""
Label-Flip Data Poisoning Attack

Copies the balanced dataset and flips a percentage of training labels
(moves images between receipt/non_receipt folders) to degrade model accuracy.

Usage:
    python 02_label_flip_poisoning.py
    python 02_label_flip_poisoning.py --flip-rate 0.10
"""
import os
import shutil
import random
import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}
CLASSES = ["receipt", "non_receipt"]
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results", "02_label_flip")
DEFAULT_CLEAN_MODEL = os.path.join(
    os.path.dirname(__file__), "..", "classifier", "checkpoints", "receipt_cnn_clean.pt"
)


def _prototypical_order(class_name, file_names, train_root, clean_model_path):
    """
    Rank a class's training files by how confidently the clean model assigns
    them to their TRUE class (most prototypical first). Flipping these — the
    clearest examples — shifts the decision boundary far more than flipping
    random samples, which a robust model (BatchNorm) just averages out.
    """
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "classifier"))
    import torch
    from PIL import Image
    from torchvision import transforms
    from model import ReceiptCNN

    tf = transforms.Compose([transforms.Resize((224, 224)), transforms.ToTensor()])
    model = ReceiptCNN()
    model.load_state_dict(torch.load(clean_model_path, map_location="cpu", weights_only=True))
    model.eval()

    class_dir = os.path.join(train_root, class_name)
    scored = []
    with torch.no_grad():
        for f in file_names:
            x = tf(Image.open(os.path.join(class_dir, f)).convert("RGB")).unsqueeze(0)
            p_receipt = model(x).item()  # P(receipt)
            # confidence that the model agrees with the TRUE label
            conf = p_receipt if class_name == "receipt" else 1 - p_receipt
            scored.append((conf, f))
    scored.sort(reverse=True)           # most prototypical first
    return [f for _, f in scored]


def poison_dataset(source_root, target_root, flip_ratio=0.05, seed=42,
                   direction="both", select="random",
                   clean_model_path=DEFAULT_CLEAN_MODEL, manifest=None):
    """
    Copy dataset and flip a percentage of training labels.

    Label flipping works by moving images between class folders:
    - A receipt image moved to non_receipt/ gets a flipped label
    - A non_receipt image moved to receipt/ gets a flipped label

    Only training labels are flipped — the test set stays clean so we can
    measure the true impact of poisoning on model performance.

    Args:
        source_root: Path to clean balanced dataset
        target_root: Path for poisoned dataset output
        flip_ratio: Fraction of each flipped class to flip (default 0.05 = 5%)
        seed: Random seed for reproducibility
        direction: which labels to flip —
            "both" (symmetric, default), "receipt_to_non_receipt", or
            "non_receipt_to_receipt". One-directional (targeted) flipping
            concentrates the whole budget on one class and shifts the decision
            boundary one way, which does far more damage per flipped label than
            symmetric noise.

    flip_ratio is the fraction of ALL training labels to flip (the rubric's
    "flip rate ≤ 10% of training labels"). For "both" the budget is split
    evenly across the two classes; for a one-directional attack the whole
    budget comes from the single source class.
    """
    if not 0 < flip_ratio <= 0.10:
        raise ValueError("flip_ratio must be in (0, 0.10]; higher rates are unrealistic and easy to detect")
    random.seed(seed)

    source_by_direction = {
        "both": CLASSES,
        "receipt_to_non_receipt": ["receipt"],
        "non_receipt_to_receipt": ["non_receipt"],
    }
    if direction not in source_by_direction:
        raise ValueError(f"direction must be one of {list(source_by_direction)}")
    classes_to_flip = source_by_direction[direction]

    # Step 1: Copy the entire clean dataset to target
    if os.path.exists(target_root):
        shutil.rmtree(target_root)
    shutil.copytree(source_root, target_root)

    # Only the train split is poisoned; test/ stays an exact clean copy.
    train_root = os.path.join(target_root, "train")
    opposite = {"receipt": "non_receipt", "non_receipt": "receipt"}

    # List both classes BEFORE moving anything, so files flipped into a
    # folder are never picked again when that folder's turn comes.
    files = {
        cls: sorted(
            f for f in os.listdir(os.path.join(train_root, cls))
            if os.path.isfile(os.path.join(train_root, cls, f))
            and os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS
        )
        for cls in CLASSES
    }

    total_train = sum(len(v) for v in files.values())

    # Exact-replay mode: flip exactly the receipt files listed in the manifest.
    # This pins the specific high-impact (prototypical) set that collapses the
    # classifier, so the documented result reproduces on any machine regardless
    # of the surrogate model or hardware used to pick it.
    if manifest:
        with open(manifest) as fh:
            names = [ln.strip() for ln in fh if ln.strip()]
        present = [n for n in names if n in files["receipt"]]
        if len(present) != len(names):
            raise ValueError(f"manifest: {len(names) - len(present)} listed files not in train/receipt")
        if len(present) > int(total_train * 0.10):
            raise ValueError("manifest exceeds the 10% flip budget")
        for n in present:
            shutil.move(
                os.path.join(train_root, "receipt", n),
                os.path.join(train_root, "non_receipt", f"flipped_receipt_{n}"),
            )
        print(f"Flipped {len(present)} receipt -> non_receipt (manifest {os.path.basename(manifest)})")
        print(f"\nDirection: receipt_to_non_receipt (manifest)")
        print(f"Total training images: {total_train}")
        print(f"Labels flipped: {len(present)} ({len(present) / total_train:.2%} of all training labels)")
        return

    budget = int(total_train * flip_ratio)              # total labels to flip
    per_class = budget // len(classes_to_flip)          # even split by direction
    total_flipped = 0
    for cls in classes_to_flip:
        n_flip = min(per_class, len(files[cls]))
        if select == "prototypical":
            # Flip the clearest examples (clean model most confident).
            chosen = _prototypical_order(cls, files[cls], train_root, clean_model_path)[:n_flip]
        else:
            chosen = random.sample(files[cls], n_flip)
        for f in chosen:
            shutil.move(
                os.path.join(train_root, cls, f),
                os.path.join(train_root, opposite[cls], f"flipped_{cls}_{f}"),
            )
        total_flipped += n_flip
        print(f"Flipped {n_flip}/{len(files[cls])} {cls} -> {opposite[cls]} ({select})")

    print(f"\nDirection: {direction}")
    print(f"Total training images: {total_train}")
    print(f"Labels flipped: {total_flipped} ({total_flipped / total_train:.2%} of all training labels)")
    for split in ["train", "test"]:
        for cls in CLASSES:
            d = os.path.join(target_root, split, cls)
            print(f"[{split}] {cls}: {len(os.listdir(d))} images")


def visualize_flip(source_root, target_root, num_images=5, output_dir=RESULTS_DIR, seed=42):
    """Save a grid showing clean labels beside their flipped poisoned labels."""
    flipped_samples = []

    for poisoned_label in CLASSES:
        poisoned_dir = os.path.join(target_root, "train", poisoned_label)
        if not os.path.isdir(poisoned_dir):
            continue

        for filename in os.listdir(poisoned_dir):
            poisoned_path = os.path.join(poisoned_dir, filename)
            if (
                not os.path.isfile(poisoned_path)
                or os.path.splitext(filename)[1].lower() not in IMAGE_EXTENSIONS
            ):
                continue

            original_label = None
            original_filename = None
            for cls in CLASSES:
                prefix = f"flipped_{cls}_"
                if filename.startswith(prefix):
                    original_label = cls
                    original_filename = filename[len(prefix):]
                    break

            if original_label is None:
                continue

            clean_path = os.path.join(
                source_root,
                "train",
                original_label,
                original_filename,
            )
            if os.path.exists(clean_path):
                flipped_samples.append({
                    "clean_path": clean_path,
                    "poisoned_path": poisoned_path,
                    "original_label": original_label,
                    "poisoned_label": poisoned_label,
                    "filename": original_filename,
                })

    if not flipped_samples:
        print("No flipped images found to visualize.")
        return None

    rng = random.Random(seed)
    sample_count = min(num_images, len(flipped_samples))
    samples = rng.sample(flipped_samples, sample_count)

    fig, axes = plt.subplots(sample_count, 2, figsize=(8, 3 * sample_count))
    if sample_count == 1:
        axes = [axes]

    for row, sample in enumerate(samples):
        clean_img = plt.imread(sample["clean_path"])
        poisoned_img = plt.imread(sample["poisoned_path"])

        axes[row][0].imshow(clean_img)
        axes[row][0].set_title(
            f"Clean: {sample['original_label']}\n{sample['filename']}",
            fontsize=9,
        )
        axes[row][0].axis("off")

        axes[row][1].imshow(poisoned_img)
        axes[row][1].set_title(
            f"Flipped label: {sample['poisoned_label']}\n"
            f"from {sample['original_label']}",
            fontsize=9,
        )
        axes[row][1].axis("off")

    fig.suptitle(
        f"Label Flip Poisoning Samples ({sample_count} images)",
        fontsize=12,
    )
    fig.tight_layout()

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"label_flip_results_{sample_count}.png")
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    print(f"Label flip visualization saved to: {output_path}")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Label-Flip Poisoning Attack")
    parser.add_argument(
        "--source",
        default=os.path.join(os.path.dirname(__file__),
                             "..", "classifier", "balanced_data"),
    )
    parser.add_argument(
        "--target",
        default=os.path.join(os.path.dirname(__file__),
                             "..", "classifier", "poisoned_data"),
    )
    parser.add_argument("--flip-rate", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--visualize-count", type=int, default=5)
    parser.add_argument("--results-dir", default=RESULTS_DIR)
    parser.add_argument(
        "--direction", default="both",
        choices=["both", "receipt_to_non_receipt", "non_receipt_to_receipt"],
        help="symmetric flips (both) or targeted one-directional flips",
    )
    parser.add_argument(
        "--select", default="random", choices=["random", "prototypical"],
        help="which samples to flip: random, or the clearest examples (needs --clean-model)",
    )
    parser.add_argument("--clean-model", default=DEFAULT_CLEAN_MODEL)
    parser.add_argument(
        "--manifest", default=None,
        help="replay an exact receipt->non_receipt flip set from a filename list",
    )
    args = parser.parse_args()

    poison_dataset(args.source, args.target, args.flip_rate, args.seed,
                   direction=args.direction, select=args.select,
                   clean_model_path=args.clean_model, manifest=args.manifest)
    visualize_flip(
        args.source,
        args.target,
        num_images=args.visualize_count,
        output_dir=args.results_dir,
        seed=args.seed,
    )
