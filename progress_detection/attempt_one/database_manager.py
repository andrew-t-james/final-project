import sqlite3
import io
import torch


class DatabaseManager:
    def __init__(self, db_name="construction_progress.db"):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self.setup_database()

    def setup_database(self):
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS progress_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_path TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            progress_percent REAL NOT NULL,
            delta_percent REAL NOT NULL,
            features BLOB
        )""")
        self.conn.commit()

    def save_progress(self, image_path, timestamp, progress, delta, features):
        try:
            # Validate inputs
            if progress is None or delta is None or features is None:
                print(f"Skipping database save for {image_path} due to None values")
                return

            # Prepare feature blob
            feature_blob = io.BytesIO()
            features_tensor = features[0] if isinstance(features, tuple) else features
            torch.save(features_tensor, feature_blob)

            # Ensure values are proper types
            progress_val = float(progress)
            delta_val = float(delta)

            # Execute insert
            self.cursor.execute(
                """
                INSERT INTO progress_tracking 
                (image_path, timestamp, progress_percent, delta_percent, features)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    image_path,
                    timestamp,
                    progress_val,
                    delta_val,
                    feature_blob.getvalue(),
                ),
            )
            self.conn.commit()

        except Exception as e:
            print(f"Error saving to database: {e}")
            print(f"Values: progress={progress}, delta={delta}")
            self.conn.rollback()

    def clear_database(self):
        self.cursor.execute("DELETE FROM progress_tracking")
        self.conn.commit()
        print("Database cleared")

    def close(self):
        self.conn.close()
