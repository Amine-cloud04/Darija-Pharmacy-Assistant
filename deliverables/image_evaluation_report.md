# Real-photo OCR spot check

- Dataset: [Medicine Boxes Annotated (test split)](https://huggingface.co/datasets/gokuljegadeesan/Medicine_boxes_annotated) (MIT (as stated on the dataset card)).
- Split / sample: `test/1745236103.jpg`; one photograph, one manually read product name (`DiaCURE`).
- The dataset's own annotation is the generic class `Med-Box (generic box class)`, not a product identity. The product name was transcribed manually from the image.
- Local OCR text: `ENFANTS / CHILDREN / ©`.
- Visible-text character error rate: 7/22 = 31.8%.
- Product name read: `False`. Exact local-catalog top-1/top-3 identification: 0/1 (the pictured foreign-market product is not in the Moroccan catalogue).
- Safety behavior: 0 catalogue candidates; confirmation required: True.

This spot check demonstrates a real-image failure case. It is too small and geographically mismatched to estimate general performance. The raw image is downloaded temporarily at evaluation time and is not redistributed in this repository. Full machine-readable output: `deliverables/image_evaluation_results.json`.
