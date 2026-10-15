# Third-party notices

Facet uses the following components. Each one keeps its own licence.

| Component | Used for | Licence |
|---|---|---|
| [Qt for Python (PySide6)](https://doc.qt.io/qtforpython-6/) | User interface | LGPL-3.0 |
| [Pillow](https://python-pillow.org/) | Image decoding and resizing | MIT-CMU (HPND) |
| [rawpy](https://github.com/letmaik/rawpy) / [LibRaw](https://www.libraw.org/) | RAW decoding | MIT / LGPL-2.1 or CDDL-1.0 |
| [pillow-heif](https://github.com/bigcat88/pillow_heif) / [libheif](https://github.com/strukturag/libheif) | HEIC/HEIF decoding | BSD-3-Clause / LGPL-3.0 |
| [OpenCV](https://opencv.org/) (`opencv-python-headless`) | Local face detection and recognition | Apache-2.0 |
| [NumPy](https://numpy.org/) | Face embeddings | BSD-3-Clause |
| [YuNet face detection model](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet) (`facet/assets/models/face_detection_yunet_2023mar.onnx`) | Finding faces | MIT – see `facet/assets/models/LICENSE-yunet.txt` |
| [SFace face recognition model](https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface) (`facet/assets/models/face_recognition_sface_2021dec.onnx`) | Grouping faces of the same person | Apache-2.0 – see `facet/assets/models/LICENSE-sface.txt` |

**TypeSafe Jev** is an online service used through its public API
(<https://docs.typesafe.ai>). Photos are sent to it only when you start an analysis. Its use is governed by
TypeSafe's terms.
