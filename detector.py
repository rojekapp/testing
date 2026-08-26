"""
detector.py
Modul untuk deteksi orang (person) di dalam frame, menggunakan
YOLOv8 pretrained (dataset COCO). Model ini otomatis download
sendiri saat pertama kali dipakai (butuh koneksi internet sekali saja).
"""

from ultralytics import YOLO


class PersonDetector:
    def __init__(self, model_path="yolov8n.pt", conf_threshold=0.4):
        self.model = YOLO(model_path)
        self.conf_threshold = conf_threshold
        self.person_class_id = 0  # class 'person' di dataset COCO

    def detect(self, frame):
        """
        Deteksi semua orang dalam satu frame.

        Return: list of dict -> {"bbox": (x1, y1, x2, y2), "conf": float}
        """
        results = self.model(
            frame,
            verbose=False,
            conf=self.conf_threshold,
            classes=[self.person_class_id],
        )

        detections = []
        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
                conf = float(box.conf[0])
                detections.append({"bbox": (int(x1), int(y1), int(x2), int(y2)), "conf": conf})
        return detections
