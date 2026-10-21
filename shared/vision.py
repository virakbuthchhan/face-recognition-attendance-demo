from pathlib import Path
import cv2
import numpy as np

MODEL_VERSION = 'sface-2021dec-yunet-2023mar-v1'


class Vision:
    def __init__(self, model_dir):
        root = Path(model_dir)
        self.detector = cv2.FaceDetectorYN.create(str(root / 'face_detection_yunet_2023mar.onnx'), '', (320, 320), 0.9)
        self.recognizer = cv2.FaceRecognizerSF.create(str(root / 'face_recognition_sface_2021dec.onnx'), '')

    def detect(self, frame):
        self.detector.setInputSize((frame.shape[1], frame.shape[0]))
        _, faces = self.detector.detect(frame)
        return [] if faces is None else faces

    def embedding(self, frame, face):
        crop = self.recognizer.alignCrop(frame, face)
        vector = self.recognizer.feature(crop).reshape(-1)
        return vector / max(float(np.linalg.norm(vector)), 1e-12)


def match(vector, employees, threshold=0.5, margin=0.08):
    scores = sorted([(max(float(np.dot(vector, e)) for e in p['embeddings']), p)
                     for p in employees if p['embeddings']], key=lambda x: x[0], reverse=True)
    if not scores or scores[0][0] < threshold:
        return None
    if len(scores) > 1 and scores[0][0] - scores[1][0] < margin:
        return None
    return scores[0]
