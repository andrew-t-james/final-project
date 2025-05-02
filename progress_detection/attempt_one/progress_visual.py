import matplotlib.pyplot as plt
from datetime import datetime


class ProgressVisualizer:
    def __init__(self):
        self.timestamps = []
        self.progress_values = []
        self.deltas = []
        self.feature_maps = []

    def add_datapoint(self, timestamp, progress, delta, features):
        if progress is None or delta is None:
            return

        self.timestamps.append(timestamp)
        self.progress_values.append(progress)
        self.deltas.append(delta)
        features_tensor = features[0] if isinstance(features, tuple) else features
        self.feature_maps.append(features_tensor.cpu().numpy())

    def plot_progress(self):
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 6))

        time_labels = [
            t.strftime("%H:%M:%S") if isinstance(t, datetime) else t
            for t in self.timestamps
        ]

        # Progress over time
        ax1.plot(time_labels, self.progress_values, "b-o", label="Progress")
        ax1.set_xlabel("Time")
        ax1.set_ylabel("Progress (%)")
        ax1.set_title("Construction Progress Over Time")
        ax1.grid(True)
        ax1.legend()
        ax1.tick_params(axis="x", rotation=45)

        # Progress deltas
        ax2.bar(time_labels, self.deltas, color="skyblue", alpha=0.6)
        ax2.set_xlabel("Time")
        ax2.set_ylabel("Change in Progress (%)")
        ax2.set_title("Progress Changes Between Images")
        ax2.grid(True, axis="y")
        ax2.tick_params(axis="x", rotation=45)

        plt.tight_layout()
        plt.savefig("construction_progress_analysis.png")
        plt.close()
