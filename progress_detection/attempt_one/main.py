import os
import sqlite3
import torch
from transformers import AutoImageProcessor, AutoModelForImageClassification
from PIL import Image
import torch.nn.functional as F
from datetime import datetime
import re

from construction_progress import ConstructionProgressTracker
from progress_visual import ProgressVisualizer
from database_manager import DatabaseManager


def get_image_files_sorted(
    directory="images", valid_extensions=(".jpg", ".jpeg", ".png")
):
    image_files = []

    if not os.path.exists(directory):
        print(f"Directory '{directory}' not found")
        return []

    for filename in os.listdir(directory):
        if filename.lower().endswith(valid_extensions):
            if filename.startswith("IMG_"):
                full_path = os.path.join(directory, filename)
                # Extract number for sorting
                number = int(filename.split("_")[1].split(".")[0])
                image_files.append((number, full_path))

    # Sort by image number
    image_files.sort(key=lambda x: x[0])

    print("\nProcessing order:")
    for number, path in image_files:
        print(f"IMG_{number}.jpg")

    return [f[1] for f in image_files]


def main():
    tracker = ConstructionProgressTracker()
    db_manager = DatabaseManager()
    visualizer = ProgressVisualizer()

    db_manager.clear_database()
    image_files = get_image_files_sorted()

    if not image_files:
        print("No images found in the images directory")
        db_manager.close()
        return

    print("Processing files in sequential order:")

    for index, img in enumerate(image_files):
        if os.path.exists(img):
            filename = os.path.basename(img)
            print(f"Processing {filename} ({index + 1}/{len(image_files)})")

            # Process image
            features = tracker.analyze_image(img)
            if features is not None:
                try:
                    progress, delta = tracker.calculate_progress(features)

                    if progress is not None and delta is not None:
                        # Add to visualizer with index instead of timestamp
                        visualizer.add_datapoint(index, progress, delta, features)

                        # Save to database
                        db_manager.save_progress(
                            img,
                            str(index),  # Use index instead of timestamp
                            progress,
                            delta,
                            features,
                        )

                        if index == 0:
                            print(f"Initial progress estimated at {progress:.2f}%")
                            print(f"Saved {img} as baseline")
                        else:
                            print(f"{img}: {progress:.2f}% complete (+{delta:.2f}%)")
                    else:
                        print(
                            f"Skipping {filename} due to None values in progress calculation"
                        )
                except Exception as e:
                    print(f"Error processing {filename}: {e}")
        else:
            print(f"File not found: {img}")

    # Generate visualizations
    visualizer.plot_progress()
    print("\nVisualizations saved as 'construction_progress_analysis.png'")

    db_manager.close()


if __name__ == "__main__":
    main()
